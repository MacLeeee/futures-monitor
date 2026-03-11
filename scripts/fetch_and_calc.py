#!/usr/bin/env python3
# ============================================================
# 期货监控系统 - 数据抓取与指标计算 (Python + AKShare)
# 运行环境: Python 3.10+  依赖: akshare pandas numpy
# 输出:     futures-monitor/public/data.json
# ============================================================

import json
import os
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import akshare as ak
except ImportError:
    print("[FATAL] akshare 未安装，请执行: pip install akshare pandas numpy")
    sys.exit(1)

# 中国期货交易时段（北京时间）
# 窗口比实际交易时间各宽约 5 分钟，确保 :25/:55 的 cron 也能通过守卫
TRADING_WINDOWS = [
    (time(8, 50), time(11, 40)),
    (time(13, 20), time(15, 10)),
    (time(20, 50), time(23, 40)),
]

# 三个开盘时间窗口（各90分钟，覆盖 GitHub cron 最大延迟）
OPEN_WINDOWS: list[tuple[time, time, str]] = [
    (time(8, 45),  time(10, 15), "早盘"),
    (time(13, 00), time(14, 30), "午盘"),
    (time(20, 45), time(22, 15), "夜盘"),
]

def is_trading_time() -> bool:
    tz = ZoneInfo("Asia/Shanghai")
    now_bj = datetime.now(tz)
    if now_bj.weekday() >= 5:
        return False
    t = now_bj.time()
    for s, e in TRADING_WINDOWS:
        if s <= t <= e:
            return True
    return False

def get_open_session() -> str | None:
    """返回当前开盘时间窗口名称，不在窗口内返回 None。"""
    tz = ZoneInfo("Asia/Shanghai")
    now_bj = datetime.now(tz)
    if now_bj.weekday() >= 5:
        return None
    t = now_bj.time()
    for start, end, name in OPEN_WINDOWS:
        if start <= t <= end:
            return name
    return None

def find_session_gap(df: pd.DataFrame) -> tuple[float, float, float] | None:
    """
    扫描最近4对相邻K线，找到跨越交易时段的断层（间隔>60分钟）。
    返回 (gap_pct, new_session_open, prev_session_close) 或 None。
    这比直接用 df.iloc[-1].open 更可靠——避免因 AKShare 延迟未返回新K线时误比较。
    """
    n = len(df)
    if n < 3:
        return None
    for lag in range(1, min(5, n)):
        idx_new = n - lag
        idx_old = n - lag - 1
        try:
            t_new = pd.to_datetime(df["time"].iloc[idx_new])
            t_old = pd.to_datetime(df["time"].iloc[idx_old])
            gap_min = (t_new - t_old).total_seconds() / 60
            if gap_min >= 60:
                op = float(df["open"].iloc[idx_new])
                pc = float(df["close"].iloc[idx_old])
                if pc > 0:
                    gap_pct = round((op - pc) / pc * 100, 3)
                    return gap_pct, round(op, 2), round(pc, 2)
        except Exception:
            continue
    return None

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "futures-monitor" / "public" / "data.json"

# ── 品种定义 ─────────────────────────────────────────────────
SYMBOLS = [
    ("黄金",     "贵金属", "AU0"),
    ("白银",     "贵金属", "AG0"),
    ("铜",       "有色",   "CU0"),
    ("铝",       "有色",   "AL0"),
    ("镍",       "有色",   "NI0"),
    ("锡",       "有色",   "SN0"),
    ("碳酸锂",   "有色",   "LC0"),
    ("铁矿石",   "黑色",   "I0" ),
    ("螺纹钢",   "黑色",   "RB0"),
    ("焦煤",     "黑色",   "JM0"),
    ("锰硅",     "黑色",   "SM0"),
    ("硅铁",     "黑色",   "SF0"),
    ("生猪",     "农产品", "LH0"),
    ("玉米",     "农产品", "C0" ),
    ("棉花",     "农产品", "CF0"),
    ("白糖",     "农产品", "SR0"),
    ("豆油",     "油脂",   "Y0" ),
    ("菜油",     "油脂",   "OI0"),
    ("棕榈油",   "油脂",   "P0" ),
    ("豆粕",     "油脂",   "M0" ),
    ("菜粕",     "油脂",   "RM0"),
    ("原油",     "能化",   "SC0"),
    ("燃油",     "能化",   "FU0"),
    ("苯乙烯",   "能化",   "EB0"),
    ("烧碱",     "能化",   "SH0"),
    ("橡胶",     "能化",   "RU0"),
    ("PVC",      "能化",   "V0" ),
    ("玻璃",     "建材",   "FG0"),
    ("纯碱",     "建材",   "SA0"),
    ("中证1000", "股指",   "IM0"),
]

# ── K 线获取 ──────────────────────────────────────────────────
def fetch_klines(code: str, rows: int = 200) -> pd.DataFrame:
    df = ak.futures_zh_minute_sina(symbol=code, period="30")
    if df is None or len(df) < 30:
        raise ValueError(f"数据不足: {len(df) if df is not None else 0} 行")
    df.columns = df.columns.str.lower()
    df = df.rename(columns={"datetime": "time"})
    df["open_interest"] = pd.to_numeric(df.get("hold", np.nan), errors="coerce")
    return df.tail(rows).reset_index(drop=True)

# ── 指标计算 ──────────────────────────────────────────────────
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def calc_ma(df: pd.DataFrame) -> dict:
    c = df["close"]
    ma20, ma60 = c.rolling(20).mean(), c.rolling(60).mean()
    n = len(df)

    def st(i):
        v, m20, m60 = c.iloc[i], ma20.iloc[i], ma60.iloc[i]
        if pd.isna(m20) or pd.isna(m60): return "Silent"
        if v > m20 and v > m60:  return "Upward"
        if v < m20 and v < m60:  return "Downward"
        return "Silent"

    cur = st(n - 1)
    cnt = 1
    for i in range(n - 2, -1, -1):
        if st(i) == cur: cnt += 1
        else: break
    return {"status": cur, "cumulative": cnt}

def calc_macd(df: pd.DataFrame) -> dict:
    c = df["close"]
    diff = ema(c, 12) - ema(c, 26)
    dea  = ema(diff, 9)
    hist = diff - dea          # MACD 柱状图（diff - dea）
    n = len(df)

    # ── 方向：hist 正负决定金叉区 / 死叉区 ──
    sign = "positive" if float(hist.iloc[-1]) >= 0 else "negative"

    # ── 连续同向根数 ──
    def get_sign(i):
        return "positive" if float(hist.iloc[i]) >= 0 else "negative"
    cnt = 1
    for i in range(n - 2, -1, -1):
        if get_sign(i) == sign:
            cnt += 1
        else:
            break

    # ── 快速走扩：|hist| 逐根变化速率 vs 近 10 期均值 ──
    LOOKBACK = 10
    hist_abs = hist.abs()
    start = max(1, n - LOOKBACK)
    deltas = [float(hist_abs.iloc[i]) - float(hist_abs.iloc[i - 1]) for i in range(start, n)]

    current_delta = deltas[-1] if deltas else 0.0
    prev_deltas = [abs(d) for d in deltas[:-1]]
    avg_abs_delta = float(np.mean(prev_deltas)) if prev_deltas else 0.0

    rapid_expanding = bool(current_delta > 0 and (avg_abs_delta == 0 or current_delta > avg_abs_delta))
    expansion_rate = round(current_delta / avg_abs_delta, 2) if avg_abs_delta > 0 else (1.0 if current_delta > 0 else 0.0)

    return {
        "sign":           sign,
        "rapidExpanding": rapid_expanding,
        "expansionRate":  expansion_rate,
        "cumulative":     cnt,
    }

def calc_volume(df: pd.DataFrame) -> dict:
    v = df["volume"]
    n = len(df)
    if n < 2:
        return {"status": "Shrink", "cumulative": 0, "value": 0, "change": 0, "changePct": 0.0}

    def st(i): return "Surge" if i >= 1 and v.iloc[i] > v.iloc[i - 1] else "Shrink"
    cur = st(n - 1)
    change = float(v.iloc[-1] - v.iloc[-2])
    pct = round(change / float(v.iloc[-2]) * 100, 1) if v.iloc[-2] else 0.0
    cnt = 1
    for i in range(n - 2, 0, -1):
        if st(i) == cur: cnt += 1
        else: break
    return {"status": cur, "cumulative": cnt,
            "value": int(v.iloc[-1]), "change": int(change), "changePct": pct}

def calc_oi(df: pd.DataFrame) -> dict:
    empty = {"value": 0, "prevValue": 0, "change": 0, "changePct": 0.0,
             "status": "Decreasing", "cumulative": 0}
    if "open_interest" not in df.columns: return empty
    oi = df["open_interest"].dropna()
    if len(oi) < 2: return empty
    n = len(df)
    oi_full = df["open_interest"]

    def st(i):
        if i < 1 or pd.isna(oi_full.iloc[i]) or pd.isna(oi_full.iloc[i - 1]):
            return "Decreasing"
        return "Increasing" if oi_full.iloc[i] > oi_full.iloc[i - 1] else "Decreasing"

    cur = st(n - 1)
    cur_v, prev_v = float(oi.iloc[-1]), float(oi.iloc[-2])
    change = cur_v - prev_v
    pct = round(change / prev_v * 100, 2) if prev_v else 0.0
    cnt = 1
    for i in range(n - 2, 0, -1):
        if st(i) == cur: cnt += 1
        else: break
    return {"value": int(cur_v), "prevValue": int(prev_v),
            "change": int(change), "changePct": pct, "status": cur, "cumulative": cnt}

# ── 单品种处理 ────────────────────────────────────────────────
def process_symbol(args: tuple) -> dict | None:
    symbol, category, code = args
    try:
        df = fetch_klines(code)
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        change = round((last - prev) / prev * 100, 2) if prev else 0.0
        # 用时间间隔法检测跨时段跳空（比 iloc[-1].open 更可靠）
        gap_info = find_session_gap(df)  # (gap_pct, open_price, prev_close) or None
        return {
            "symbol":   symbol,
            "category": category,
            "timeframe": "30min",
            "lastUpdate": datetime.now().strftime("%H:%M:%S"),
            "price":     round(last, 2),
            "change":    change,
            "_gapInfo":  gap_info,       # 临时字段，输出前剥离
            "ma":           calc_ma(df),
            "macd":         calc_macd(df),
            "volume":       calc_volume(df),
            "openInterest": calc_oi(df),
        }
    except Exception as e:
        print(f"  [SKIP] {symbol}({code}): {e}", file=sys.stderr)
        return None

# ── Telegram 推送 ─────────────────────────────────────────────

def tg_send(token: str, chat_id: str, text: str) -> None:
    """调用 Telegram Bot API 发送消息，失败不崩溃。"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
        print(f"[TG] 推送成功 ({len(text)} chars)")
    except Exception as e:
        print(f"[TG] 推送失败: {e}", file=sys.stderr)


def build_gap_message(gaps: list[dict], update_time: str) -> str:
    lines = [f"<b>🚨 开盘跳空预警 {update_time} {gaps[0]['session']}</b>"]
    up   = [g for g in gaps if g["direction"] == "up"]
    down = [g for g in gaps if g["direction"] == "down"]
    if up:
        lines.append("\n🔴 <b>跳涨</b>")
        for g in up:
            lines.append(
                f"  ↑ {g['symbol']}({g['category']})"
                f"  +{g['gapPct']:.2f}%"
                f"  开{g['openPrice']} / 前收{g['prevClose']}"
            )
    if down:
        lines.append("\n🟢 <b>跳跌</b>")
        for g in down:
            lines.append(
                f"  ↓ {g['symbol']}({g['category']})"
                f"  {g['gapPct']:.2f}%"
                f"  开{g['openPrice']} / 前收{g['prevClose']}"
            )
    return "\n".join(lines)


def build_signal_message(data: list[dict], update_time: str) -> str | None:
    """
    扫描全量数据，生成推送文本。无信号返回 None。

    触发条件：
    1. 做多信号（4/4）：MA上行 + MACD金叉区走扩 + 放量 + 增仓
    2. 做空信号（4/4）：MA下行 + MACD死叉区走扩 + 放量 + 增仓
    3. 待观察做多（3/4）
    4. 待观察做空（3/4）
    5. 均线第一根上行（cumulative == 1）
    6. 均线第一根下行（cumulative == 1）
    """
    def is_long(d):
        return (d["ma"]["status"] == "Upward"
                and d["macd"]["sign"] == "positive"
                and d["macd"]["rapidExpanding"]
                and d["volume"]["status"] == "Surge"
                and d["openInterest"]["status"] == "Increasing")

    def is_short(d):
        return (d["ma"]["status"] == "Downward"
                and d["macd"]["sign"] == "negative"
                and d["macd"]["rapidExpanding"]
                and d["volume"]["status"] == "Surge"
                and d["openInterest"]["status"] == "Increasing")

    def long_score(d):
        return sum([
            d["ma"]["status"] == "Upward",
            d["macd"]["sign"] == "positive" and d["macd"]["rapidExpanding"],
            d["volume"]["status"] == "Surge",
            d["openInterest"]["status"] == "Increasing",
        ])

    def short_score(d):
        return sum([
            d["ma"]["status"] == "Downward",
            d["macd"]["sign"] == "negative" and d["macd"]["rapidExpanding"],
            d["volume"]["status"] == "Surge",
            d["openInterest"]["status"] == "Increasing",
        ])

    longs       = [d for d in data if is_long(d)]
    shorts      = [d for d in data if is_short(d)]
    near_longs  = [d for d in data if not is_long(d) and long_score(d) == 3]
    near_shorts = [d for d in data if not is_short(d) and short_score(d) == 3]
    ma_first_up = [d for d in data if d["ma"]["status"] == "Upward"   and d["ma"]["cumulative"] == 1]
    ma_first_dn = [d for d in data if d["ma"]["status"] == "Downward" and d["ma"]["cumulative"] == 1]

    # 无任何信号 → 不推送
    if not any([longs, shorts, near_longs, near_shorts, ma_first_up, ma_first_dn]):
        return None

    lines = [f"<b>📊 期货监控信号 {update_time}</b>"]

    def fmt(d):
        sign = "+" if d["change"] > 0 else ""
        return f"{d['symbol']}({d['category']}) {sign}{d['change']:.2f}%"

    if longs:
        lines.append("\n🔴 <b>做多信号（4/4满足）</b>")
        for d in longs:
            lines.append(f"  ✅ {fmt(d)}")
            lines.append(f"     MA上行×{d['ma']['cumulative']} | MACD金叉走扩{d['macd']['expansionRate']:.1f}x | 放量 | 增仓")

    if shorts:
        lines.append("\n🟢 <b>做空信号（4/4满足）</b>")
        for d in shorts:
            lines.append(f"  ✅ {fmt(d)}")
            lines.append(f"     MA下行×{d['ma']['cumulative']} | MACD死叉走扩{d['macd']['expansionRate']:.1f}x | 放量 | 增仓")

    if near_longs:
        lines.append("\n🔸 <b>待观察做多（3/4）</b>")
        missing_map = {
            "MA":   lambda d: d["ma"]["status"] != "Upward",
            "MACD": lambda d: not (d["macd"]["sign"] == "positive" and d["macd"]["rapidExpanding"]),
            "V":    lambda d: d["volume"]["status"] != "Surge",
            "OI":   lambda d: d["openInterest"]["status"] != "Increasing",
        }
        for d in near_longs:
            missing = [k for k, fn in missing_map.items() if fn(d)]
            lines.append(f"  ⚠️ {fmt(d)}  缺: {', '.join(missing)}")

    if near_shorts:
        lines.append("\n🔹 <b>待观察做空（3/4）</b>")
        missing_map = {
            "MA":   lambda d: d["ma"]["status"] != "Downward",
            "MACD": lambda d: not (d["macd"]["sign"] == "negative" and d["macd"]["rapidExpanding"]),
            "V":    lambda d: d["volume"]["status"] != "Surge",
            "OI":   lambda d: d["openInterest"]["status"] != "Increasing",
        }
        for d in near_shorts:
            missing = [k for k, fn in missing_map.items() if fn(d)]
            lines.append(f"  ⚠️ {fmt(d)}  缺: {', '.join(missing)}")

    if ma_first_up:
        lines.append("\n📈 <b>均线首根上行（新突破）</b>")
        for d in ma_first_up:
            lines.append(f"  ↗ {fmt(d)}")

    if ma_first_dn:
        lines.append("\n📉 <b>均线首根下行（新跌破）</b>")
        for d in ma_first_dn:
            lines.append(f"  ↘ {fmt(d)}")

    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────
def main():
    # 非交易时段不抓取、不写文件、不提交，避免空刷；手动触发时可设 FORCE_FETCH=1 强制执行
    if os.environ.get("FORCE_FETCH") != "1" and not is_trading_time():
        print("[SKIP] 非交易时段或非交易日，跳过抓取（不写入、不提交）")
        sys.exit(0)

    print(f"[{datetime.utcnow().isoformat()}Z] Fetching {len(SYMBOLS)} symbols ...")

    results = []
    # 最多 8 线程并发，兼顾速度与新浪限流
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(process_symbol, s): s for s in SYMBOLS}
        for fut in as_completed(futures):
            r = fut.result()
            if r: results.append(r)

    if not results:
        print("[FATAL] No data fetched — aborting write.", file=sys.stderr)
        sys.exit(1)

    # 合并上次数据中本次失败的品种（防止偶发故障清空）
    merged = results
    if OUTPUT.exists():
        try:
            prev = json.loads(OUTPUT.read_text("utf-8"))
            prev_map = {d["symbol"]: d for d in prev.get("data", [])}
            new_set  = {d["symbol"] for d in results}
            kept = [v for k, v in prev_map.items() if k not in new_set]
            merged = results + kept
        except Exception:
            pass

    output = {
        "source":    "github-actions",
        "updatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data":      merged,
    }
    # ── 开盘跳空检测 ──
    session = get_open_session()
    gap_alerts: list[dict] = []
    GAP_THRESHOLD = 0.2  # 跳空阈值 %
    tz_bj = ZoneInfo("Asia/Shanghai")
    bj_now = datetime.now(tz_bj)

    for d in merged:
        gap_info = d.pop("_gapInfo", None)  # (gap_pct, open_price, prev_close) or None
        if session and gap_info:
            gap_pct, open_price, prev_close = gap_info
            if abs(gap_pct) >= GAP_THRESHOLD:
                gap_alerts.append({
                    "symbol":    d["symbol"],
                    "category":  d["category"],
                    "gapPct":    gap_pct,
                    "direction": "up" if gap_pct > 0 else "down",
                    "openPrice": open_price,
                    "prevClose": prev_close,
                    "session":   session,
                })

    gap_alerts.sort(key=lambda x: abs(x["gapPct"]), reverse=True)

    # 跳空扫描确认信息（不论有无跳空，只要在开盘窗口内就记录）
    gap_check_info: dict | None = None
    if session:
        gap_check_info = {
            "checkedAt": bj_now.strftime("%H:%M"),
            "session":   session,
            "count":     len(gap_alerts),
        }
        print(f"[GAP] {session} 跳空扫描完成：{len(gap_alerts)} 个品种跳空幅度≥{GAP_THRESHOLD}%")
    else:
        print("[GAP] 非开盘窗口，跳过跳空检测")

    output = {
        "source":       "github-actions",
        "updatedAt":    datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "gapCheckInfo": gap_check_info,
        "gapAlerts":    gap_alerts,
        "data":         merged,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    print(f"✓ {len(results)}/{len(SYMBOLS)} symbols → {OUTPUT}")

    # ── Telegram 推送 ──
    tg_token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat_id:
        bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
        messages = []
        # 跳空推送
        if gap_alerts:
            messages.append(build_gap_message(gap_alerts, bj_time))
        # 信号推送
        sig_msg = build_signal_message(merged, bj_time)
        if sig_msg:
            messages.append(sig_msg)
        if messages:
            tg_send(tg_token, tg_chat_id, "\n\n".join(messages))
        else:
            print("[TG] 无跳空/信号，不推送")

if __name__ == "__main__":
    main()

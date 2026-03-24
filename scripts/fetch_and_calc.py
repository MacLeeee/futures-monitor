#!/usr/bin/env python3
# ============================================================
# 期货监控系统 - 数据抓取与指标计算 (Python + AKShare)
# 运行环境: Python 3.10+  依赖: akshare pandas numpy
# 输出:     futures-monitor/public/data.json       (30min)
#           futures-monitor/public/data_daily.json (日K 复盘)
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

ROOT         = Path(__file__).parent.parent
OUTPUT       = ROOT / "futures-monitor" / "public" / "data.json"
OUTPUT_DAILY = ROOT / "futures-monitor" / "public" / "data_daily.json"

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
def fetch_klines(code: str, rows: int = 200, _retries: int = 3) -> pd.DataFrame:
    import time as _time
    last_err: Exception = RuntimeError("未知错误")
    for attempt in range(1, _retries + 1):
        try:
            df = ak.futures_zh_minute_sina(symbol=code, period="30")
            if df is None or len(df) < 30:
                raise ValueError(f"数据不足: {len(df) if df is not None else 0} 行")
            df.columns = df.columns.str.lower()
            df = df.rename(columns={"datetime": "time"})
            df["open_interest"] = pd.to_numeric(df.get("hold", np.nan), errors="coerce")
            return df.tail(rows).reset_index(drop=True)
        except Exception as e:
            last_err = e
            if attempt < _retries:
                _time.sleep(2 * attempt)  # 2s, 4s 退避后重试
    raise last_err

def fetch_klines_daily(code: str, rows: int = 200) -> pd.DataFrame:
    """获取日K线数据（近 rows 根），使用 Sina 主力合约历史接口。"""
    from datetime import date, timedelta
    end_d   = date.today().strftime("%Y%m%d")
    start_d = (date.today() - timedelta(days=600)).strftime("%Y%m%d")
    df = ak.futures_main_sina(symbol=code, start_date=start_d, end_date=end_d)
    if df is None or len(df) < 30:
        raise ValueError(f"日K数据不足: {len(df) if df is not None else 0} 行")
    col_map = {
        "日期": "time", "开盘价": "open", "最高价": "high",
        "最低价": "low", "收盘价": "close", "成交量": "volume", "持仓量": "open_interest",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "open_interest" not in df.columns:
        df["open_interest"] = 0.0
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce").fillna(0)
    df = df.dropna(subset=["close"])
    return df.tail(rows).reset_index(drop=True)

# ── 指标计算 ──────────────────────────────────────────────────
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def calc_ma(df: pd.DataFrame) -> dict:
    c = df["close"]
    ma20s = c.rolling(20).mean()
    ma60s = c.rolling(60).mean()
    n = len(df)

    def st(i):
        v, m20, m60 = c.iloc[i], ma20s.iloc[i], ma60s.iloc[i]
        if pd.isna(m20) or pd.isna(m60): return "Silent"
        if v > m20 and v > m60:  return "Upward"
        if v < m20 and v < m60:  return "Downward"
        return "Silent"

    cur = st(n - 1)
    cnt = 1
    for i in range(n - 2, -1, -1):
        if st(i) == cur: cnt += 1
        else: break

    ma20_cur = float(ma20s.iloc[-1]) if not pd.isna(ma20s.iloc[-1]) else None
    ma60_cur = float(ma60s.iloc[-1]) if not pd.isna(ma60s.iloc[-1]) else None

    # MA20斜率：用倒数第4根K线（3根前）作基准，计算3根内的累计%变化
    slope20_pct = 0.0
    slope_type  = "flat"
    if ma20_cur and n >= 5:
        old_val = float(ma20s.iloc[-4]) if not pd.isna(ma20s.iloc[-4]) else None
        if old_val and old_val > 0:
            slope20_pct = round((ma20_cur - old_val) / old_val * 100, 4)
            # 0.2% / 3根K线 ≈ 视觉上 45° 参考线
            if slope20_pct > 0.2:
                slope_type = "steep"      # 急速上行（≥45°）
            elif slope20_pct >= 0:
                slope_type = "gentle"     # 缓慢上行（<45°）
            else:
                slope_type = "declining"  # 下行

    return {
        "status":     cur,
        "cumulative": cnt,
        "ma20":       round(ma20_cur, 2) if ma20_cur else None,
        "ma60":       round(ma60_cur, 2) if ma60_cur else None,
        "slope20Pct": slope20_pct,
        "slopeType":  slope_type,
    }

# 抄底阈值：收盘价距支撑均线最大距离（%）
_DIP_TOL    = 0.5
_BOUNCE_TOL = 0.5   # 回踩策略均线距离阈值（%）

def calc_dip_signal(close: float, ma: dict, macd: dict) -> dict | None:
    """
    抄底信号：MACD 死叉区 + 幅度缩窄（粘合），收盘触及支撑均线。
    - MA20 急速上行（steep）→ MA20 支撑，收盘在 MA20 ± 0.5%
    - MA20 缓慢上行（gentle）→ MA60 支撑，收盘在 MA60 ± 0.5%
    """
    if macd["sign"] != "negative" or macd["rapidExpanding"]:
        return None
    slope_type = ma.get("slopeType", "flat")
    ma20 = ma.get("ma20")
    ma60 = ma.get("ma60")
    if slope_type == "steep" and ma20 and ma20 > 0:
        dist = abs(close - ma20) / ma20 * 100
        if dist <= _DIP_TOL:
            return {"type": "MA20", "support": round(ma20, 2),
                    "distPct": round(dist, 3), "slopeType": slope_type}
    elif slope_type == "gentle" and ma60 and ma60 > 0:
        dist = abs(close - ma60) / ma60 * 100
        if dist <= _DIP_TOL:
            return {"type": "MA60", "support": round(ma60, 2),
                    "distPct": round(dist, 3), "slopeType": slope_type}
    return None

def calc_strategy_signal(
    close: float,
    ma: dict,
    macd: dict,
    volume: dict,
    daily_ma20: float | None,
) -> dict | None:
    """
    回踩策略信号（与 strategy.py 逻辑对应）。
    做多: close > 日MA20 & 30min多头排列 & 回踩均线 & MACD金叉扩口 & 放量
    做空: close < 日MA20 & 30min空头排列 & 反抽均线 & MACD死叉扩口 & 放量
    """
    ma20 = ma.get("ma20")
    ma60 = ma.get("ma60")
    slope_type = ma.get("slopeType", "flat")

    if not ma20 or not ma60 or ma20 <= 0 or ma60 <= 0:
        return None

    dist_ma20 = abs(close - ma20) / ma20 * 100
    dist_ma60 = abs(close - ma60) / ma60 * 100

    # 均线排列判断
    bull_aligned = (ma20 > ma60) and slope_type in ("steep", "gentle")
    bear_aligned = (ma20 < ma60) and slope_type == "declining"

    # 回踩/反抽均线（价格贴近均线 ±0.5%）
    bounce_ma20_long  = bull_aligned and dist_ma20 <= _BOUNCE_TOL and close >= ma20 * (1 - _BOUNCE_TOL / 100)
    bounce_ma60_long  = (ma20 > ma60)  and dist_ma60 <= _BOUNCE_TOL and close >= ma60 * (1 - _BOUNCE_TOL / 100)
    bounce_ma20_short = bear_aligned and dist_ma20 <= _BOUNCE_TOL and close <= ma20 * (1 + _BOUNCE_TOL / 100)
    bounce_ma60_short = (ma20 < ma60)  and dist_ma60 <= _BOUNCE_TOL and close <= ma60 * (1 + _BOUNCE_TOL / 100)

    # MACD 动能爆发方向
    macd_surge_long  = (macd.get("sign") == "positive") and macd.get("rapidExpanding", False)
    macd_surge_short = (macd.get("sign") == "negative") and macd.get("rapidExpanding", False)

    # 放量确认
    volume_confirm = volume.get("status") == "Surge"

    # 日线 MA20 过滤（无数据时不过滤）
    above_daily = (daily_ma20 is None) or (close > daily_ma20)
    below_daily = (daily_ma20 is None) or (close < daily_ma20)

    long_signal = (
        above_daily
        and bull_aligned
        and (bounce_ma20_long or bounce_ma60_long)
        and macd_surge_long
        and volume_confirm
    )
    short_signal = (
        below_daily
        and bear_aligned
        and (bounce_ma20_short or bounce_ma60_short)
        and macd_surge_short
        and volume_confirm
    )

    if not long_signal and not short_signal:
        return None

    direction = "long" if long_signal else "short"
    if direction == "long":
        bounce_at = "MA20" if bounce_ma20_long else "MA60"
        dist_pct  = dist_ma20 if bounce_at == "MA20" else dist_ma60
    else:
        bounce_at = "MA20" if bounce_ma20_short else "MA60"
        dist_pct  = dist_ma20 if bounce_at == "MA20" else dist_ma60

    return {
        "type":      direction,              # "long" | "short"
        "bounceAt":  bounce_at,              # "MA20" | "MA60"
        "distPct":   round(dist_pct, 3),
        "ma20":      round(ma20, 2),
        "ma60":      round(ma60, 2),
        "dailyMa20": round(daily_ma20, 2) if daily_ma20 else None,
    }


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
def process_symbol(args: tuple, daily_ma20: float | None = None) -> dict | None:
    symbol, category, code = args
    try:
        df = fetch_klines(code)
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        change = round((last - prev) / prev * 100, 2) if prev else 0.0
        ma_data   = calc_ma(df)
        macd_data = calc_macd(df)
        vol_data  = calc_volume(df)
        return {
            "symbol":         symbol,
            "category":       category,
            "timeframe":      "30min",
            "lastUpdate":     datetime.now().strftime("%H:%M:%S"),
            "price":          round(last, 2),
            "change":         change,
            "ma":             ma_data,
            "macd":           macd_data,
            "volume":         vol_data,
            "openInterest":   calc_oi(df),
            "dipSignal":      calc_dip_signal(round(last, 2), ma_data, macd_data),
            "strategySignal": calc_strategy_signal(round(last, 2), ma_data, macd_data, vol_data, daily_ma20),
        }
    except Exception as e:
        print(f"  [SKIP] {symbol}({code}): {e}", file=sys.stderr)
        return None

def process_symbol_daily(args: tuple) -> dict | None:
    """处理单品种日K数据（与 process_symbol 逻辑相同，仅数据源不同）。"""
    symbol, category, code = args
    try:
        df = fetch_klines_daily(code)
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        change = round((last - prev) / prev * 100, 2) if prev else 0.0
        ma_data   = calc_ma(df)
        macd_data = calc_macd(df)
        return {
            "symbol":       symbol,
            "category":     category,
            "timeframe":    "daily",
            "lastUpdate":   str(df["time"].iloc[-1]) if "time" in df.columns else "",
            "price":        round(last, 2),
            "change":       change,
            "ma":           ma_data,
            "macd":         macd_data,
            "volume":       calc_volume(df),
            "openInterest": calc_oi(df),
            "dipSignal":    calc_dip_signal(round(last, 2), ma_data, macd_data),
        }
    except Exception as e:
        print(f"  [SKIP-D] {symbol}({code}): {e}", file=sys.stderr)
        return None

# ── Telegram 推送 ─────────────────────────────────────────────

def tg_send(token: str, chat_id: str, text: str, label: str = "") -> None:
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
        tag = f"[{label}] " if label else ""
        print(f"[TG] {tag}推送成功 ({len(text)} chars)")
    except Exception as e:
        tag = f"[{label}] " if label else ""
        print(f"[TG] {tag}推送失败: {e}", file=sys.stderr)


def tg_send_all(text: str) -> None:
    """向所有配置的 Telegram Bot 发送同一条消息。"""
    bots = [
        (os.environ.get("TELEGRAM_BOT_TOKEN",   ""),
         os.environ.get("TELEGRAM_CHAT_ID",     ""),
         "Bot1"),
        (os.environ.get("TELEGRAM_BOT_TOKEN_2", ""),
         os.environ.get("TELEGRAM_CHAT_ID_2",   ""),
         "Bot2"),
    ]
    sent = 0
    for token, chat_id, label in bots:
        if token and chat_id:
            tg_send(token, chat_id, text, label)
            sent += 1
    if sent == 0:
        print("[TG] 未配置任何 Bot Token，跳过推送")


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


def build_dip_message(data: list[dict], bj_time: str) -> str | None:
    """构建抄底信号推送文本。"""
    dips = [d for d in data if d.get("dipSignal")]
    if not dips:
        return None
    ma20_dips = [d for d in dips if d["dipSignal"]["type"] == "MA20"]
    ma60_dips = [d for d in dips if d["dipSignal"]["type"] == "MA60"]

    def fmt_dip(d: dict) -> str:
        sig  = d["dipSignal"]
        chg  = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        slp  = f"+{d['ma']['slope20Pct']:.3f}%" if d['ma']['slope20Pct'] >= 0 else f"{d['ma']['slope20Pct']:.3f}%"
        return (f"  ↩ {d['symbol']}({d['category']}) {chg}"
                f"  距{sig['type']}: {sig['distPct']:.3f}%"
                f"  斜率: {slp}/3K"
                f"  MACD死叉×{d['macd']['cumulative']}")

    lines = [f"<b>🎯 抄底信号 {bj_time}</b>"]
    if ma20_dips:
        lines.append("\n🟦 <b>MA20 抄底</b>（急速上行≥45°·收盘触及MA20）")
        lines.extend(fmt_dip(d) for d in ma20_dips)
    if ma60_dips:
        lines.append("\n🟩 <b>MA60 抄底</b>（缓慢上行&lt;45°·收盘触及MA60）")
        lines.extend(fmt_dip(d) for d in ma60_dips)
    return "\n".join(lines)


def build_strategy_message(data: list[dict], bj_time: str) -> str | None:
    """构建回踩策略信号推送文本。"""
    longs  = [d for d in data if d.get("strategySignal") and d["strategySignal"]["type"] == "long"]
    shorts = [d for d in data if d.get("strategySignal") and d["strategySignal"]["type"] == "short"]
    if not longs and not shorts:
        return None

    def fmt_strat(d: dict) -> str:
        sig = d["strategySignal"]
        chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        dma = f"日MA20={sig['dailyMa20']}" if sig.get("dailyMa20") else "日MA20=N/A"
        return (f"  {d['symbol']}({d['category']}) {chg}"
                f"  回踩{sig['bounceAt']}: {sig['distPct']:.3f}%  {dma}"
                f"  MACD×{d['macd']['cumulative']}")

    lines = [f"<b>📐 回踩策略信号 {bj_time}</b>"]
    if longs:
        lines.append("\n🟢 <b>做多回踩</b>（30m多头排列·回踩均线·MACD金叉扩口·放量·日MA20上方）")
        lines.extend(fmt_strat(d) for d in longs)
    if shorts:
        lines.append("\n🔴 <b>做空反抽</b>（30m空头排列·反抽均线·MACD死叉扩口·放量·日MA20下方）")
        lines.extend(fmt_strat(d) for d in shorts)
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────
def main():
    # 非交易时段不抓取、不写文件、不提交，避免空刷；手动触发时可设 FORCE_FETCH=1 强制执行
    if os.environ.get("FORCE_FETCH") != "1" and not is_trading_time():
        print("[SKIP] 非交易时段或非交易日，跳过抓取（不写入、不提交）")
        sys.exit(0)

    # ── Step 1: 先抓日K，获取日线 MA20（用于策略过滤）──
    print("[DAILY] 开始抓取日K数据（用于日MA20过滤）...")
    daily_results_pre: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(process_symbol_daily, s): s for s in SYMBOLS}
        for fut in as_completed(futs):
            r = fut.result()
            if r: daily_results_pre.append(r)
    # symbol → 日线MA20值
    daily_ma20_map: dict[str, float | None] = {
        r["symbol"]: r["ma"].get("ma20") for r in daily_results_pre
    }

    # ── Step 2: 抓30min数据，传入日MA20 ──
    print(f"[{datetime.utcnow().isoformat()}Z] Fetching {len(SYMBOLS)} symbols ...")

    results = []
    # 最多 8 线程并发，兼顾速度与新浪限流
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(process_symbol, s, daily_ma20_map.get(s[0])): s
            for s in SYMBOLS
        }
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
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    print(f"✓ {len(results)}/{len(SYMBOLS)} symbols → {OUTPUT}")

    # ── 日K数据（已在 Step 1 完成，直接写文件）──
    daily_results = daily_results_pre
    if daily_results:
        daily_output = {
            "source":    "local-runner",
            "updatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "data":      daily_results,
        }
        OUTPUT_DAILY.write_text(json.dumps(daily_output, ensure_ascii=False, indent=2), "utf-8")
        print(f"✓ {len(daily_results)}/{len(SYMBOLS)} daily symbols → {OUTPUT_DAILY}")
    else:
        print("[DAILY] 无日K数据写入", file=sys.stderr)

    # ── Telegram 推送（仅30min信号，日K不推）──
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
    messages = []
    sig_msg = build_signal_message(merged, bj_time)
    if sig_msg:
        messages.append(sig_msg)
    dip_msg = build_dip_message(merged, bj_time)
    if dip_msg:
        messages.append(dip_msg)
    strat_msg = build_strategy_message(merged, bj_time)
    if strat_msg:
        messages.append(strat_msg)
    if messages:
        tg_send_all("\n\n".join(messages))
    else:
        print("[TG] 无突破/抄底/策略信号，不推送")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# ============================================================
# 期货监控系统 - 数据抓取与指标计算 (Python + AKShare)
# 运行环境: Python 3.10+  依赖: akshare pandas numpy
# 输出:     futures-monitor/public/data.json
# ============================================================

import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import akshare as ak
except ImportError:
    print("[FATAL] akshare 未安装，请执行: pip install akshare pandas numpy")
    sys.exit(1)

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
    cnt = sum(1 for i in range(n - 2, -1, -1) if st(i) == cur or cnt_break(i))
    # 重写：手动累计
    cnt = 1
    for i in range(n - 2, -1, -1):
        if st(i) == cur: cnt += 1
        else: break
    return {"status": cur, "cumulative": cnt}

def calc_macd(df: pd.DataFrame) -> dict:
    c = df["close"]
    diff = ema(c, 12) - ema(c, 26)
    dea  = ema(diff, 9)
    hist = diff - dea
    n = len(df)

    cross = "无"
    if diff.iloc[-1] > 0 and dea.iloc[-1] > 0 and diff.iloc[-2] < dea.iloc[-2] and diff.iloc[-1] > dea.iloc[-1]:
        cross = "水上金叉"
    elif diff.iloc[-1] < 0 and dea.iloc[-1] < 0 and diff.iloc[-2] > dea.iloc[-2] and diff.iloc[-1] < dea.iloc[-1]:
        cross = "水下死叉"

    d, d2 = float(diff.iloc[-1]), float(dea.iloc[-1])
    region = "水上" if d > d2 and d > 0 else "水下" if d < d2 and d < 0 else "中性"

    cur_abs, prev_abs = abs(hist.iloc[-1]), abs(hist.iloc[-2])
    same_sign = hist.iloc[-1] * hist.iloc[-2] > 0
    spread = "Expanding" if same_sign and cur_abs > prev_abs else "Shrinking"

    def sp(i):
        if i < 1: return "Shrinking"
        ss = hist.iloc[i] * hist.iloc[i - 1] > 0
        return "Expanding" if ss and abs(hist.iloc[i]) > abs(hist.iloc[i - 1]) else "Shrinking"

    cnt = 1
    for i in range(n - 2, 0, -1):
        if sp(i) == spread: cnt += 1
        else: break
    return {"crossStatus": cross, "spreadStatus": spread, "cumulative": cnt, "region": region}

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
        return {
            "symbol":   symbol,
            "category": category,
            "timeframe": "30min",
            "lastUpdate": datetime.now().strftime("%H:%M:%S"),
            "price":  round(last, 2),
            "change": change,
            "ma":           calc_ma(df),
            "macd":         calc_macd(df),
            "volume":       calc_volume(df),
            "openInterest": calc_oi(df),
        }
    except Exception as e:
        print(f"  [SKIP] {symbol}({code}): {e}", file=sys.stderr)
        return None

# ── 主流程 ────────────────────────────────────────────────────
def main():
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
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    print(f"✓ {len(results)}/{len(SYMBOLS)} symbols → {OUTPUT}")

if __name__ == "__main__":
    main()

# 辅助（避免 linter 报 undefined）
def cnt_break(_): return False

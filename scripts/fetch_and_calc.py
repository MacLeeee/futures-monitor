#!/usr/bin/env python3
# ============================================================
# 期货监控系统 - 数据抓取与指标计算 (Python + AKShare)
# 运行环境: Python 3.10+  依赖: akshare pandas numpy
#
# 多周期策略架构：
#   30min K线 → MA20/MA60 方向判断（均线排列、斜率）
#   15min K线 → MACD、成交量、持仓量触发条件
#
# 两类信号：
#   突破信号: 30min MA排列方向 + 15min MACD扩口 + 15min放量 [+ 15min增仓]
#   回踩信号: 30min MA60锚定多空 + 价格回踩MA20/MA60 ±0.5% + 15min MACD方向缩窄 + 15min放量
#
# 输出: futures-monitor/public/data.json       (30min+15min)
#       futures-monitor/public/data_daily.json (日K 复盘)
# ============================================================

import json
import os
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, UTC
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

ROOT            = Path(__file__).parent.parent
OUTPUT          = ROOT / "futures-monitor" / "public" / "data.json"
OUTPUT_DAILY    = ROOT / "futures-monitor" / "public" / "data_daily.json"
POSITIONS_FILE  = ROOT / "futures-monitor" / "public" / "positions.json"

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
    ("甲醇",     "能化",   "MA0"),
    ("对二甲苯", "能化",   "PX0"),
    ("乙二醇",   "能化",   "EG0"),
    ("合成橡胶", "能化",   "BR0"),
    ("低硫燃油", "能化",   "LU0"),
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

def fetch_klines_15m(code: str, rows: int = 200, _retries: int = 3) -> pd.DataFrame:
    """获取 15 分钟 K 线数据，供 MACD/量/OI 触发层使用。"""
    import time as _time
    last_err: Exception = RuntimeError("未知错误")
    for attempt in range(1, _retries + 1):
        try:
            df = ak.futures_zh_minute_sina(symbol=code, period="15")
            if df is None or len(df) < 30:
                raise ValueError(f"15m数据不足: {len(df) if df is not None else 0} 行")
            df.columns = df.columns.str.lower()
            df = df.rename(columns={"datetime": "time"})
            df["open_interest"] = pd.to_numeric(df.get("hold", np.nan), errors="coerce")
            return df.tail(rows).reset_index(drop=True)
        except Exception as e:
            last_err = e
            if attempt < _retries:
                _time.sleep(2 * attempt)
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

    # MA20 斜率：用倒数第4根（3根前）作基准，计算3根内的累计%变化
    slope20_pct = 0.0
    slope_type  = "flat"
    if ma20_cur and n >= 5:
        old_val = float(ma20s.iloc[-4]) if not pd.isna(ma20s.iloc[-4]) else None
        if old_val and old_val > 0:
            slope20_pct = round((ma20_cur - old_val) / old_val * 100, 4)
            if slope20_pct > 0.2:
                slope_type = "steep"
            elif slope20_pct >= 0:
                slope_type = "gentle"
            else:
                slope_type = "declining"

    # MA60 斜率：同样用3根窗口，判断长均线方向
    slope60_pct = 0.0
    if ma60_cur and n >= 5:
        old60 = float(ma60s.iloc[-4]) if not pd.isna(ma60s.iloc[-4]) else None
        if old60 and old60 > 0:
            slope60_pct = round((ma60_cur - old60) / old60 * 100, 4)

    return {
        "status":     cur,
        "cumulative": cnt,
        "ma20":       round(ma20_cur, 2) if ma20_cur else None,
        "ma60":       round(ma60_cur, 2) if ma60_cur else None,
        "slope20Pct": slope20_pct,
        "slope60Pct": slope60_pct,
        "slopeType":  slope_type,
    }


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    """14周期 ATR（平均真实波幅），用于止损距离计算。"""
    n = len(df)
    if n < period + 1:
        return 0.0
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return round(float(tr.iloc[-period:].mean()), 4)


# ══════════════════════════════════════════════════════════════
# 市场状态判定：趋势 vs 震荡
# 维度1: 唐奇安通道 + 枢轴点结构
# 维度2: EMA缎带(20/50/120) + 斜率
# ══════════════════════════════════════════════════════════════

def calc_donchian(df: pd.DataFrame, period: int = 20) -> dict:
    """唐奇安通道: N周期最高/最低 + 中轴 + 宽度%。"""
    n = len(df)
    if n < period:
        return {"upper": 0, "lower": 0, "basis": 0, "widthPct": 0, "pricePos": 0.5}
    high   = df["high"].astype(float)
    low    = df["low"].astype(float)
    close  = float(df["close"].iloc[-1])
    upper  = float(high.iloc[-period:].max())
    lower  = float(low.iloc[-period:].min())
    basis  = (upper + lower) / 2
    width  = upper - lower
    width_pct = round(width / basis * 100, 4) if basis > 0 else 0
    price_pos = round((close - lower) / width, 4) if width > 0 else 0.5
    # 通道近 5 根的斜率变化（上轨是否走平）
    if n >= period + 5:
        old_upper = float(high.iloc[-(period + 5):-5].max())
        old_lower = float(low.iloc[-(period + 5):-5].min())
        old_width = old_upper - old_lower
        flat_ratio = round(abs(width - old_width) / max(old_width, 0.01), 4)
    else:
        flat_ratio = 0.0
    return {
        "upper":     round(upper, 4),
        "lower":     round(lower, 4),
        "basis":     round(basis, 4),
        "widthPct":  width_pct,
        "pricePos":  price_pos,      # 0=下轨, 0.5=中轴, 1=上轨
        "flatRatio": flat_ratio,     # 通道宽度变化率，越小越走平
    }


def calc_pivot_structure(df: pd.DataFrame, lookback: int = 5) -> dict:
    """
    用分型点(Fractal)识别枢轴高低点序列，判定趋势结构。
    返回: structure="HH_HL"|"LL_LH"|"mixed", pivotHighs=[], pivotLows=[]
    """
    n = len(df)
    if n < lookback * 2 + 3:
        return {"structure": "mixed", "pivotHighs": [], "pivotLows": []}
    high = df["high"].astype(float).values
    low  = df["low"].astype(float).values

    pivot_highs: list[float] = []
    pivot_lows:  list[float] = []

    for i in range(lookback, n - lookback):
        if all(high[i] >= high[i - j] for j in range(1, lookback + 1)) and \
           all(high[i] >= high[i + j] for j in range(1, lookback + 1)):
            pivot_highs.append(high[i])
        if all(low[i] <= low[i - j] for j in range(1, lookback + 1)) and \
           all(low[i] <= low[i + j] for j in range(1, lookback + 1)):
            pivot_lows.append(low[i])

    # 只取最近 4 个高点和低点做序列分析
    recent_h = pivot_highs[-4:] if len(pivot_highs) >= 2 else pivot_highs
    recent_l = pivot_lows[-4:]  if len(pivot_lows) >= 2 else pivot_lows

    hh_hl = False
    ll_lh = False

    if len(recent_h) >= 2 and len(recent_l) >= 2:
        higher_highs = all(recent_h[i] > recent_h[i-1] for i in range(1, len(recent_h)))
        higher_lows  = all(recent_l[i] > recent_l[i-1] for i in range(1, len(recent_l)))
        lower_highs  = all(recent_h[i] < recent_h[i-1] for i in range(1, len(recent_h)))
        lower_lows   = all(recent_l[i] < recent_l[i-1] for i in range(1, len(recent_l)))
        hh_hl = higher_highs and higher_lows
        ll_lh = lower_lows and lower_highs

    if hh_hl:
        structure = "HH_HL"
    elif ll_lh:
        structure = "LL_LH"
    else:
        structure = "mixed"

    return {
        "structure":  structure,
        "pivotHighs": [round(x, 4) for x in recent_h],
        "pivotLows":  [round(x, 4) for x in recent_l],
    }


def calc_ema_ribbon(df: pd.DataFrame) -> dict:
    """
    EMA缎带: EMA20/50/120 + 各自线性回归斜率。
    alignment: "bull"=多头排列, "bear"=空头排列, "tangled"=缠绕
    """
    c = df["close"].astype(float)
    n = len(df)
    ema20  = c.ewm(span=20,  adjust=False).mean()
    ema50  = c.ewm(span=50,  adjust=False).mean()
    ema120 = c.ewm(span=120, adjust=False).mean()

    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])
    e120 = float(ema120.iloc[-1])

    # 斜率: 用最近 5 根 EMA 的变化百分比
    def slope_pct(series: pd.Series, window: int = 5) -> float:
        if n < window + 1:
            return 0.0
        cur = float(series.iloc[-1])
        old = float(series.iloc[-window])
        return round((cur - old) / max(abs(old), 0.01) * 100, 4)

    s20  = slope_pct(ema20)
    s50  = slope_pct(ema50)
    s120 = slope_pct(ema120)

    if e20 > e50 > e120:
        alignment = "bull"
    elif e20 < e50 < e120:
        alignment = "bear"
    else:
        alignment = "tangled"

    return {
        "alignment": alignment,
        "ema20":     round(e20, 4),
        "ema50":     round(e50, 4),
        "ema120":    round(e120, 4),
        "slope20":   s20,
        "slope50":   s50,
        "slope120":  s120,
    }


def calc_market_regime(donchian: dict, pivot: dict, ema: dict) -> dict:
    """
    综合唐奇安通道、枢轴点结构、EMA缎带，给出趋势/震荡判定。
    评分 0~100: >=55 趋势，<55 震荡。
    """
    score = 0

    # ── 维度1a: 唐奇安通道宽度 (0-15分) ──
    # 宽度>3% 可能趋势展开；<1.5% 大概率震荡
    w = donchian["widthPct"]
    if w >= 4.0:
        score += 15
    elif w >= 2.5:
        score += 10
    elif w >= 1.5:
        score += 5

    # ── 维度1b: 价格在通道中的位置 (0-15分) ──
    # 趋势：贴近上轨(>0.85)或下轨(<0.15)
    pp = donchian["pricePos"]
    if pp > 0.85 or pp < 0.15:
        score += 15
    elif pp > 0.75 or pp < 0.25:
        score += 8

    # ── 维度1c: 通道是否走平 (0-5分) ──
    if donchian["flatRatio"] > 0.3:
        score += 5    # 通道在扩张 → 趋势信号

    # ── 维度2a: 枢轴点结构 (0-25分) ──
    if pivot["structure"] == "HH_HL":
        score += 25
    elif pivot["structure"] == "LL_LH":
        score += 25
    # mixed → 0分

    # ── 维度2b: EMA排列 (0-20分) ──
    if ema["alignment"] in ("bull", "bear"):
        score += 20
    # tangled → 0分

    # ── 维度2c: EMA斜率强度 (0-20分) ──
    # 中短期EMA斜率绝对值 > 0.1% 视为有力度
    abs_s20 = abs(ema["slope20"])
    abs_s50 = abs(ema["slope50"])
    abs_s120 = abs(ema["slope120"])
    if abs_s20 > 0.2 and abs_s50 > 0.1:
        score += 15
    elif abs_s20 > 0.1 or abs_s50 > 0.05:
        score += 8
    if abs_s120 > 0.05:
        score += 5

    score = min(score, 100)
    regime = "trending" if score >= 55 else "ranging"

    # 趋势方向
    if regime == "trending":
        if pivot["structure"] == "HH_HL" or ema["alignment"] == "bull":
            direction = "bullish"
        elif pivot["structure"] == "LL_LH" or ema["alignment"] == "bear":
            direction = "bearish"
        else:
            direction = "neutral"
    else:
        direction = "neutral"

    return {
        "regime":    regime,
        "direction": direction,
        "score":     score,
        "donchian":  donchian,
        "pivot":     pivot["structure"],
        "emaRibbon": ema,
    }


def calc_box_signal(close: float, donchian: dict, regime: dict,
                    tolerance_pct: float = 0.5) -> dict | None:
    """
    箱体策略信号：仅在震荡行情中，价格触及唐奇安通道上下沿时触发。
    上沿附近 → 做空；下沿附近 → 做多
    """
    if regime["regime"] != "ranging":
        return None

    upper = donchian["upper"]
    lower = donchian["lower"]
    basis = donchian["basis"]
    if upper <= lower or basis <= 0:
        return None

    dist_upper_pct = abs(close - upper) / upper * 100 if upper > 0 else 999
    dist_lower_pct = abs(close - lower) / lower * 100 if lower > 0 else 999

    # 触及上沿 → 做空（价格在上沿附近且接近或超过）
    if dist_upper_pct <= tolerance_pct and close >= basis:
        return {
            "type":          "short",
            "boundary":      "upper",
            "boundaryPrice": round(upper, 4),
            "distPct":       round(dist_upper_pct, 4),
            "boxUpper":      round(upper, 4),
            "boxLower":      round(lower, 4),
        }

    # 触及下沿 → 做多（价格在下沿附近且接近或低于）
    if dist_lower_pct <= tolerance_pct and close <= basis:
        return {
            "type":          "long",
            "boundary":      "lower",
            "boundaryPrice": round(lower, 4),
            "distPct":       round(dist_lower_pct, 4),
            "boxUpper":      round(upper, 4),
            "boxLower":      round(lower, 4),
        }

    return None


_BOUNCE_TOL = 0.5   # 回踩阈值：价格距目标均线最大距离（%）

def calc_breakout_signal(
    ma_30m: dict,
    macd_15m: dict,
    vol_15m: dict,
    oi_15m: dict,
) -> dict | None:
    """
    突破信号（多周期）- 三个必选条件（缺一不触发）：
      1. 30min MA 排列方向：收盘价在 MA20 和 MA60 上方（Upward）/ 下方（Downward）
         ★ 不要求均线斜率，早期突破时均线往往还未跟上价格
      2. 15min MACD 方向正确且快速扩口（金叉区做多，死叉区做空）
      3. 15min 成交量：环比放量 + （当前或前一根）高于近10根均量

    增仓（OI）为或有加分项：触发后额外标注 "+OI"，不影响信号触发。
    """
    ma_status = ma_30m.get("status")
    if ma_status not in ("Upward", "Downward"):
        return None

    is_long = (ma_status == "Upward")

    macd_ok = (macd_15m.get("sign") == ("positive" if is_long else "negative")
               and macd_15m.get("rapidExpanding", False))
    # 成交量：环比放量 + （当前量 OR 前一根量）高于均量
    vol_above = vol_15m.get("aboveVolMa", False) or vol_15m.get("prevAboveVolMa", False)
    vol_ok    = vol_15m.get("status") == "Surge" and vol_above

    if not (macd_ok and vol_ok):
        return None

    oi_ok = oi_15m.get("status") == "Increasing"
    return {
        "type":          "long" if is_long else "short",
        "maCumulative":  ma_30m.get("cumulative", 1),
        "macdSign":      macd_15m.get("sign"),
        "expansionRate": macd_15m.get("expansionRate", 1.0),
        "oiConfirmed":   oi_ok,
    }


def calc_pullback_signal(
    close: float,
    ma_30m: dict,
    macd_15m: dict,
    vol_15m: dict,
) -> dict | None:
    """
    回踩信号（多周期）：
      30min MA60 锚定多空方向 + 价格回踩 MA20/MA60 ±0.5%
      + 15min MACD 方向缩窄（已到位，压力/动能将释放）
      + 15min 放量确认

    做多回踩: close > MA60(30m) → 在 Upward 上行中回踩支撑
      - MA20 斜率 steep → 用 MA20 作支撑
      - MA20 斜率 gentle/flat → 用 MA60 作支撑
      - 15min MACD 死叉 + 缩窄（粘合）→ 卖压将尽
    做空反抽: close < MA60(30m) → 在 Downward 下行中反抽阻力
      - MA20 斜率 declining → 用 MA20 作阻力
      - 否则用 MA60 作阻力
      - 15min MACD 金叉 + 缩窄 → 买压将尽
    """
    ma20 = ma_30m.get("ma20")
    ma60 = ma_30m.get("ma60")
    slope_type = ma_30m.get("slopeType", "flat")

    if not ma20 or not ma60 or ma20 <= 0 or ma60 <= 0:
        return None

    dist_ma20 = abs(close - ma20) / ma20 * 100
    dist_ma60 = abs(close - ma60) / ma60 * 100

    slope20 = ma_30m.get("slope20Pct", 0.0)
    slope60 = ma_30m.get("slope60Pct", 0.0)

    # 方向由 30min MA60 锚定
    bullish = close > ma60   # 多头方向（价格在 MA60 上方）
    bearish = close < ma60   # 空头方向（价格在 MA60 下方）

    if not bullish and not bearish:
        return None

    # 斜率双重过滤：防止震荡期误触发
    # 做多回踩：MA20 和 MA60 斜率都 > 0（趋势明确向上）
    # 做空反抽：MA20 和 MA60 斜率都 < 0（趋势明确向下）
    if bullish and not (slope20 > 0 and slope60 > 0):
        return None
    if bearish and not (slope20 < 0 and slope60 < 0):
        return None

    # 成交量：环比放量 + （当前量 OR 前一根量）高于均量
    vol_above = vol_15m.get("aboveVolMa", False) or vol_15m.get("prevAboveVolMa", False)
    vol_ok    = vol_15m.get("status") == "Surge" and vol_above
    if not vol_ok:
        return None

    # 回踩方向精确判断阈值：允许收盘价在均线下方的最大容忍幅度
    # 做多回踩：价格从上方回落贴近均线，close ≥ support * (1 - 0.15%)
    #   即只允许极小幅度跌穿（收盘wick），防止把"从下方逼近"也误判为回踩
    # 做空反抽：价格从下方反弹贴近阻力，close ≤ resist  * (1 + 0.15%)，同理
    _APPROACH_TOL = 0.15  # 方向容忍：允许穿越均线的最大 %

    if bullish:
        # 多头回踩：MACD 15min 死叉 + 缩窄（粘合）→ 买入
        macd_ok = (macd_15m.get("sign") == "negative"
                   and not macd_15m.get("rapidExpanding", True))
        if not macd_ok:
            return None
        # 支撑均线选择
        if slope_type == "steep":
            target, support_val = "MA20", ma20
        else:  # gentle / flat / declining → 用 MA60
            target, support_val = "MA60", ma60

        dist_pct = (close - support_val) / support_val * 100   # 正=上方，负=下方

        # 价格必须从上方贴近：close ∈ [support*(1-0.15%), support*(1+0.5%)]
        # 上方 0.5% 以内说明正在回踩；下方 0.15% 是允许wick轻微跌穿
        if not (support_val * (1 - _APPROACH_TOL / 100) <= close <= support_val * (1 + _BOUNCE_TOL / 100)):
            return None

        return {
            "type":       "long",
            "target":     target,
            "support":    round(support_val, 2),
            "distPct":    round(abs(dist_pct), 3),   # 展示用，取绝对值
            "aboveMa":    dist_pct >= 0,             # True=价格仍在均线上方
            "slopeType":  slope_type,
            "ma20":       round(ma20, 2),
            "ma60":       round(ma60, 2),
        }
    else:
        # 空头反抽：MACD 15min 金叉 + 缩窄（粘合）→ 做空
        macd_ok = (macd_15m.get("sign") == "positive"
                   and not macd_15m.get("rapidExpanding", True))
        if not macd_ok:
            return None
        # 阻力均线选择
        if slope_type == "declining":
            target, resist_val = "MA20", ma20
        else:
            target, resist_val = "MA60", ma60

        dist_pct = (resist_val - close) / resist_val * 100   # 正=下方，负=上方

        # 价格必须从下方贴近：close ∈ [resist*(1-0.5%), resist*(1+0.15%)]
        # 下方 0.5% 以内说明正在反抽；上方 0.15% 是允许wick轻微突破
        if not (resist_val * (1 - _BOUNCE_TOL / 100) <= close <= resist_val * (1 + _APPROACH_TOL / 100)):
            return None

        return {
            "type":       "short",
            "target":     target,
            "support":    round(resist_val, 2),
            "distPct":    round(abs(dist_pct), 3),
            "aboveMa":    dist_pct <= 0,             # True=价格已经突破均线上方（轻微）
            "slopeType":  slope_type,
            "ma20":       round(ma20, 2),
            "ma60":       round(ma60, 2),
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
        return {"status": "Shrink", "cumulative": 0, "value": 0,
                "change": 0, "changePct": 0.0, "aboveVolMa": False, "volMa": 0}

    def st(i): return "Surge" if i >= 1 and v.iloc[i] > v.iloc[i - 1] else "Shrink"
    cur = st(n - 1)
    change = float(v.iloc[-1] - v.iloc[-2])
    pct = round(change / float(v.iloc[-2]) * 100, 1) if v.iloc[-2] else 0.0
    cnt = 1
    for i in range(n - 2, 0, -1):
        if st(i) == cur: cnt += 1
        else: break

    # 量MA10：以倒数第2~11根（排除当前可能未完结K线）计算均量
    # 用 prev（上一根已完结K线）对比均量，更能反映真实量能水平
    vol_ma_window = 10
    if n > vol_ma_window + 1:
        vol_ma = float(v.iloc[-(vol_ma_window + 2):-2].mean())   # 排除最新两根，取稳定均值
    elif n > 2:
        vol_ma = float(v.iloc[:-2].mean())
    else:
        vol_ma = float(v.iloc[-1])

    cur_vol  = float(v.iloc[-1])
    prev_vol = float(v.iloc[-2]) if n >= 2 else cur_vol

    # 当前量（可能未完结）或前一根已完结K线，任一高于均量即视为量能充足
    above_vol_ma      = cur_vol  > vol_ma if vol_ma > 0 else False
    prev_above_vol_ma = prev_vol > vol_ma if vol_ma > 0 else False

    return {
        "status":          cur,
        "cumulative":      cnt,
        "value":           int(cur_vol),
        "change":          int(change),
        "changePct":       pct,
        "aboveVolMa":      above_vol_ma,       # 当前量 > 均量（可能含未完结K线）
        "prevAboveVolMa":  prev_above_vol_ma,  # 前一根完结量 > 均量（更可靠）
        "volMa":           round(vol_ma, 0),
    }

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

# ── 单品种处理（双周期）─────────────────────────────────────
import time as _time_module

def process_symbol(args: tuple) -> dict | None:
    """
    30min K线 → MA方向（均线排列）
    15min K线 → MACD / 成交量 / 持仓量（触发层）
    若 15min 获取失败，自动降级到 30min 数据，确保系统可用。
    """
    symbol, category, code = args
    try:
        df_30m = fetch_klines(code)
        # 短暂间隔，避免对同一品种连续请求触发新浪限流
        _time_module.sleep(0.8)
        try:
            df_15m = fetch_klines_15m(code)
            tf_label = "15m"
        except Exception as e15:
            # 15min 不可用时降级：MACD/量/OI 使用 30min 数据
            print(f"  [WARN-15m] {symbol}({code}): {e15}，降级用30min", file=sys.stderr)
            df_15m = df_30m
            tf_label = "30m↓"

        last = float(df_30m["close"].iloc[-1])
        prev = float(df_30m["close"].iloc[-2])
        change = round((last - prev) / prev * 100, 2) if prev else 0.0

        ma_30m   = calc_ma(df_30m)
        macd_15m = calc_macd(df_15m)
        vol_15m  = calc_volume(df_15m)
        oi_15m   = calc_oi(df_15m)

        close = round(last, 2)
        atr      = calc_atr(df_30m)
        prev_low  = round(float(df_30m["low"].iloc[-2]),  4) if len(df_30m) >= 2 else close
        prev_high = round(float(df_30m["high"].iloc[-2]), 4) if len(df_30m) >= 2 else close

        # ── 市场状态判定（30min 数据）──
        donchian = calc_donchian(df_30m)
        pivot    = calc_pivot_structure(df_30m)
        ema_rib  = calc_ema_ribbon(df_30m)
        regime   = calc_market_regime(donchian, pivot, ema_rib)
        box_sig  = calc_box_signal(close, donchian, regime)

        return {
            "symbol":          symbol,
            "category":        category,
            "timeframe":       "30min",
            "triggerTf":       tf_label,
            "lastUpdate":      datetime.now().strftime("%H:%M:%S"),
            "price":           close,
            "change":          change,
            "atr":             atr,
            "prevLow":         prev_low,
            "prevHigh":        prev_high,
            "ma":              ma_30m,
            "macd":            macd_15m,
            "volume":          vol_15m,
            "openInterest":    oi_15m,
            "breakoutSignal":  calc_breakout_signal(ma_30m, macd_15m, vol_15m, oi_15m),
            "pullbackSignal":  calc_pullback_signal(close, ma_30m, macd_15m, vol_15m),
            "marketRegime":    regime,
            "boxSignal":       box_sig,
        }
    except Exception as e:
        print(f"  [SKIP] {symbol}({code}): {e}", file=sys.stderr)
        return None

def process_symbol_daily(args: tuple) -> dict | None:
    """处理单品种日K数据（用于复盘，MA方向+MACD均基于日K）。"""
    symbol, category, code = args
    try:
        df = fetch_klines_daily(code)
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        change = round((last - prev) / prev * 100, 2) if prev else 0.0
        ma_data   = calc_ma(df)
        macd_data = calc_macd(df)
        vol_data  = calc_volume(df)
        oi_data   = calc_oi(df)
        return {
            "symbol":          symbol,
            "category":        category,
            "timeframe":       "daily",
            "lastUpdate":      str(df["time"].iloc[-1]) if "time" in df.columns else "",
            "price":           round(last, 2),
            "change":          change,
            "ma":              ma_data,
            "macd":            macd_data,
            "volume":          vol_data,
            "openInterest":    oi_data,
            "breakoutSignal":  calc_breakout_signal(ma_data, macd_data, vol_data, oi_data),
            "pullbackSignal":  calc_pullback_signal(round(last, 2), ma_data, macd_data, vol_data),
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


def build_breakout_message(data: list[dict], bj_time: str) -> str | None:
    """
    突破信号推送格式：
    ─────────────────────────────────
    📊 突破信号 03-24 10:00
    ─────────────────────────────────
    🔴 做多：黄金 +0.8%  铜 +0.5%
    🟢 做空：原油 -1.2%
    📈 均线新突破：白银↗  棉花↘
    ─────────────────────────────────
    """
    longs  = [d for d in data if d.get("breakoutSignal") and d["breakoutSignal"]["type"] == "long"]
    shorts = [d for d in data if d.get("breakoutSignal") and d["breakoutSignal"]["type"] == "short"]
    ma_first_up = [d for d in data if d["ma"]["status"] == "Upward"   and d["ma"]["cumulative"] == 1]
    ma_first_dn = [d for d in data if d["ma"]["status"] == "Downward" and d["ma"]["cumulative"] == 1]

    if not any([longs, shorts, ma_first_up, ma_first_dn]):
        return None

    def fmt_item(d: dict, arrow: str) -> str:
        sig = d.get("breakoutSignal") or {}
        chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        oi  = " +OI" if sig.get("oiConfirmed") else ""
        return f"  {arrow}{d['symbol']} {chg}  MA×{d['ma']['cumulative']} 15mMACD×{d['macd']['cumulative']}{oi}"

    sep = "─" * 24
    lines = [f"<b>📊 突破信号</b>  {bj_time}",  sep]

    if longs:
        lines.append("🔴 <b>做多</b>（30m上行 · 15m金叉扩口 · 放量）")
        lines.extend(fmt_item(d, "▲") for d in longs)
    if shorts:
        if longs: lines.append("")
        lines.append("🟢 <b>做空</b>（30m下行 · 15m死叉扩口 · 放量）")
        lines.extend(fmt_item(d, "▼") for d in shorts)

    if ma_first_up or ma_first_dn:
        lines.append("")
        lines.append("📈 <b>均线首根变化</b>（新方向）")
        for d in ma_first_up:
            chg = f"+{d['change']:.2f}%"
            lines.append(f"  ↗ {d['symbol']} {chg} 上行第1根")
        for d in ma_first_dn:
            chg = f"{d['change']:.2f}%"
            lines.append(f"  ↘ {d['symbol']} {chg} 下行第1根")

    lines.append(sep)
    return "\n".join(lines)


def build_pullback_message(data: list[dict], bj_time: str) -> str | None:
    """
    回踩信号推送格式：
    ─────────────────────────────────
    🎯 回踩信号 03-24 10:00
    ─────────────────────────────────
    🔵 做多回踩：黄金 回踩MA20 距0.23%
    🟠 做空反抽：原油 反抽MA60 距0.18%
    ─────────────────────────────────
    """
    longs  = [d for d in data if d.get("pullbackSignal") and d["pullbackSignal"]["type"] == "long"]
    shorts = [d for d in data if d.get("pullbackSignal") and d["pullbackSignal"]["type"] == "short"]
    if not longs and not shorts:
        return None

    def fmt_item(d: dict, action: str) -> str:
        sig = d["pullbackSignal"]
        chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        slp = f"{d['ma']['slope20Pct']:+.3f}%"
        return (f"  {d['symbol']} {chg}"
                f"  {action}{sig['target']}={sig['support']}"
                f"  距{sig['distPct']:.3f}%"
                f"  斜率{slp}")

    sep = "─" * 24
    lines = [f"<b>🎯 回踩信号</b>  {bj_time}", sep]

    if longs:
        lines.append("🔵 <b>做多回踩</b>（30m MA60上方 · 价格贴近支撑 · 15m死叉缩窄 · 放量）")
        lines.extend(fmt_item(d, "↩") for d in longs)
    if shorts:
        if longs: lines.append("")
        lines.append("🟠 <b>做空反抽</b>（30m MA60下方 · 价格贴近阻力 · 15m金叉缩窄 · 放量）")
        lines.extend(fmt_item(d, "↪") for d in shorts)

    lines.append(sep)
    return "\n".join(lines)


def build_regime_message(data: list[dict], bj_time: str,
                         prev_map: dict[str, dict] | None = None) -> str | None:
    """
    推送规则：
    1. 只推「震荡 → 趋势」或「趋势 → 震荡」的品种（存量不推）
    2. 有箱体信号（触及通道边沿）时额外附加，仅供观测，不开单

    推送格式：
    ─────────────────────────────
    🔮 状态切换  03-30 14:00
    ─────────────────────────────
    📊 新入趋势：黄金↗(72分) 铜↗(68分)
    📦 新入震荡：原油(38分) 螺纹(41分)
    ─────────────────────────────
    📦 箱体观测（仅供参考）：
      ▲白糖 触下沿 距0.3%
      ▼螺纹 触上沿 距0.2%
    ─────────────────────────────
    """
    prev = prev_map or {}

    to_trending: list[dict] = []   # 震荡 → 趋势
    to_ranging:  list[dict] = []   # 趋势 → 震荡
    box_longs:   list[dict] = []
    box_shorts:  list[dict] = []

    for d in data:
        sym    = d["symbol"]
        cur_rg = d.get("marketRegime", {}).get("regime")
        if not cur_rg:
            continue

        # 箱体信号（独立收集，不受状态变化限制）
        if d.get("boxSignal"):
            if d["boxSignal"]["type"] == "long":
                box_longs.append(d)
            else:
                box_shorts.append(d)

        # 对比上一次 regime
        prev_rg = prev.get(sym, {}).get("marketRegime", {}).get("regime")
        if prev_rg is None or prev_rg == cur_rg:
            continue   # 无变化，跳过

        if cur_rg == "trending":
            to_trending.append(d)
        else:
            to_ranging.append(d)

    has_change = bool(to_trending or to_ranging)
    has_box    = bool(box_longs or box_shorts)

    if not has_change and not has_box:
        return None

    sep = "─" * 24
    lines: list[str] = []

    # ── 状态切换 ──────────────────────────────────────────────
    if has_change:
        lines += [f"<b>🔮 状态切换</b>  {bj_time}", sep]

        if to_trending:
            items = []
            for d in to_trending:
                dr    = d.get("marketRegime", {}).get("direction", "")
                arrow = "↗" if dr == "bullish" else "↘" if dr == "bearish" else "→"
                score = d.get("marketRegime", {}).get("score", "?")
                items.append(f"{d['symbol']}{arrow}({score}分)")
            lines.append(f"📊 <b>震荡→趋势</b>: {' '.join(items)}")
            lines.append("  💡 可关注突破策略（顺势）或回踩策略入场机会")

        if to_ranging:
            items = [
                f"{d['symbol']}({d.get('marketRegime',{}).get('score','?')}分)"
                for d in to_ranging
            ]
            lines.append(f"📦 <b>趋势→震荡</b>: {' '.join(items)}")
            lines.append("  💡 可关注突破策略或箱体边沿机会")

    # ── 箱体观测 ──────────────────────────────────────────────
    if has_box:
        if has_change:
            lines.append("")
        else:
            lines += [f"<b>📦 箱体观测</b>  {bj_time}", sep]

        lines.append("📦 <b>箱体边沿</b>（仅观测·不自动开单）")
        for d in box_longs:
            sig = d["boxSignal"]
            chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
            lines.append(f"  ▲{d['symbol']} {chg}"
                         f"  触下沿{sig['boundaryPrice']}  距{sig['distPct']:.2f}%"
                         f"  箱[{sig['boxLower']}~{sig['boxUpper']}]")
        for d in box_shorts:
            sig = d["boxSignal"]
            chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
            lines.append(f"  ▼{d['symbol']} {chg}"
                         f"  触上沿{sig['boundaryPrice']}  距{sig['distPct']:.2f}%"
                         f"  箱[{sig['boxLower']}~{sig['boxUpper']}]")

    lines.append(sep)
    return "\n".join(lines)


def _build_signal_message_legacy(data: list[dict], update_time: str) -> str | None:
    """Legacy: 已被 build_breakout_message 替代，保留函数体供内部兼容。"""
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

    # ── Step 1: 并发抓取 30min+15min 数据 ──
    # 每个 symbol 内顺序发出 30min→15min 两次请求（间隔 0.8s），
    # 4 个 worker 并发，整体约 4 个品种同时请求，不易触发新浪限流
    print(f"[{datetime.now(UTC).isoformat()}Z] Fetching {len(SYMBOLS)} symbols (30min+15min)...")
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(process_symbol, s): s for s in SYMBOLS}
        for fut in as_completed(futures):
            r = fut.result()
            if r: results.append(r)

    # ── Step 2: 抓取日K（复盘用，稍作等待让 API 冷却）──
    print("[DAILY] 开始抓取日K数据...")
    _time_module.sleep(2)
    daily_results_pre: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(process_symbol_daily, s): s for s in SYMBOLS}
        for fut in as_completed(futs):
            r = fut.result()
            if r: daily_results_pre.append(r)

    if not results:
        print("[FATAL] No data fetched — aborting write.", file=sys.stderr)
        sys.exit(1)

    # 合并上次数据中本次失败的品种（防止偶发故障清空）
    # prev_map 同时用于 regime 变化对比
    merged   = results
    prev_map: dict[str, dict] = {}
    if OUTPUT.exists():
        try:
            prev_raw = json.loads(OUTPUT.read_text("utf-8"))
            prev_map = {d["symbol"]: d for d in prev_raw.get("data", [])}
            new_set  = {d["symbol"] for d in results}
            kept = [v for k, v in prev_map.items() if k not in new_set]
            merged = results + kept
        except Exception:
            pass

    output = {
        "source":    "github-actions",
        "updatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data":      merged,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    print(f"✓ {len(results)}/{len(SYMBOLS)} symbols → {OUTPUT}")

    # ── 日K数据（已在 Step 1 完成，直接写文件）──
    daily_results = daily_results_pre
    if daily_results:
        daily_output = {
            "source":    "local-runner",
            "updatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "data":      daily_results,
        }
        OUTPUT_DAILY.write_text(json.dumps(daily_output, ensure_ascii=False, indent=2), "utf-8")
        print(f"✓ {len(daily_results)}/{len(SYMBOLS)} daily symbols → {OUTPUT_DAILY}")
    else:
        print("[DAILY] 无日K数据写入", file=sys.stderr)

    # ── Telegram 推送（仅30min+15min信号，日K不推）──
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
    messages = []
    bo_msg = build_breakout_message(merged, bj_time)
    if bo_msg:
        messages.append(bo_msg)
    pb_msg = build_pullback_message(merged, bj_time)
    if pb_msg:
        messages.append(pb_msg)
    rg_msg = build_regime_message(merged, bj_time, prev_map)
    if rg_msg:
        messages.append(rg_msg)
    if messages:
        tg_send_all("\n\n".join(messages))
    else:
        print("[TG] 无突破/回踩/状态切换信号，不推送")

    # ── 持仓管理（检查止损止盈 + 新建信号持仓）──
    _manage_positions(merged)

    # ── Git Push（仅本地/服务器运行时；GitHub Actions 由 workflow 自行处理）──
    if not os.environ.get("GITHUB_ACTIONS"):
        _git_push()


# ══════════════════════════════════════════════════════════════
# 持仓记录管理
# ══════════════════════════════════════════════════════════════

def _load_positions() -> list[dict]:
    """从 positions.json 读取历史持仓列表。"""
    if POSITIONS_FILE.exists():
        try:
            return json.loads(POSITIONS_FILE.read_text("utf-8")).get("positions", [])
        except Exception:
            return []
    return []


def _save_positions(positions: list[dict]) -> None:
    """将持仓列表写回 positions.json。"""
    data = {
        "updatedAt":  datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "openCount":  sum(1 for p in positions if p["status"] == "open"),
        "totalCount": len(positions),
        "positions":  positions,
    }
    POSITIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _can_open(positions: list[dict], symbol: str, direction: str,
              cooldown_min: int = 60) -> bool:
    """同一品种+方向在 cooldown_min 分钟内已有开仓则跳过（防止同一信号重复入场）。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    for p in positions:
        if p["symbol"] != symbol or p["direction"] != direction:
            continue
        try:
            from datetime import timedelta
            entry_dt = datetime.strptime(p["entryTime"], "%Y-%m-%d %H:%M")
            entry_dt = entry_dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            if (now - entry_dt) < timedelta(minutes=cooldown_min):
                return False
        except Exception:
            pass
    return True


def _open_position(symbol: str, direction: str, signal_type: str,
                   entry_price: float, atr: float,
                   prev_low: float, prev_high: float) -> dict:
    """
    创建新持仓记录。
    止损：做多 = 前K低点 - 1.5×ATR；做空 = 前K高点 + 1.5×ATR
    止盈：2:1 固定风险回报（TP距离 = 2 × 止损距离）
    """
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    uid     = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")

    if direction == "long":
        stop_loss = prev_low - 1.5 * atr
        risk      = entry_price - stop_loss
    else:
        stop_loss = prev_high + 1.5 * atr
        risk      = stop_loss - entry_price

    risk      = max(risk, 0.0001)   # 防止除零
    take_profit = (entry_price + 2 * risk) if direction == "long" else (entry_price - 2 * risk)

    return {
        "id":          f"{symbol}-{direction[0].upper()}-{uid}",
        "symbol":      symbol,
        "direction":   direction,            # "long" | "short"
        "signalType":  signal_type,          # "breakout" | "pullback"
        "entryTime":   bj_time,
        "entryPrice":  round(entry_price, 4),
        "atr":         round(atr, 4),
        "stopLoss":    round(stop_loss, 4),
        "takeProfit":  round(take_profit, 4),
        "riskDist":    round(risk, 4),
        "status":      "open",               # open | closed_sl | closed_tp
        "exitTime":    None,
        "exitPrice":   None,
        "pnl":         None,                 # 盈亏点数
        "pnlPct":      None,                 # 盈亏 %
    }


def _check_and_close(positions: list[dict],
                     current_map: dict[str, dict]) -> list[dict]:
    """轮查所有 open 持仓，若触及止损/止盈则关闭并记录。"""
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    for pos in positions:
        if pos["status"] != "open":
            continue
        sym_data = current_map.get(pos["symbol"])
        if not sym_data:
            continue
        cur_price = sym_data.get("price") or sym_data.get("close")
        if not cur_price:
            continue

        direction = pos["direction"]
        sl, tp    = pos["stopLoss"], pos["takeProfit"]
        entry     = pos["entryPrice"]

        if direction == "long":
            hit_sl = cur_price <= sl
            hit_tp = cur_price >= tp
        else:
            hit_sl = cur_price >= sl
            hit_tp = cur_price <= tp

        if hit_sl or hit_tp:
            exit_px     = sl if hit_sl else tp
            pos["status"]    = "closed_sl" if hit_sl else "closed_tp"
            pos["exitTime"]  = bj_time
            pos["exitPrice"] = round(exit_px, 4)
            pnl_pts          = (exit_px - entry) if direction == "long" else (entry - exit_px)
            pos["pnl"]       = round(pnl_pts, 4)
            pos["pnlPct"]    = round(pnl_pts / entry * 100, 4) if entry else None
            print(f"[POS] {pos['id']} → {pos['status']} @ {exit_px}")
    return positions


def _manage_positions(merged: list[dict]) -> None:
    """
    主入口：
    1. 检查现有 open 持仓是否触及 SL/TP
    2. 扫描当次信号，新建持仓记录
    3. 写回 positions.json
    """
    positions   = _load_positions()
    current_map = {d["symbol"]: d for d in merged}

    # ── Step A: 检查现有持仓 ──────────────────────────────────
    positions = _check_and_close(positions, current_map)

    # ── Step B: 根据当次信号新建持仓 ──────────────────────────
    for d in merged:
        symbol     = d["symbol"]
        close      = d.get("price") or d.get("close")
        atr        = d.get("atr", 0.0)
        prev_low   = d.get("prevLow",  close or 0.0)
        prev_high  = d.get("prevHigh", close or 0.0)

        if not close or not atr:
            continue

        for sig_key, sig_type in [("breakoutSignal", "breakout"), ("pullbackSignal", "pullback")]:
            sig = d.get(sig_key)
            if not sig:
                continue
            direction = sig.get("type", "long")   # "long" | "short"
            if _can_open(positions, symbol, direction):
                pos = _open_position(symbol, direction, sig_type,
                                     close, atr, prev_low, prev_high)
                positions.append(pos)
                print(f"[POS] 新建 {pos['id']}  SL={pos['stopLoss']}  TP={pos['takeProfit']}")

    _save_positions(positions)
    print(f"[POS] 持仓更新完成，共 {len(positions)} 笔，"
          f"其中 open={sum(1 for p in positions if p['status']=='open')}")


def _git_push():
    """将更新后的 data.json / data_daily.json 推送到 GitHub，供 Cloudflare Pages 部署。"""
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent

    def run(cmd: list[str]) -> tuple[int, str]:
        r = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        return r.returncode, out

    data_files = [
        "futures-monitor/public/data.json",
        "futures-monitor/public/data_daily.json",
        "futures-monitor/public/positions.json",
    ]

    code, out = run(["git", "add"] + data_files)
    if code != 0:
        print(f"[GIT] git add 失败: {out}", file=sys.stderr)
        return

    code, out = run(["git", "diff", "--staged", "--quiet"])
    if code == 0:
        print("[GIT] 数据无变化，跳过 commit/push")
        return

    code, out = run(["git", "commit", "-m", "chore: update futures data [auto]"])
    if code != 0:
        print(f"[GIT] git commit 失败: {out}", file=sys.stderr)
        return
    print(f"[GIT] commit: {out}")

    # fetch + merge -X ours 防止远端有其他提交导致 push 被拒
    run(["git", "fetch", "origin", "main"])
    run(["git", "merge", "origin/main", "--no-edit", "-X", "ours"])

    code, out = run(["git", "push", "origin", "main"])
    if code != 0:
        print(f"[GIT] git push 失败: {out}", file=sys.stderr)
    else:
        print(f"[GIT] push 成功 → GitHub / Cloudflare Pages")


if __name__ == "__main__":
    main()

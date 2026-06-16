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
#   回踩信号: 30min MA60锚定多空 + 价格回踩MA20/MA60 + 15min MACD方向扩口 + 15min放量
#
# 输出: futures-monitor/public/data.json       (30min+15min)
#       futures-monitor/public/data_daily.json (日K 复盘)
# ============================================================

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timezone
from pathlib import Path

# Python 3.9+ 标准库 zoneinfo；Python 3.8 需要 backports.zoneinfo
try:
    from zoneinfo import ZoneInfo  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except ModuleNotFoundError:
        print("[FATAL] 缺少时区依赖：Python<3.9 请安装 backports.zoneinfo：pip install backports.zoneinfo")
        raise

# Python 3.11+ 有 datetime.UTC；为兼容 3.8/3.9/3.10 统一使用 timezone.utc
UTC = timezone.utc

import numpy as np
import pandas as pd

# ── H-005 MTF 回踩状态机 ──
try:
    from mtf_pullback import evaluate as eval_mtf_pullback
except ImportError:
    eval_mtf_pullback = None  # 模块缺失时不崩溃，回踩信号返回 None

try:
    import akshare as ak
except ImportError:
    print("[FATAL] akshare 未安装，请执行: pip install akshare pandas numpy")
    sys.exit(1)

# 中国期货交易时段（北京时间）
# 窗口比实际交易时间各宽约 5 分钟，确保 :25/:55 的 cron 也能通过守卫
def _get_trading_windows() -> list:
    th = _p()["trading_hours"]
    return [
        (time(*map(int, th["morning"][0].split(":"))),  time(*map(int, th["morning"][1].split(":")))),
        (time(*map(int, th["afternoon"][0].split(":"))), time(*map(int, th["afternoon"][1].split(":")))),
        (time(*map(int, th["night"][0].split(":"))),     time(*map(int, th["night"][1].split(":")))),
    ]

def is_trading_time() -> bool:
    tz = ZoneInfo("Asia/Shanghai")
    now_bj = datetime.now(tz)
    if now_bj.weekday() >= 5:
        return False
    t = now_bj.time()
    for s, e in _get_trading_windows():
        if s <= t <= e:
            return True
    return False

ROOT            = Path(__file__).parent.parent
OUTPUT          = ROOT / "futures-monitor" / "public" / "data.json"
OUTPUT_DAILY    = ROOT / "futures-monitor" / "public" / "data_daily.json"
POSITIONS_FILE  = ROOT / "futures-monitor" / "public" / "positions.json"
PENDING_BREAKOUTS_FILE = ROOT / "futures-monitor" / "public" / "pending_breakouts.json"
PARAMS_FILE     = ROOT / "strategy_params.json"

# ── 参数加载 ─────────────────────────────────────────────────
_params_cache: dict | None = None


def _load_params() -> dict:
    """加载策略参数配置。首次调用从 strategy_params.json 读取并缓存。
    若文件不存在或格式错误，回退到内置默认值（与 v1.0 完全一致）。
    返回的 dict 可直接用点分键访问，如 PARAMS["pullback"]["bounce_tol_pct"]。
    """
    global _params_cache
    if _params_cache is not None:
        return _params_cache
    try:
        if PARAMS_FILE.exists():
            _params_cache = json.loads(PARAMS_FILE.read_text("utf-8"))
            print(f"[PARAMS] 已加载: {PARAMS_FILE} (v{_params_cache.get('version','?')})")
            return _params_cache
    except Exception as e:
        print(f"[PARAMS] 加载失败 ({e})，使用内置默认值", file=sys.stderr)
    _params_cache = {
        "version": "1.0",
        "pullback": {"bounce_tol_pct": 1.5, "atr_factor": 0.8, "adaptive_min_pct": 0.30,
                      "approach_tol_pct": 0.30, "min_slope20_pct": 0.05, "min_slope60_pct": 0.02,
                      "ma_entanglement_threshold_pct": 0.15},
        "breakout": {"body_atr_ratio_min": 1.0, "donchian_tolerance_pct": 0.1,
                      "kd_cooling": {"long_k_max": 80, "long_d_max": 80, "short_k_min": 20, "short_d_min": 20}},
        "macd": {"fast": 12, "slow": 26, "signal": 9, "expansion_rate_min": 1.2, "expansion_lookback_bars": 10},
        "volume": {"surge_ma_mult": 1.5, "ma_window": 10},
        "risk": {"min_risk_pct": 0.15, "min_price_gap_pct": 0.01, "stop_loss_atr_entry": 2,
                  "stop_loss_atr_prev_bar": 1, "take_profit_risk_ratio": 2, "breakeven_r": 1,
                  "trailing_activate_r": 1.5, "trailing_atr_mult": 1.2},
        "position": {"cooldown_minutes": 60, "max_wait_bars": 12},
        "trading_hours": {"morning": ["08:50", "11:40"], "afternoon": ["13:20", "15:10"],
                           "night": ["20:50", "23:40"], "daily_k_window": ["23:00", "23:15"]},
        "fetch": {"max_workers": 4, "kline_rows": 200, "request_delay_seconds": 0.8, "max_retries": 3},
    }
    return _params_cache


def _p() -> dict:
    """快捷访问：_p()['pullback']['bounce_tol_pct']"""
    return _load_params()


def _mtf_cfg() -> dict:
    """加载 H-005 MTF回踩参数（从 strategy_params.json 的 mtf_pullback 节）。"""
    params = _load_params()
    raw = params.get("mtf_pullback", {})
    # 映射到 mtf_pullback.evaluate() 所需的 CONFIG 格式
    return {
        "zone_tol_atr30":   raw.get("zone_tol_atr30", 0.3),
        "zone_tol_atr_d":   raw.get("zone_tol_atr_d", 0.5),
        "overheat_atr_d":   raw.get("overheat_atr_d", 2.0),
        "max_retrace":      raw.get("max_retrace", 0.618),
        "shrink_ratio":     raw.get("shrink_ratio", 0.8),
        "max_oi_increase":  raw.get("max_oi_increase", 3.0),
        "min_pb_bars":      raw.get("min_pb_bars", 2),
        "max_pb_bars":      raw.get("max_pb_bars", 20),
        "trigger_wait":     raw.get("trigger_wait", 8),
        "stop_buffer_atr":  raw.get("stop_buffer_atr", 0.5),
        "swing_lookback":   raw.get("swing_lookback", 5),
        "use_tet":          raw.get("use_tet", True),
        "ats_min":          raw.get("ats_min", 0.30),
        "ei_washout":       raw.get("ei_washout", 0.30),
        "ti_entry":         raw.get("ti_entry", 0.50),
        "trend_score_version": raw.get("trend_score_version", 2),
        "tet_variant":      raw.get("tet_variant", "V1"),
        "fib_zones":        raw.get("fib_zones", True),
        "sweep_trigger":    raw.get("sweep_trigger", True),
        "sweep_pierce_atr": raw.get("sweep_pierce_atr", 0.1),
    }


_daily_map_cache: dict | None = None
_daily_map_loaded: bool = False


def _load_daily_map() -> dict[str, dict] | None:
    """加载 data_daily.json 中的品种→复盘数据映射（缓存）。"""
    global _daily_map_cache, _daily_map_loaded
    if _daily_map_loaded:
        return _daily_map_cache
    _daily_map_loaded = True
    if OUTPUT_DAILY.exists():
        try:
            raw = json.loads(OUTPUT_DAILY.read_text("utf-8"))
            _daily_map_cache = {d["symbol"]: d for d in raw.get("data", [])}
        except Exception:
            _daily_map_cache = None
    return _daily_map_cache


def _eval_pullback(symbol: str, df_daily, df_30m,
                   macd_15m: dict, vol_15m: dict,
                   daily_entry: dict | None = None) -> dict | None:
    """
    H-005 MTF回踩状态机评估。
    若 df_daily 不可用或模块缺失，返回 None（不崩溃）。
    """
    if eval_mtf_pullback is None:
        return None
    if df_daily is None or df_30m is None:
        return None
    try:
        cfg = _mtf_cfg()
        return eval_mtf_pullback(symbol, df_daily, df_30m,
                                 macd_15m, vol_15m,
                                 daily_entry=daily_entry, cfg=cfg)
    except Exception as e:
        print(f"  [MTF-PB] {symbol}: 评估异常 {e}", file=sys.stderr)
        return None


# ── 品种定义 ─────────────────────────────────────────────────
SYMBOLS = [
    ("黄金",     "贵金属", "AU0"),
    ("白银",     "贵金属", "AG0"),
    ("铜",       "有色",   "CU0"),
    ("铝",       "有色",   "AL0"),
    ("镍",       "有色",   "NI0"),
    ("锡",       "有色",   "SN0"),
    ("碳酸锂",   "有色",   "LC0"),
    ("氧化铝",   "有色",   "AO0"),
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
def fetch_klines(code: str, rows: int | None = None, _retries: int | None = None) -> pd.DataFrame:
    if rows is None: rows = _p()["fetch"]["kline_rows"]
    if _retries is None: _retries = _p()["fetch"]["max_retries"]
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

def fetch_klines_15m(code: str, rows: int | None = None, _retries: int | None = None) -> pd.DataFrame:
    if rows is None: rows = _p()["fetch"]["kline_rows"]
    if _retries is None: _retries = _p()["fetch"]["max_retries"]
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

def fetch_klines_daily(code: str, rows: int | None = None) -> pd.DataFrame:
    if rows is None: rows = _p()["fetch"]["kline_rows"]
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


def calc_kdj(df: pd.DataFrame, period: int = 9) -> dict:
    """KDJ 指标，用于突破后等待动能冷却的二次确认。"""
    n = len(df)
    if n < period:
        return {"k": 50.0, "d": 50.0, "j": 50.0}
    low_n = df["low"].astype(float).rolling(period).min()
    high_n = df["high"].astype(float).rolling(period).max()
    close = df["close"].astype(float)
    denom = (high_n - low_n).replace(0, np.nan)
    rsv = (close - low_n) / denom * 100
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    j = 3 * k - 2 * d

    def val(s: pd.Series, default: float = 50.0) -> float:
        x = float(s.iloc[-1])
        return round(x, 4) if not np.isnan(x) else default

    return {"k": val(k), "d": val(d), "j": val(j)}


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


def _tf_state(ma: dict | None, macd: dict | None, close: float | None) -> int:
    """
    单周期状态判定：
      1 = Bull: close > MA20 > MA60  且  MACD > 0
     -1 = Bear: close < MA20 < MA60  且  MACD < 0
      0 = Neutral
    """
    if not ma or not macd or close is None:
        return 0
    ma20 = ma.get("ma20")
    ma60 = ma.get("ma60")
    sign = macd.get("sign")
    if not ma20 or not ma60 or not sign:
        return 0
    if close > ma20 and ma20 > ma60 and sign == "positive":
        return 1
    if close < ma20 and ma20 < ma60 and sign == "negative":
        return -1
    return 0


# ── MTF 状态矩阵：15m × 30m × 日线 → 操作建议 + 信号门控 ──
# 每周期: 1=Bull  -1=Bear  0=Neutral
# 原则: 日线定战略方向, 30m定战术偏向, 15m定入场时机
# allowBreakout/allowPullback 控制信号是否可入场
_ACTION_MATRIX: dict[tuple, tuple[str, str, str, bool, bool]] = {
    # 日线 Bull — 战略做多
    (1,  1,  1):  ("trending", "bullish", "顺势持有 / 趋势加仓",           True,  True),
    (-1, 1,  1):  ("trending", "bullish", "止盈部分，不轻易反手空",         False, False),
    (1,  0,  1):  ("trending", "bullish", "可重新试多",                    True,  True),
    (1,  -1, 1):  ("trending", "bullish", "最重要的小仓试多结构",           False, True),
    (-1, -1, 1):  ("ranging",  "neutral", "观察是否升级为4h转空，或15m转多",  False, False),
    (-1, 0,  1):  ("ranging",  "neutral", "先观察，不急着追空",              False, False),
    # 日线 Bear — 战略做空
    (-1, -1, -1): ("trending", "bearish", "顺势做空 / 持空",               True,  True),
    (1,  -1, -1): ("trending", "bearish", "短线反弹，趋势偏空",              False, False),
    (1,  1,  -1): ("trending", "bearish", "可逐步加仓",                    False, True),
    (1,  0,  -1): ("ranging",  "neutral", "观察是否升级为1h转多",            False, False),
    (-1, 1,  -1): ("trending", "bearish", "可考虑反手空",                   True,  True),
}


def calc_mtf_regime(ma_15m: dict, ma_30m: dict, ma_daily: dict | None,
                    macd_15m: dict, macd_30m: dict, macd_daily: dict | None,
                    close_15m: float, close_30m: float,
                    close_daily: float | None = None) -> dict:
    """
    MTF 状态矩阵：15min + 30min + 日线。
    每周期独立判定 Bull/Bear/Neutral，查表得操作建议。
    日线不可用时降级为 2TF 模式（以 30m 为锚）。
    """
    s15 = _tf_state(ma_15m, macd_15m, close_15m)
    s30 = _tf_state(ma_30m, macd_30m, close_30m)
    sd  = _tf_state(ma_daily, macd_daily, close_daily) if ma_daily else 0

    key = (s15, s30, sd)
    if key in _ACTION_MATRIX:
        regime, direction, action, allow_bo, allow_pb = _ACTION_MATRIX[key]
    elif sd == 1:
        regime, direction, action, allow_bo, allow_pb = "trending", "bullish", "偏多观望", True, False
    elif sd == -1:
        regime, direction, action, allow_bo, allow_pb = "trending", "bearish", "偏空观望", True, False
    elif s30 == 1:
        regime, direction, action, allow_bo, allow_pb = "ranging", "neutral", "30m偏多，等日线确认", False, False
    elif s30 == -1:
        regime, direction, action, allow_bo, allow_pb = "ranging", "neutral", "30m偏空，等日线确认", False, False
    else:
        regime, direction, action, allow_bo, allow_pb = "ranging", "neutral", "等待方向明确", False, False

    bull_count = (1 if s15 == 1 else 0) + (1 if s30 == 1 else 0) + (1 if sd == 1 else 0)
    bear_count = (1 if s15 == -1 else 0) + (1 if s30 == -1 else 0) + (1 if sd == -1 else 0)

    return {
        "regime":          regime,
        "direction":       direction,
        "action":          action,
        "allowBreakout":   allow_bo,
        "allowPullback":   allow_pb,
        "bullCount":       bull_count,
        "bearCount":       bear_count,
        "states":          {"15m": s15, "30m": s30, "daily": sd},
    }


# ── 旧版 regime 判定（已弃用，保留供参考）─────────────────────
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


# ── 结构位突破过滤器（H-010 突破战术增强）──────────────
_STRUCT_BREAKOUT  = True   # False = 一行回滚到旧逻辑
_LEVEL_LOOKBACK   = 30     # 前期关键位 = 近30根(不含当前K)最高/最低
_EXT_ATR_MAX      = 1.0    # 收盘距突破位最大延伸(×ATR)，超出=追高不开
_LEVEL_FRESH_TOL  = 0.001  # 新鲜度容差：前收须仍在位内 ±0.1%

_params_module = _load_params()  # 模块加载时初始化
_BOUNCE_TOL          = _params_module["pullback"]["bounce_tol_pct"]          # 回踩阈值上限
_PULLBACK_ATR_FACTOR = _params_module["pullback"]["atr_factor"]               # 回踩ATR自适应因子
_MIN_RISK_PCT        = _params_module["risk"]["min_risk_pct"]                 # 最小初始风险
_MIN_PRICE_GAP_PCT   = _params_module["risk"]["min_price_gap_pct"]            # 止损最小保护距离


def _adaptive_bounce_tol(close: float, atr: float = 0.0) -> float:
    """回踩右侧确认距离：不超过固定 1.5%，同时按当前 ATR 收缩。"""
    if close > 0 and atr > 0:
        atr_pct = atr / close * 100
        return max(_p()["pullback"]["adaptive_min_pct"], min(_BOUNCE_TOL, _PULLBACK_ATR_FACTOR * atr_pct))
    return _BOUNCE_TOL


def calc_struct_levels(df: pd.DataFrame, lookback: int = _LEVEL_LOOKBACK) -> dict:
    """前期关键位：近 lookback 根（不含当前K）的最高/最低 + 前收（新鲜度判断用）。"""
    n = len(df)
    if n < lookback + 2:
        return {"up": None, "dn": None, "prevClose": None}
    return {
        "up":        float(df["high"].astype(float).iloc[-(lookback + 1):-1].max()),
        "dn":        float(df["low"].astype(float).iloc[-(lookback + 1):-1].min()),
        "prevClose": float(df["close"].iloc[-2]),
    }


def calc_breakout_signal(
    ma_30m: dict,
    macd_15m: dict,
    vol_15m: dict,
    oi_15m: dict,
    regime: dict | None = None,
    donchian: dict | None = None,
    close: float = 0.0,
    trigger_open: float = 0.0,
    atr: float = 0.0,
    levels: dict | None = None,
) -> dict | None:
    """
    突破信号（多周期）- 四个必选条件（缺一不触发）：
      1. 30min MA 排列方向：收盘价在 MA20 和 MA60 上方（Upward）/ 下方（Downward）
      2. 15min MACD 方向正确且快速扩口（金叉区做多，死叉区做空）
      3. 15min 成交量：环比放量（或量超均量1.5倍）且高于近10根均量
      4. 触发K线实体足够大：abs(close - open) / ATR > 1
         → 抓起爆点，实体太小说明方向不够果断，容易折返

    震荡行情附加条件（regime=ranging 时必须同时满足）：
      5. 价格必须已突破唐奇安通道边沿（做多须穿越上轨，做空须穿越下轨）

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

    # ── 触发K线实体校验：abs(close - open) / ATR > 1 ────────────
    # 抓起爆点要求方向性足够强，实体小于 1 ATR 说明力度不足
    if trigger_open > 0 and atr > 0 and close > 0:
        body = abs(close - trigger_open)
        if body / atr <= _p()["breakout"]["body_atr_ratio_min"]:
            return None

    # ── 震荡行情附加：必须同时突破箱体边沿 ─────────────────────
    # 趋势行情中均线排列已经说明价格有持续性，箱体条件可豁免
    # 震荡行情中仅突破均线极易快速折返，需要箱体上/下沿也被穿越才开单
    box_breakout = False   # 是否突破了箱体（仅在 ranging 时强制要求）
    if regime is not None and regime.get("regime") == "ranging" and donchian and close > 0:
        upper = donchian.get("upper", 0)
        lower = donchian.get("lower", 0)
        basis = donchian.get("basis", 0)
        if upper > lower > 0:
            if is_long:
                # 做多：价格须已站上箱体上沿（允许 donchian_tolerance_pct% 容差，防止恰好卡边）
                _dtol = _p()["breakout"]["donchian_tolerance_pct"] / 100
                box_breakout = close >= upper * (1 - _dtol)
            else:
                # 做空：价格须已跌破箱体下沿
                box_breakout = close <= lower * (1 + _dtol)
        if not box_breakout:
            return None   # 震荡中未突破箱体，不触发

    # ── 结构位锚定：所有 regime 一律生效 ──
    level_val = None
    ext_atr = None
    if _STRUCT_BREAKOUT and levels and levels.get("up") and levels.get("dn") and atr > 0:
        prev_c = levels.get("prevClose") or 0.0
        if is_long:
            level_val = levels["up"]
            fresh = prev_c <= level_val * (1 + _LEVEL_FRESH_TOL)
            broke = close > level_val
            ext = close - level_val
        else:
            level_val = levels["dn"]
            fresh = prev_c >= level_val * (1 - _LEVEL_FRESH_TOL)
            broke = close < level_val
            ext = level_val - close
        if not (broke and fresh):
            return None      # 非新鲜结构突破 → 只是均线上方动量点火，不开
        if ext > _EXT_ATR_MAX * atr:
            return None      # 延伸过远=追高 → 转回踩接力
        ext_atr = round(ext / atr, 3)

    oi_ok = oi_15m.get("status") == "Increasing"
    return {
        "type":          "long" if is_long else "short",
        "maCumulative":  ma_30m.get("cumulative", 1),
        "macdSign":      macd_15m.get("sign"),
        "expansionRate": macd_15m.get("expansionRate", 1.0),
        "oiConfirmed":   oi_ok,
        "boxBreakout":   box_breakout,   # True=震荡行情下同步突破了箱体
        "level":  round(level_val, 4) if level_val else None,
        "extAtr": ext_atr,
    }


def calc_pullback_signal(
    close: float,
    ma_30m: dict,
    macd_15m: dict,
    vol_15m: dict,
    regime: dict | None = None,
    donchian: dict | None = None,
    atr: float = 0.0,
    oi_15m: dict | None = None,
) -> dict | None:
    """
    回踩信号（右侧入场）：
      价格回踩 MA20/MA60 支撑后反弹，等第二波启动确认再入场。
      30min MA60 锚定多空方向 + 15min MACD 回归趋势方向且扩口 + 放量确认

    过滤层：
      ① 市场状态必须为趋势（regime=trending），震荡期不触发
      ② MA20/MA60 必须保持多空排列，纠缠时不触发
      ③ 斜率最小阈值：slope20 ≥ 0.05% / slope60 ≥ 0.02%，走平均线不触发

    做多回踩（右侧）: close > MA60(30m) → 回踩支撑后，MACD 金叉 + 扩口 → 确认第二波上涨启动
      - 价格在支撑均线上方 0~min(1.5%, 0.8ATR)（已反弹区域），或轻微跌穿 0.3%（wick）
    做空反抽（右侧）: close < MA60(30m) → 反抽阻力后，MACD 死叉 + 扩口 → 确认第二波下跌启动
      - 价格在阻力均线下方 0~min(1.5%, 0.8ATR)（已回落区域），或轻微突破 0.3%（wick）
      - 空头额外要求趋势方向 bearish、价格位于唐奇安中轴下方、并伴随增仓确认
    """
    ma20 = ma_30m.get("ma20")
    ma60 = ma_30m.get("ma60")
    slope_type = ma_30m.get("slopeType", "flat")

    if not ma20 or not ma60 or ma20 <= 0 or ma60 <= 0:
        return None

    slope20 = ma_30m.get("slope20Pct", 0.0)
    slope60 = ma_30m.get("slope60Pct", 0.0)

    # ── 过滤①：市场状态必须为趋势 ───────────────────────────────
    # 震荡市中价格触碰均线是正常来回，不构成有效回踩
    if regime is not None and regime.get("regime") == "ranging":
        return None

    # 方向由 30min MA60 锚定
    bullish = close > ma60   # 多头方向（价格在 MA60 上方）
    bearish = close < ma60   # 空头方向（价格在 MA60 下方）

    if not bullish and not bearish:
        return None

    # ── 过滤②：MA多空排列校验 + 纠缠检测 ───────────────────────
    # 多头回踩：MA20 必须在 MA60 上方（标准多头排列）
    # 空头反抽：MA20 必须在 MA60 下方（标准空头排列）
    # 纠缠：MA20 与 MA60 间距 < 0.15% → 均线交织，趋势不明，跳过
    ma_gap_pct = abs(ma20 - ma60) / ma60 * 100
    if ma_gap_pct < _p()["pullback"]["ma_entanglement_threshold_pct"]:
        return None   # 均线纠缠，不触发
    if bullish and ma20 <= ma60:
        return None   # 价格在MA60上方但均线倒排，趋势不可信
    if bearish and ma20 >= ma60:
        return None   # 价格在MA60下方但均线倒排，趋势不可信

    # ── 过滤③：斜率最小阈值 ─────────────────────────────────────
    # slope20/60 是3根K线内的累计变化%，< 0.05% 视为走平
    _MIN_SLOPE20 = _p()["pullback"]["min_slope20_pct"]
    _MIN_SLOPE60 = _p()["pullback"]["min_slope60_pct"]
    if bullish and not (slope20 >= _MIN_SLOPE20 and slope60 >= _MIN_SLOPE60):
        return None
    if bearish and not (slope20 <= -_MIN_SLOPE20 and slope60 <= -_MIN_SLOPE60):
        return None

    # 成交量：环比放量 + （当前量 OR 前一根量）高于均量
    vol_above = vol_15m.get("aboveVolMa", False) or vol_15m.get("prevAboveVolMa", False)
    vol_ok    = vol_15m.get("status") == "Surge" and vol_above
    if not vol_ok:
        return None

    # 右侧入场阈值：价格已从支撑/阻力反弹，允许在均线附近 ±幅度内触发
    # 做多：close 在 support 下方最多 0.3%（仅允许wick轻微跌穿）~ 上方最多 1.5%（已反弹区域）
    # 做空：close 在 resist  上方最多 0.3%（仅允许wick轻微突破）~ 下方最多 1.5%（已回落区域）
    _APPROACH_TOL = _p()["pullback"]["approach_tol_pct"]
    bounce_tol = _adaptive_bounce_tol(close, atr)

    if bullish:
        # 多头回踩右侧入场：价格已从支撑反弹，MACD 回归金叉区 + 快速扩口 → 第二波启动确认
        macd_ok = (macd_15m.get("sign") == "positive"
                   and macd_15m.get("rapidExpanding", False))
        if not macd_ok:
            return None
        # 支撑均线选择
        if slope_type == "steep":
            target, support_val = "MA20", ma20
        else:  # gentle / flat / declining → 用 MA60
            target, support_val = "MA60", ma60

        dist_pct = (close - support_val) / support_val * 100   # 正=上方，负=下方

        # 价格在支撑均线附近：close ∈ [support*(1-0.3%), support*(1+bounce_tol)]
        # 下方 0.3%：允许wick轻微跌穿支撑后反弹
        # 上方 bounce_tol：右侧确认时价格已反弹，过远则放弃追入
        if not (support_val * (1 - _APPROACH_TOL / 100) <= close <= support_val * (1 + bounce_tol / 100)):
            return None

        return {
            "type":       "long",
            "target":     target,
            "support":    round(support_val, 2),
            "distPct":    round(abs(dist_pct), 3),
            "aboveMa":    dist_pct >= 0,
            "slopeType":  slope_type,
            "ma20":       round(ma20, 2),
            "ma60":       round(ma60, 2),
            "bounceTol":  round(bounce_tol, 3),
        }
    else:
        # 空头反抽右侧入场：价格已从阻力回落，MACD 回归死叉区 + 快速扩口 → 第二波下跌确认
        macd_ok = (macd_15m.get("sign") == "negative"
                   and macd_15m.get("rapidExpanding", False))
        if not macd_ok:
            return None

        # 空头回踩历史表现弱，额外要求大结构与资金方向同时支持下行。
        if regime is not None and regime.get("direction") != "bearish":
            return None
        if donchian and donchian.get("basis", 0) > 0 and close >= donchian["basis"]:
            return None
        if oi_15m is not None and oi_15m.get("status") != "Increasing":
            return None

        # 阻力均线选择
        if slope_type == "declining":
            target, resist_val = "MA20", ma20
        else:
            target, resist_val = "MA60", ma60

        dist_pct = (resist_val - close) / resist_val * 100   # 正=下方，负=上方

        # 价格在阻力均线附近：close ∈ [resist*(1-bounce_tol%), resist*(1+0.3%)]
        # 下方 bounce_tol：右侧确认时价格已回落，过远则放弃追空
        # 上方 0.3%：允许wick轻微突破阻力后回落
        if not (resist_val * (1 - bounce_tol / 100) <= close <= resist_val * (1 + _APPROACH_TOL / 100)):
            return None

        return {
            "type":       "short",
            "target":     target,
            "support":    round(resist_val, 2),
            "distPct":    round(abs(dist_pct), 3),
            "aboveMa":    dist_pct <= 0,
            "slopeType":  slope_type,
            "ma20":       round(ma20, 2),
            "ma60":       round(ma60, 2),
            "bounceTol":  round(bounce_tol, 3),
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
    LOOKBACK = _p()["macd"]["expansion_lookback_bars"]
    hist_abs = hist.abs()
    start = max(1, n - LOOKBACK)
    deltas = [float(hist_abs.iloc[i]) - float(hist_abs.iloc[i - 1]) for i in range(start, n)]

    current_delta = deltas[-1] if deltas else 0.0
    prev_delta    = deltas[-2] if len(deltas) >= 2 else 0.0   # 前一根棒的扩口幅度
    prev_deltas = [abs(d) for d in deltas[:-1]]
    avg_abs_delta = float(np.mean(prev_deltas)) if prev_deltas else 0.0

    # 当前棒扩口：expansionRate > 1.2（略高于 1.0 基线，排除刚刚勉强触发的弱信号）
    _EXPANSION_RATE_MIN = _p()["macd"]["expansion_rate_min"]
    rapid_expanding = bool(
        current_delta > 0
        and (avg_abs_delta == 0 or current_delta > avg_abs_delta * _EXPANSION_RATE_MIN)
    )
    expansion_rate = round(current_delta / avg_abs_delta, 2) if avg_abs_delta > 0 else (1.0 if current_delta > 0 else 0.0)

    return {
        "sign":           sign,
        "rapidExpanding": rapid_expanding,
        "expansionRate":  expansion_rate,
        "cumulative":     cnt,
        "prevExpanding":  bool(prev_delta > 0),   # 前一根是否也在扩口（供外部调试/前端展示）
    }

def calc_volume(df: pd.DataFrame) -> dict:
    v = df["volume"]
    n = len(df)
    if n < 2:
        return {"status": "Shrink", "cumulative": 0, "value": 0,
                "change": 0, "changePct": 0.0, "aboveVolMa": False, "volMa": 0}

    # 量MA10：以倒数第2~11根（排除当前可能未完结K线）计算均量
    # 先算均量，供放量判断函数使用
    vol_ma_window = _p()["volume"]["ma_window"]
    if n > vol_ma_window + 1:
        vol_ma = float(v.iloc[-(vol_ma_window + 2):-2].mean())   # 排除最新两根，取稳定均值
    elif n > 2:
        vol_ma = float(v.iloc[:-2].mean())
    else:
        vol_ma = float(v.iloc[-1])

    # 放量判断：环比放量（v[i] > v[i-1]），或绝对量超过均量 1.5 倍（开盘段/放量启动也能被捕捉）
    # 场景：开盘第2棒可能量略少于第1棒，但绝对量远高于历史均量，仍应视为放量
    _SURGE_MA_MULT = _p()["volume"]["surge_ma_mult"]
    def st(i):
        env_surge = i >= 1 and v.iloc[i] > v.iloc[i - 1]          # 环比放量
        abs_surge = vol_ma > 0 and v.iloc[i] > vol_ma * _SURGE_MA_MULT
        return "Surge" if (env_surge or abs_surge) else "Shrink"

    cur = st(n - 1)
    change = float(v.iloc[-1] - v.iloc[-2])
    pct = round(change / float(v.iloc[-2]) * 100, 1) if v.iloc[-2] else 0.0
    cnt = 1
    for i in range(n - 2, 0, -1):
        if st(i) == cur: cnt += 1
        else: break

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
        _time_module.sleep(_p()["fetch"]["request_delay_seconds"])
        try:
            df_15m = fetch_klines_15m(code)
            tf_label = "15m"
        except Exception as e15:
            # 15min 不可用时降级：MACD/量/OI 使用 30min 数据
            print(f"  [WARN-15m] {symbol}({code}): {e15}，降级用30min", file=sys.stderr)
            df_15m = df_30m
            tf_label = "30m↓"

        # ── H-005: 抓日K供 MTF 回踩状态机使用 ──
        df_daily = None
        try:
            _time_module.sleep(_p()["fetch"]["request_delay_seconds"])
            df_daily = fetch_klines_daily(code)
        except Exception as e_d:
            print(f"  [WARN-D] {symbol}({code}): 日K抓取失败: {e_d}", file=sys.stderr)

        # ── 日线复盘数据（regime / direction 等）──
        daily_entry = None
        _daily_map = _load_daily_map()
        if _daily_map:
            daily_entry = _daily_map.get(symbol)

        last = float(df_30m["close"].iloc[-1])
        prev = float(df_30m["close"].iloc[-2])
        change = round((last - prev) / prev * 100, 2) if prev else 0.0

        ma_30m   = calc_ma(df_30m)
        ma_15m   = calc_ma(df_15m)
        macd_15m = calc_macd(df_15m)
        macd_30m = calc_macd(df_30m)
        vol_15m  = calc_volume(df_15m)
        oi_15m   = calc_oi(df_15m)

        close = round(last, 2)
        atr        = calc_atr(df_30m)
        kdj_30m    = calc_kdj(df_30m)
        bar_time   = str(df_30m["time"].iloc[-1])
        cur_open   = round(float(df_30m["open"].iloc[-1]),  4)
        cur_low    = round(float(df_30m["low"].iloc[-1]),   4)
        cur_high   = round(float(df_30m["high"].iloc[-1]),  4)
        prev_low   = round(float(df_30m["low"].iloc[-2]),   4) if len(df_30m) >= 2 else close
        prev_high  = round(float(df_30m["high"].iloc[-2]),  4) if len(df_30m) >= 2 else close
        prev_close = round(float(df_30m["close"].iloc[-2]), 4) if len(df_30m) >= 2 else close

        # ── 市场状态判定（多周期共振：15m + 30m + 日线）──
        donchian = calc_donchian(df_30m)

        # 日线 MA/MACD 数据
        daily_ma = daily_entry.get("ma") if daily_entry else None
        daily_macd = daily_entry.get("macd") if daily_entry else None
        daily_close_val = daily_entry.get("price") if daily_entry else None

        regime   = calc_mtf_regime(ma_15m, ma_30m, daily_ma,
                                   macd_15m, macd_30m, daily_macd,
                                   close_15m=round(float(df_15m["close"].iloc[-1]), 2),
                                   close_30m=close,
                                   close_daily=daily_close_val)
        box_sig  = calc_box_signal(close, donchian, regime)

        return {
            "symbol":          symbol,
            "category":        category,
            "timeframe":       "30min",
            "triggerTf":       tf_label,
            "lastUpdate":      datetime.now().strftime("%H:%M:%S"),
            "barTime":         bar_time,
            "price":           close,
            "change":          change,
            "atr":             atr,
            "curOpen":         cur_open,
            "curLow":          cur_low,
            "curHigh":         cur_high,
            "prevLow":         prev_low,
            "prevHigh":        prev_high,
            "prevClose":       prev_close,
            "kdj30":           kdj_30m,
            "ma":              ma_30m,
            "macd":            macd_15m,
            "volume":          vol_15m,
            "openInterest":    oi_15m,
            "breakoutSignal":  calc_breakout_signal(ma_30m, macd_15m, vol_15m, oi_15m,
                                                     regime=regime, donchian=donchian, close=close,
                                                     trigger_open=round(float(df_15m["open"].iloc[-1]), 2),
                                                     atr=atr,
                                                     levels=calc_struct_levels(df_30m)),
            "pullbackSignal":  _eval_pullback(symbol, df_daily, df_30m, macd_15m, vol_15m,
                                           daily_entry=daily_entry),
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
            "breakoutSignal":  calc_breakout_signal(ma_data, macd_data, vol_data, oi_data),  # daily 无 regime/donchian 数据，沿用原逻辑
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
    """突破/接近信号推送。有信号推信号，没信号推接近。"""
    longs  = [d for d in data if d.get("breakoutSignal") and d["breakoutSignal"]["type"] == "long"]
    shorts = [d for d in data if d.get("breakoutSignal") and d["breakoutSignal"]["type"] == "short"]

    # 接近信号：3/4满足（缺增仓），且该方向没有真实突破信号
    def _near(d, is_long):
        if d.get("breakoutSignal"): return False
        ma = d.get("ma", {})
        macd = d.get("macd", {})
        vol = d.get("volume", {})
        return (
            ma.get("status") == ("Upward" if is_long else "Downward")
            and macd.get("sign") == ("positive" if is_long else "negative")
            and macd.get("rapidExpanding")
            and vol.get("status") == "Surge"
        )
    near_long  = [d for d in data if _near(d, True)] if not longs else []
    near_short = [d for d in data if _near(d, False)] if not shorts else []

    if not any([longs, shorts, near_long, near_short]):
        return None

    def fmt_bo(d: dict, arrow: str) -> str:
        sig = d.get("breakoutSignal") or {}
        chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        oi  = " +OI" if sig.get("oiConfirmed") else ""
        lv  = sig.get("level")
        ext = sig.get("extAtr")
        extra = f" lv{lv} ext{ext}" if lv else ""
        return f"  {arrow}{d['symbol']} {chg} MA×{d['ma']['cumulative']} MACD{sig.get('expansionRate',1):.1f}x{oi}{extra}"

    def fmt_near(d: dict, arrow: str) -> str:
        chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        return f"  {arrow}{d['symbol']} {chg} MA×{d['ma']['cumulative']} MACD{d['macd']['expansionRate']:.1f}x 待确认"

    sep = "─" * 24
    lines = [f"<b>⚡ 突破信号</b>  {bj_time}", sep]

    if longs:
        lines.append("🔴 <b>做多</b> → pending等KD冷却")
        lines.extend(fmt_bo(d, "▲") for d in longs)
    if shorts:
        if longs: lines.append("")
        lines.append("🟢 <b>做空</b> → pending等KD冷却")
        lines.extend(fmt_bo(d, "▼") for d in shorts)

    if near_long or near_short:
        if longs or shorts: lines.append("")
        lines.append("🟡 <b>接近信号</b>（体量/结构未过）")
        lines.extend(fmt_near(d, "▲") for d in near_long)
        lines.extend(fmt_near(d, "▼") for d in near_short)

    if longs or shorts:
        lines.append("")
        lines.append("💡 等30m KD冷却确认（最多12K）")
    lines.append(sep)
    return "\n".join(lines)


def build_pullback_message(data: list[dict], bj_time: str) -> str | None:
    """
    H-005 MTF回踩信号推送格式：
    ─────────────────────────────────
    🎯 MTF回踩 06-11 14:30
    ─────────────────────────────────
    🔵 黄金 做多 sweep@pivot_retest entry=620.5 SL=618.2 risk=0.37%
       pbBars=3 retrace=0.382 volRatio=0.45 TET✓(ATS=0.42 EI=-0.35 TI=0.77)
    🟠 螺纹 做空 structure_macd@daily_ema20 entry=3850 SL=3875 risk=0.65%
       pbBars=8 retrace=0.500 volRatio=0.62 TET✓(ATS=-0.38 EI=0.42 TI=-0.80)
    ─────────────────────────────────
    """
    longs  = [d for d in data if d.get("pullbackSignal") and d["pullbackSignal"].get("type") == "long"]
    shorts = [d for d in data if d.get("pullbackSignal") and d["pullbackSignal"].get("type") == "short"]
    if not longs and not shorts:
        return None

    def fmt_item(d: dict) -> str:
        sig = d["pullbackSignal"]
        chg = f"+{d['change']:.2f}%" if d["change"] >= 0 else f"{d['change']:.2f}%"
        q = sig.get("quality", {})
        pb_info = f"pbBars={q.get('pbBars','?')} retrace={q.get('retrace','?')} volRatio={q.get('volRatio','?')}"
        tet = sig.get("tet")
        tet_str = ""
        if tet:
            tet_str = (f" TET✓(ATS={tet.get('ats',0):.2f} "
                       f"EI={tet.get('eiNow',0):.2f} TI={tet.get('ti',0):.2f})")
        return (f"  {d['symbol']} {chg}\n"
                f"     {sig['trigger']}@{sig['zone']} "
                f"entry={sig['entry']} SL={sig['stopLoss']} risk={sig['riskPct']}%\n"
                f"     {pb_info}{tet_str}")

    sep = "─" * 32
    lines = [f"<b>🎯 MTF回踩</b>  {bj_time}", sep]

    if longs:
        lines.append("🔵 <b>做多回踩</b>（日线EMA多头排列 · 30min结构回踩 · 扫损/结构触发）")
        lines.extend(fmt_item(d) for d in longs)
    if shorts:
        if longs: lines.append("")
        lines.append("🟠 <b>做空反抽</b>（日线EMA空头排列 · 30min结构反抽 · 扫损/结构触发）")
        lines.extend(fmt_item(d) for d in shorts)

    lines.append(sep)
    return "\n".join(lines)


def build_trend_ready_message(data: list[dict], bj_time: str,
                              prev_map: dict[str, dict] | None = None) -> str | None:
    """
    趋势就绪推送：仅推送「震荡 → 趋势」的品种（存量不推，趋势→震荡不推）。
    """
    prev = prev_map or {}
    just_trending: list[dict] = []

    for d in data:
        sym = d["symbol"]
        cur_rg = d.get("marketRegime", {}).get("regime")
        if cur_rg != "trending":
            continue
        prev_rg = prev.get(sym, {}).get("marketRegime", {}).get("regime")
        if prev_rg == "trending":
            continue   # 已经是趋势，不推
        just_trending.append(d)

    if not just_trending:
        return None

    items = []
    for d in just_trending:
        mr = d.get("marketRegime", {})
        dr = mr.get("direction", "")
        arrow = "↗" if dr == "bullish" else "↘" if dr == "bearish" else "→"
        items.append(f"{d['symbol']}{arrow}({mr.get('bullCount',0)}/{mr.get('bearCount',0)})")

    sep = "─" * 24
    lines = [f"<b>🔮 趋势就绪</b>  {bj_time}", sep,
             " ".join(items),
             "💡 突破策略关注入场机会",
             sep]
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


def build_position_opened_message(new_positions: list[dict], bj_time: str) -> str | None:
    """
    开仓确认推送格式：
    ─────────────────────────────────
    ✅ 已开仓 03-24 14:30
    ─────────────────────────────────
    🔴 突破确认做多：黄金 3028.50
    🟢 回踩做空：    原油 612.30
    ─────────────────────────────────
    """
    if not new_positions:
        return None

    def fmt_pos(pos: dict) -> str:
        direction   = pos.get("direction", "long")
        arrow       = "▲" if direction == "long" else "▼"
        signal_type = pos.get("signalType", "")
        sig_label   = "突破确认" if signal_type == "breakout" else "回踩"
        action      = "做多" if direction == "long" else "做空"
        entry       = pos.get("entryPrice", 0)
        sl          = pos.get("stopLoss", 0)
        # 突破确认额外信息
        bc = pos.get("breakoutConfirm")
        wait_str = f"  等{bc['barsWaited']}K" if bc else ""
        return f"  {arrow}{pos['symbol']} {action} @{entry:.2f}  SL{sl:.2f}{wait_str}"

    sep = "─" * 24
    lines: list[str] = [f"<b>✅ 已开仓</b>  {bj_time}", sep]

    longs  = [p for p in new_positions if p.get("direction") == "long"]
    shorts = [p for p in new_positions if p.get("direction") == "short"]

    if longs:
        lines.extend(fmt_pos(p) for p in longs)
    if shorts:
        lines.extend(fmt_pos(p) for p in shorts)

    lines.append(sep)
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
    with ThreadPoolExecutor(max_workers=_p()["fetch"]["max_workers"]) as pool:
        futures = {pool.submit(process_symbol, s): s for s in SYMBOLS}
        for fut in as_completed(futures):
            r = fut.result()
            if r: results.append(r)

    # ── Step 2: 抓取日K（仅在收盘后23:00-23:15执行，其余时间跳过，避免API挂死产生僵尸）──
    _now_bj_daily = datetime.now(ZoneInfo("Asia/Shanghai"))
    _dk = _p()["trading_hours"]["daily_k_window"]
    _daily_window   = (time(*map(int, _dk[0].split(":"))), time(*map(int, _dk[1].split(":"))))
    _do_daily       = (_daily_window[0] <= _now_bj_daily.time() <= _daily_window[1])
    daily_results_pre: list[dict] = []
    if _do_daily:
        print("[DAILY] 收盘窗口(23:00-23:15)，开始抓取日K数据...")
        _time_module.sleep(2)
        with ThreadPoolExecutor(max_workers=_p()["fetch"]["max_workers"]) as pool:
            futs = {pool.submit(process_symbol_daily, s): s for s in SYMBOLS}
            for fut in as_completed(futs):
                r = fut.result()
                if r: daily_results_pre.append(r)
    else:
        print(f"[DAILY] 非收盘窗口({_now_bj_daily.strftime('%H:%M')})，跳过日K抓取")

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

    # ── 持仓管理（检查止损止盈 + 新建信号持仓，返回本轮新开仓）──
    new_opened = _manage_positions(merged)

    # ── Telegram 推送 ──
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
    messages = []

    bo_msg = build_breakout_message(merged, bj_time)
    if bo_msg:
        messages.append(bo_msg)
    pb_msg = build_pullback_message(merged, bj_time)
    if pb_msg:
        messages.append(pb_msg)
    ok_msg = build_position_opened_message(new_opened, bj_time)
    if ok_msg:
        messages.append(ok_msg)
    tr_msg = build_trend_ready_message(merged, bj_time, prev_map)
    if tr_msg:
        messages.append(tr_msg)
    if messages:
        tg_send_all("\n\n".join(messages))
    else:
        print("[TG] 无信号，不推送")

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


def _load_pending_breakouts() -> list[dict]:
    """读取等待 KD 冷却确认的突破事件。"""
    if PENDING_BREAKOUTS_FILE.exists():
        try:
            return json.loads(PENDING_BREAKOUTS_FILE.read_text("utf-8")).get("pending", [])
        except Exception:
            return []
    return []


def _save_pending_breakouts(pending: list[dict]) -> None:
    pending.sort(key=lambda x: x.get("breakoutTime", ""))
    data = {
        "updatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "count": len(pending),
        "pending": pending,
    }
    PENDING_BREAKOUTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _has_pending_breakout(pending: list[dict], symbol: str, direction: str) -> bool:
    return any(
        p.get("symbol") == symbol and p.get("direction") == direction
        for p in pending
    )


def _make_pending_breakout(d: dict, direction: str) -> dict | None:
    """把原始突破信号转成等待 30m KD 冷却的事件。"""
    symbol = d.get("symbol")
    close = d.get("price") or d.get("close")
    open_ = d.get("curOpen")
    bar_time = d.get("barTime") or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    if not symbol or not close or not open_:
        return None

    trigger_level = (float(open_) + float(close)) / 2
    return {
        "id": f"{symbol}-{direction}-{bar_time}",
        "symbol": symbol,
        "direction": direction,
        "breakoutTime": bar_time,
        "breakoutOpen": round(float(open_), 4),
        "breakoutClose": round(float(close), 4),
        "triggerLevel": round(trigger_level, 4),  # 突破K实体50%位置
        "lastCheckedBarTime": bar_time,
        "barsWaited": 0,
        "maxWaitBars": _p()["position"]["max_wait_bars"],
    }


def _confirm_pending_breakout(pending: dict, d: dict) -> bool:
    """30m KD 冷却 + 价格守住突破K实体50%位置。"""
    close = d.get("price") or d.get("close")
    kdj = d.get("kdj30") or {}
    if not close or not kdj:
        return False
    k = kdj.get("k", 50.0)
    d_val = kdj.get("d", 50.0)
    level = pending.get("triggerLevel")
    if level is None:
        return False
    _kd = _p()["breakout"]["kd_cooling"]
    if pending.get("direction") == "long":
        return k < _kd["long_k_max"] and d_val < _kd["long_d_max"] and close >= level
    return k > _kd["short_k_min"] and d_val > _kd["short_d_min"] and close <= level


def _dedup_positions(positions: list[dict]) -> list[dict]:
    """
    去除两类重复持仓：
    1. 同入场价重复（同一批量信号的副本）：(symbol, direction, entryPrice) 相同 → 保留最早入场那笔
    2. 同批次平仓重复（ghost rebuild 副本）：(symbol, direction, exitPrice, exitTime) 相同 → 保留最早入场那笔
    """
    removed: set[str] = set()

    seen_entry: dict = {}
    for p in sorted(positions, key=lambda x: x.get("entryTime", "")):
        key = (p["symbol"], p["direction"], p["entryPrice"])
        if key not in seen_entry:
            seen_entry[key] = p["id"]
        else:
            removed.add(p["id"])

    seen_exit: dict = {}
    for p in sorted(positions, key=lambda x: x.get("entryTime", "")):
        if p["id"] in removed:
            continue
        ep, et = p.get("exitPrice"), p.get("exitTime")
        if ep is not None and et is not None:
            key = (p["symbol"], p["direction"], ep, et)
            if key not in seen_exit:
                seen_exit[key] = p["id"]
            else:
                removed.add(p["id"])

    if removed:
        print(f"[POS] 自动去重：移除 {len(removed)} 笔重复持仓")
    return [p for p in positions if p["id"] not in removed]


def _save_positions(positions: list[dict]) -> None:
    """将持仓列表写回 positions.json（自动去重后写入）。"""
    positions = _dedup_positions(positions)
    positions.sort(key=lambda x: x.get("entryTime", ""))
    data = {
        "updatedAt":  datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "openCount":  sum(1 for p in positions if p["status"] == "open"),
        "totalCount": len(positions),
        "positions":  positions,
    }
    POSITIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _can_open(positions: list[dict], symbol: str, direction: str,
              cooldown_min: int | None = None) -> bool:
    if cooldown_min is None:
        cooldown_min = _p()["position"]["cooldown_minutes"]
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
                   prev_low: float, prev_high: float,
                   signal_stop: float | None = None) -> dict | None:
    """
    创建新持仓记录。
    止损：默认做多 = max(入场价-2ATR, 前K低点-1ATR)；做空 = min(入场价+2ATR, 前K高点+1ATR)
          若 signal_stop 传入（回踩信号的结构止损），优先使用 signal_stop。
    风险保护：止损必须位于入场价正确一侧，且初始风险不得过小。
    止盈目标：2:1 风险回报。
    """
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    uid     = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")

    _sl_entry = _p()["risk"]["stop_loss_atr_entry"]
    _sl_prev  = _p()["risk"]["stop_loss_atr_prev_bar"]

    if direction == "long":
        if signal_stop is not None and signal_stop < entry_price:
            stop_loss = signal_stop
        else:
            # 两种方案取较大值（价格较高 = 止损距离较小 = 更保守地控制风险）
            # 方案1: 入场价 - stop_loss_atr_entry×ATR
            # 方案2: 前一根K线低点 - stop_loss_atr_prev_bar×ATR
            stop_loss = max(entry_price - _sl_entry * atr, prev_low - _sl_prev * atr)
        max_sl = entry_price * (1 - _MIN_PRICE_GAP_PCT / 100)
        stop_loss = min(stop_loss, max_sl)
        risk      = entry_price - stop_loss
    else:
        if signal_stop is not None and signal_stop > entry_price:
            stop_loss = signal_stop
        else:
            # 两种方案取较小值（价格较低 = 止损距离较小 = 更保守地控制风险）
            # 方案1: 入场价 + stop_loss_atr_entry×ATR
            # 方案2: 前一根K线高点 + stop_loss_atr_prev_bar×ATR
            stop_loss = min(entry_price + _sl_entry * atr, prev_high + _sl_prev * atr)
        min_sl = entry_price * (1 + _MIN_PRICE_GAP_PCT / 100)
        stop_loss = max(stop_loss, min_sl)
        risk      = stop_loss - entry_price

    min_risk = entry_price * _MIN_RISK_PCT / 100
    if risk < min_risk:
        print(f"[POS] 跳过 {symbol} {direction} {signal_type}: "
              f"初始风险过小 risk={risk:.4f} < {min_risk:.4f}")
        return None

    _rr = _p()["risk"]["take_profit_risk_ratio"]
    take_profit = (entry_price + _rr * risk) if direction == "long" else (entry_price - _rr * risk)

    return {
        "id":          f"{symbol}-{direction[0].upper()}-{uid}",
        "symbol":      symbol,
        "direction":   direction,            # "long" | "short"
        "signalType":  signal_type,          # "breakout" | "pullback"
        "entryTime":   bj_time,
        "entryPrice":  round(entry_price, 4),
        "atr":         round(atr, 4),
        "stopLoss":    round(stop_loss, 4),
        "initialStopLoss": round(stop_loss, 4),
        "takeProfit":  round(take_profit, 4),
        "riskDist":    round(risk, 4),
        "initialRiskDist": round(risk, 4),
        "trailingActive": False,
        "breakEvenMoved": False,
        "exitReason":  None,                 # initial_sl | fixed_tp | trailing_sl
        "status":      "open",               # open | closed_sl | closed_tp
        "exitTime":    None,
        "exitPrice":   None,
        "pnl":         None,                 # 盈亏点数
        "pnlPct":      None,                 # 盈亏 %
    }


def _check_and_close(positions: list[dict],
                     current_map: dict[str, dict]) -> list[dict]:
    """
    轮查所有 open 持仓：
    - 初始止损：触及 stopLoss 则止损出
    - 移动止损（Trailing Stop）：
        1R 后先把止损推到入场价附近保护本金
        激活条件: 做多 price >= entry + 2R  /  做空 price <= entry - 2R
        激活后每根K线更新止损 = prev_close ± 2×ATR（只向有利方向移动）
        触发移动止损出场记录为 closed_tp，并用 exitReason 标记 trailing_sl
    """
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    for pos in positions:
        if pos["status"] != "open":
            continue
        sym_data = current_map.get(pos["symbol"])
        if not sym_data:
            continue

        cur_price  = sym_data.get("price") or sym_data.get("close")
        if not cur_price:
            continue

        # 用当前K线最高/最低价判断是否触及止损（更接近实盘）
        cur_low    = sym_data.get("curLow",  cur_price)
        cur_high   = sym_data.get("curHigh", cur_price)
        cur_atr    = sym_data.get("atr") or pos.get("atr", 0)
        prev_close = sym_data.get("prevClose") or cur_price  # 前一根K线收盘价
        direction  = pos["direction"]
        entry      = pos["entryPrice"]
        sl         = pos["stopLoss"]
        trailing   = pos.get("trailingActive", False)  # 是否已进入移动止损模式
        risk_ref   = pos.get("initialRiskDist") or pos.get("riskDist") or abs(entry - sl)
        if risk_ref <= 0:
            continue

        if direction == "long":
            # ── 1R 先推保本，2R 后启用移动止损 ─────────────────
            if not pos.get("breakEvenMoved") and cur_high >= entry + _p()["risk"]["breakeven_r"] * risk_ref:
                new_sl = round(entry, 4)
                if new_sl > sl:
                    pos["stopLoss"] = new_sl
                    sl = new_sl
                pos["breakEvenMoved"] = True

            if not trailing and cur_high >= entry + _p()["risk"]["trailing_activate_r"] * risk_ref:
                trailing = True
                pos["trailingActive"] = True
                pos["trailingActivatedAt"] = bj_time
                print(f"[POS] {pos['id']} 移动止损激活 @ high={cur_high:.4f} "
                      f"(entry+{_p()['risk']['trailing_activate_r']}R={entry + _p()['risk']['trailing_activate_r'] * risk_ref:.4f})")

            # ── 移动止损更新（每根K线往上推进）──────────────
            if trailing and cur_atr > 0:
                new_sl = round(prev_close - _p()["risk"]["trailing_atr_mult"] * cur_atr, 4)
                if new_sl > sl:   # 只向上移动，绝不下调
                    pos["stopLoss"] = new_sl
                    sl = new_sl

            # ── 出场判断（用最低价触碰止损）─────────────────
            hit_sl = cur_low <= sl
            # 正常运行时 ATR > 0，移动止损负责止盈。hit_tp 仅在 ATR 缺失时作为兜底安全网
            hit_tp = (not trailing) and cur_atr <= 0 and cur_high >= pos["takeProfit"]

        else:  # short
            if not pos.get("breakEvenMoved") and cur_low <= entry - _p()["risk"]["breakeven_r"] * risk_ref:
                new_sl = round(entry, 4)
                if new_sl < sl:
                    pos["stopLoss"] = new_sl
                    sl = new_sl
                pos["breakEvenMoved"] = True

            if not trailing and cur_low <= entry - _p()["risk"]["trailing_activate_r"] * risk_ref:
                trailing = True
                pos["trailingActive"] = True
                pos["trailingActivatedAt"] = bj_time
                print(f"[POS] {pos['id']} 移动止损激活 @ low={cur_low:.4f} "
                      f"(entry-{_p()['risk']['trailing_activate_r']}R={entry - _p()['risk']['trailing_activate_r'] * risk_ref:.4f})")

            if trailing and cur_atr > 0:
                new_sl = round(prev_close + _p()["risk"]["trailing_atr_mult"] * cur_atr, 4)
                if new_sl < sl:   # 只向下移动
                    pos["stopLoss"] = new_sl
                    sl = new_sl

            # ── 出场判断（用最高价触碰止损）─────────────────
            hit_sl = cur_high >= sl
            # 正常运行时 ATR > 0，移动止损负责止盈。hit_tp 仅在 ATR 缺失时作为兜底安全网
            hit_tp = (not trailing) and cur_atr <= 0 and cur_low <= pos["takeProfit"]

        if hit_sl or hit_tp:
            if hit_tp:
                exit_px        = pos["takeProfit"] if hit_tp else sl
                pos["status"]  = "closed_tp"
                pos["exitReason"] = "fixed_tp"
            elif hit_sl and trailing:
                exit_px        = sl
                pos["status"]  = "closed_tp"
                pos["exitReason"] = "trailing_sl"
            elif hit_sl and pos.get("breakEvenMoved"):
                exit_px        = sl
                pos["status"]  = "closed_sl"
                pos["exitReason"] = "break_even_sl"
            else:
                exit_px        = sl
                pos["status"]  = "closed_sl"
                pos["exitReason"] = "initial_sl"

            pos["exitTime"]  = bj_time
            pos["exitPrice"] = round(exit_px, 4)
            pnl_pts          = (exit_px - entry) if direction == "long" else (entry - exit_px)
            pos["pnl"]       = round(pnl_pts, 4)
            pos["pnlPct"]    = round(pnl_pts / entry * 100, 4) if entry else None
            print(f"[POS] {pos['id']} → {pos['status']} @ {exit_px:.4f}  "
                  f"{'(trailing)' if trailing else ''}")
    return positions


def _manage_positions(merged: list[dict]) -> list[dict]:
    """
    主入口：
    1. 检查现有 open 持仓是否触及 SL/TP
    2. 突破信号先进入 pending，等待 30m KD 冷却后二次确认
    3. 回踩信号仍即时新建持仓
    3. 写回 positions.json

    返回: 本轮新开仓的持仓记录列表（供推送使用）
    """
    positions   = _load_positions()
    pending     = _load_pending_breakouts()
    current_map = {d["symbol"]: d for d in merged}
    new_opened: list[dict] = []   # 本轮新开仓（供推送）

    # ── Step A: 检查现有持仓 ──────────────────────────────────
    positions = _check_and_close(positions, current_map)

    # ── Step B: 检查等待中的突破事件，只在首次确认时开一笔 ────────
    next_pending: list[dict] = []
    for p in pending:
        symbol = p.get("symbol")
        direction = p.get("direction", "long")
        d = current_map.get(symbol)
        if not d:
            next_pending.append(p)
            continue

        bar_time = d.get("barTime")
        if bar_time and bar_time != p.get("lastCheckedBarTime"):
            p["barsWaited"] = int(p.get("barsWaited", 0)) + 1
            p["lastCheckedBarTime"] = bar_time

        if int(p.get("barsWaited", 0)) > int(p.get("maxWaitBars", 12)):
            print(f"[PENDING] {p.get('id')} 过期，未等到KD冷却确认")
            continue

        close = d.get("price") or d.get("close")
        atr = d.get("atr", 0.0)
        prev_low = d.get("prevLow", close or 0.0)
        prev_high = d.get("prevHigh", close or 0.0)
        if close and atr and _confirm_pending_breakout(p, d) and _can_open(positions, symbol, direction):
            # MTF 门控：仅在允许突破入场时确认开仓
            if not d.get("marketRegime", {}).get("allowBreakout", True):
                print(f"[PENDING] {p.get('id')} MTF状态禁止突破入场（{d.get('marketRegime',{}).get('action','?')}），跳过确认")
                continue
            pos = _open_position(symbol, direction, "breakout", close, atr, prev_low, prev_high)
            if pos:
                pos["breakoutConfirm"] = {
                    "breakoutTime": p.get("breakoutTime"),
                    "breakoutOpen": p.get("breakoutOpen"),
                    "breakoutClose": p.get("breakoutClose"),
                    "triggerLevel": p.get("triggerLevel"),
                    "barsWaited": p.get("barsWaited", 0),
                    "confirmRule": "30m_kd_cool_hold_body50",
                }
                positions.append(pos)
                new_opened.append(pos)
                print(f"[PENDING] {p.get('id')} 确认开仓 {pos['id']}  "
                      f"SL={pos['stopLoss']}  TP={pos['takeProfit']}")
                continue

        next_pending.append(p)
    pending = next_pending

    # ── Step C: 新突破信号转 pending；回踩信号即时开仓 ───────────
    for d in merged:
        symbol     = d["symbol"]
        close      = d.get("price") or d.get("close")
        atr        = d.get("atr", 0.0)
        prev_low   = d.get("prevLow",  close or 0.0)
        prev_high  = d.get("prevHigh", close or 0.0)

        if not close or not atr:
            continue

        bo_sig = d.get("breakoutSignal")
        if bo_sig:
            direction = bo_sig.get("type", "long")
            # MTF 门控：仅在允许突破入场时加入 pending
            if not d.get("marketRegime", {}).get("allowBreakout", True):
                print(f"[GATE] {symbol} 突破信号被MTF拦截（{d.get('marketRegime',{}).get('action','?')}）")
            elif _can_open(positions, symbol, direction) and not _has_pending_breakout(pending, symbol, direction):
                event = _make_pending_breakout(d, direction)
                if event:
                    pending.append(event)
                    print(f"[PENDING] 新增突破等待 {event['id']} "
                          f"level={event['triggerLevel']} maxBars={event['maxWaitBars']}")

        pb_sig = d.get("pullbackSignal")
        if pb_sig:
            direction = pb_sig.get("type", "long")
            # 互斥：同品种已有 pending breakout 或 open 持仓时，跳过回踩信号
            if _has_pending_breakout(pending, symbol, direction) or \
               any(p["symbol"] == symbol and p["direction"] == direction and p["status"] == "open"
                   for p in positions):
                continue
            if _can_open(positions, symbol, direction):
                pos = _open_position(symbol, direction, "pullback", close, atr, prev_low, prev_high,
                                     signal_stop=pb_sig.get("stopLoss"))
                if pos:
                    positions.append(pos)
                    new_opened.append(pos)
                    print(f"[POS] 新建 {pos['id']}  SL={pos['stopLoss']}  TP={pos['takeProfit']}")

    _save_positions(positions)
    _save_pending_breakouts(pending)
    print(f"[POS] 持仓更新完成，共 {len(positions)} 笔，"
          f"其中 open={sum(1 for p in positions if p['status']=='open')}，"
          f"pending_breakout={len(pending)}，"
          f"本轮新开={len(new_opened)}")
    return new_opened


def _merge_positions_union(local_path: Path) -> None:
    """
    合并本地与远端的 positions.json：
    以 ID 为唯一键取两者的并集，同 ID 时优先保留状态更新的版本
    （closed > open，或以 exitTime 更晚者为准）。
    写回本地后由调用方 git add。
    """
    import subprocess
    repo_root = local_path.parent.parent.parent

    # 读取远端最新版本
    r = subprocess.run(
        ["git", "show", "origin/main:futures-monitor/public/positions.json"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("[GIT] 无法读取远端 positions.json，跳过并集合并")
        return

    try:
        remote_data = json.loads(r.stdout)
        remote_positions = remote_data.get("positions", [])
    except Exception:
        print("[GIT] 远端 positions.json 解析失败，跳过并集合并")
        return

    try:
        local_data = json.loads(local_path.read_text("utf-8"))
        local_positions = local_data.get("positions", [])
    except Exception:
        return

    # 以 ID 为键合并：同 ID 取"已关闭"或"退出时间更晚"的版本
    # 同状态 open 时，优先保留本地版本（本地有最新的止损/保本/移动止损更新）
    merged: dict[str, dict] = {}
    for p in remote_positions + local_positions:   # local 覆盖 remote（same ID）
        pid = p.get("id", "")
        if not pid:
            continue
        if pid not in merged:
            merged[pid] = p
        else:
            existing = merged[pid]
            # 优先保留已平仓的版本
            if existing["status"] == "open" and p["status"] != "open":
                merged[pid] = p
            elif existing["status"] != "open" and p["status"] == "open":
                pass  # 保留已有的已平仓版本
            elif existing["status"] == "open" and p["status"] == "open":
                # 同为 open：优先保留有止损更新（breakEvenMoved/trailingActive）的版本
                # 或 stopLoss 更紧的版本（说明移动止损已经推进过）
                ex_be = existing.get("breakEvenMoved") or existing.get("trailingActive")
                p_be  = p.get("breakEvenMoved") or p.get("trailingActive")
                if p_be and not ex_be:
                    merged[pid] = p   # 本地版本有止损更新，远端没有 → 用本地
                elif not p_be and ex_be:
                    pass              # 远端有更新，本地没有 → 保留远端
                elif p.get("stopLoss") is not None and existing.get("stopLoss") is not None:
                    # 都有或都没有更新：优先保留止损更紧的版本
                    direc = existing.get("direction", "long")
                    if direc == "long":
                        if p["stopLoss"] > existing["stopLoss"]:
                            merged[pid] = p   # 做多止损更高 = 更紧
                    else:
                        if p["stopLoss"] < existing["stopLoss"]:
                            merged[pid] = p   # 做空止损更低 = 更紧
            else:
                # 同状态已平仓：取 exitTime 更晚（或 entryTime 更晚）的
                def ts(pos):
                    return pos.get("exitTime") or pos.get("entryTime") or ""
                if ts(p) > ts(existing):
                    merged[pid] = p

    merged_list = sorted(merged.values(), key=lambda x: x.get("entryTime", ""))
    merged_out = {
        "updatedAt":  datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "openCount":  sum(1 for p in merged_list if p["status"] == "open"),
        "totalCount": len(merged_list),
        "positions":  merged_list,
    }
    local_path.write_text(json.dumps(merged_out, ensure_ascii=False, indent=2), "utf-8")
    print(f"[GIT] positions 并集合并完成：本地{len(local_positions)} + 远端{len(remote_positions)} → {len(merged_list)}笔")


def _git_push():
    """将更新后的 data.json / data_daily.json / positions.json 推送到 GitHub。
    positions.json 采用并集合并策略：永远保留条目更多的版本，不因本地/远端冲突丢失持仓。
    """
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent

    def run(cmd: list[str]) -> tuple[int, str]:
        r = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        return r.returncode, out

    # Step 1: 先 fetch 远端，再对 positions.json 做并集合并
    run(["git", "fetch", "origin", "main"])
    _merge_positions_union(POSITIONS_FILE)

    data_files = [
        "futures-monitor/public/data.json",
        "futures-monitor/public/data_daily.json",
        "futures-monitor/public/positions.json",
        "futures-monitor/public/pending_breakouts.json",
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

    # Step 2: merge 其余文件（data.json 等），positions.json 已经是并集，不会丢失
    run(["git", "merge", "origin/main", "--no-edit", "-X", "ours"])

    code, out = run(["git", "push", "origin", "main"])
    if code != 0:
        print(f"[GIT] git push 失败: {out}", file=sys.stderr)
    else:
        print(f"[GIT] push 成功 → GitHub / Cloudflare Pages")


if __name__ == "__main__":
    main()

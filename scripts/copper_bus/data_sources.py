"""
data_sources.py — 铜宝宝巴士 Python 版 · 数据层

设计原则(延续 Pine 版的"缺数据自动降级"思路):
  - 每个逻辑序列登记多个数据源,按优先级依次尝试,任一成功即返回。
  - 任何序列取不到 → 返回 None / NaN,由上层把对应主题降级,绝不让整个程序崩。
  - 主源 yfinance(全球跨资产,免费无 key,连 USDCLP=CLP=X 都有);
    akshare 补中国/供给端(沪铜期限结构、铜库存、中国PPI)。

对外主要接口:
  get_close(name, interval, period) -> pandas.Series | None
  get_roc(name, lookback, interval, period) -> float
  get_last(name, interval, period) -> float
  get_term_spread() -> float
  get_copper_inventory_trend(lookback_days) -> float
"""
from __future__ import annotations
import math
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    _HAS_YF = True
except Exception:
    _HAS_YF = False

try:
    import akshare as ak
    _HAS_AK = True
except Exception:
    _HAS_AK = False


REGISTRY: dict[str, list[tuple[str, str]]] = {
    "copper":  [("yf", "HG=F"), ("ak_cn_fut", "CU0")],
    "gold":    [("yf", "GC=F"), ("ak_cn_fut", "AU0")],
    "alu":     [("yf", "ALI=F"), ("ak_cn_fut", "AL0")],
    "oil":     [("yf", "CL=F"), ("ak_cn_fut", "SC0")],
    "dbc":     [("yf", "DBC"), ("ak_us", "DBC")],
    "us10y":   [("yf", "^TNX")],
    "us30y":   [("yf", "^TYX")],
    "us05y":   [("yf", "^FVX")],
    "tip":     [("yf", "TIP"), ("ak_us", "TIP")],
    "dxy":     [("yf", "DX-Y.NYB")],
    "eurusd":  [("yf", "EURUSD=X")],
    "audusd":  [("yf", "AUDUSD=X")],
    "usdcnh":  [("yf", "CNH=X"), ("yf", "USDCNH=X")],
    "usdclp":  [("yf", "CLP=X")],
    "xlu":     [("yf", "XLU"), ("ak_us", "XLU")],
    "grid":    [("yf", "GRID"), ("ak_us", "GRID")],
    "copx":    [("yf", "COPX"), ("ak_us", "COPX")],
    "fxi":     [("yf", "FXI"), ("ak_us", "FXI")],
    "kweb":    [("yf", "KWEB"), ("ak_us", "KWEB")],
    "a50":     [("yf", "XIN9.FGI"), ("yf", "FXI")],
    "es":      [("yf", "ES=F"), ("yf", "SPY")],
    "nq":      [("yf", "NQ=F"), ("yf", "QQQ")],
    "hyg":     [("yf", "HYG"), ("ak_us", "HYG")],
    "vix":     [("yf", "^VIX")],
    "move":    [("yf", "^MOVE")],
}


def _fetch_yf(symbol: str, interval: str, period: str) -> pd.Series | None:
    if not _HAS_YF:
        return None
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            return None
        col = "Close" if "Close" in df.columns else df.columns[-1]
        s = df[col].dropna()
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0].dropna()
        return s if len(s) else None
    except Exception:
        return None


def _fetch_ak_us(symbol: str) -> pd.Series | None:
    if not _HAS_AK:
        return None
    try:
        df = ak.stock_us_daily(symbol=symbol)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower)
        s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"])).dropna()
        return s if len(s) else None
    except Exception:
        return None


def _fetch_ak_cn_fut(symbol: str, interval: str) -> pd.Series | None:
    if not _HAS_AK:
        return None
    try:
        if interval in ("1d", "1wk", "1mo"):
            df = ak.futures_zh_daily_sina(symbol=symbol)
            close_col, date_col = "close", "date"
        else:
            period = {"15m": "15", "30m": "30", "60m": "60", "1h": "60",
                      "5m": "5", "90m": "60"}.get(interval, "30")
            df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
            close_col, date_col = "close", "datetime"
        if df is None or df.empty:
            return None
        s = pd.Series(pd.to_numeric(df[close_col]).values,
                      index=pd.to_datetime(df[date_col])).dropna()
        return s if len(s) else None
    except Exception:
        return None


def get_close(name: str, interval: str = "30m", period: str = "30d") -> pd.Series | None:
    for source, symbol in REGISTRY.get(name, []):
        if source == "yf":
            s = _fetch_yf(symbol, interval, period)
        elif source == "ak_us":
            s = _fetch_ak_us(symbol)
        elif source == "ak_cn_fut":
            s = _fetch_ak_cn_fut(symbol, interval)
        else:
            s = None
        if s is not None and len(s) > 1:
            s.name = name
            return s
    return None


def get_last(name: str, interval: str = "30m", period: str = "30d") -> float:
    s = get_close(name, interval, period)
    return float(s.iloc[-1]) if s is not None and len(s) else math.nan


def get_roc(name: str, lookback: int = 5, interval: str = "30m", period: str = "30d") -> float:
    s = get_close(name, interval, period)
    if s is None or len(s) <= lookback:
        return math.nan
    prev = s.iloc[-1 - lookback]
    if prev == 0 or pd.isna(prev):
        return math.nan
    return float((s.iloc[-1] / prev - 1.0) * 100.0)


def fetch_all_roc(names: list[str], lookback: int, interval: str, period: str) -> dict[str, float]:
    out = {}
    for n in names:
        out[n] = get_roc(n, lookback, interval, period)
    return out


def fetch_all_last(names: list[str], interval: str, period: str) -> dict[str, float]:
    out = {}
    for n in names:
        out[n] = get_last(n, interval, period)
    return out


def get_term_spread() -> float:
    if not _HAS_AK:
        return math.nan
    try:
        import datetime as _dt
        today = _dt.date.today().strftime("%Y%m%d")
        df = ak.get_futures_daily(start_date=today, end_date=today, market="SHFE")
        if df is None or df.empty:
            return math.nan
        cu = df[df["variety"] == "CU"].copy()
        cu = cu[cu["symbol"].str.match(r"CU\d{4}")]
        cu = cu.sort_values("symbol")
        if len(cu) < 2:
            return math.nan
        near = float(cu.iloc[0]["close"])
        nxt = float(cu.iloc[1]["close"])
        return near - nxt
    except Exception:
        return math.nan


def get_copper_inventory_trend(lookback_days: int = 5) -> float:
    if not _HAS_AK:
        return math.nan
    try:
        df = ak.futures_inventory_em(symbol="沪铜")
        if df is None or df.empty or len(df) <= lookback_days:
            return math.nan
        df = df.rename(columns=str.lower)
        col = "库存" if "库存" in df.columns else df.columns[-1]
        ser = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(ser) <= lookback_days or ser.iloc[-1 - lookback_days] == 0:
            return math.nan
        chg = (ser.iloc[-1] / ser.iloc[-1 - lookback_days] - 1.0) * 100.0
        return float(-chg)
    except Exception:
        return math.nan


def availability_report(names: list[str], interval: str, period: str) -> dict[str, bool]:
    rep = {}
    for n in names:
        s = get_close(n, interval, period)
        rep[n] = bool(s is not None and len(s) > 1)
    return rep

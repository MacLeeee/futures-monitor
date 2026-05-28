#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


TICKERS = [
    # Gold
    "GC=F",  # Comex Gold Futures proxy
    "GLD",   # ETF fallback
    # Rates / real yield / dollar
    "IEF",   # 7-10Y proxy (10Y pressure)
    "TLT",   # 20Y+ proxy (20Y/30Y pressure)
    "TIP",
    "SHY",
    "BIL",
    "UUP",       # DXY proxy
    "EURUSD=X",  # EURUSD
    "JPY=X",     # USDJPY
    "CNY=X",     # USDCNY fallback for USDCNH proxy
    # Commodities
    "CL=F",
    "HG=F",
    "DBC",
    # Risk assets
    "ES=F",
    "NQ=F",
    "RTY=F",
    "BTC-USD",
    # Credit / vol
    "HYG",
    "JNK",
    "LQD",
    "^VIX",
    "^VVIX",
    "^MOVE",
    # Asia risk
    "FXI",
    "KWEB",
    "EWJ",
    # Structure support
    "SPY",
    "QQQ",
    "IWM",
]

REGIME_GUIDE = {
    "Cash Liquidation": "减杠杆，等强平/现金化抛售结束，不急于抄底。",
    "Rates-Dollar Bearish Gold": "降低做多频率，等真实利率或美元压力缓和后再评估。",
    "Clean Bullish Gold": "偏多，回调分批试多，优先等结构确认。",
    "Reflation Gold": "持多为主，关注油和商品是否持续共振。",
    "Defensive Gold": "防御性持有为主，避免在恐慌尖峰位置追价。",
    "Fiscal / Debasement Hedge": "持核心仓，不因利率高就轻易做空。",
    "Bullish Price Override": "尊重价格强势，空头只做轻仓短打。",
    "Bearish Price Override": "尊重弱势，等反转结构成立再考虑做多。",
    "Mixed": "多空驱动混杂，以等待更高质量共振为主。",
}


@dataclass
class TrendState:
    t15: str
    t60: str
    t240: str


def now_ts() -> datetime:
    return datetime.now()


def safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except Exception:
        return None


def first_valid(d: Dict[str, Optional[float]], keys: List[str]) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def fetch_openbb_snapshot() -> Dict[str, float]:
    try:
        from openbb import obb  # pyright: ignore[reportMissingImports]
    except Exception as e:
        raise RuntimeError(f"openbb 不可用: {e}") from e

    try:
        df = obb.equity.price.quote(symbol=TICKERS, provider="yfinance").to_df()
    except Exception as e:
        raise RuntimeError(f"openbb 拉取报价失败: {e}") from e

    if df is None or df.empty:
        raise RuntimeError("openbb 返回空数据")

    if "symbol" not in df.columns:
        raise RuntimeError(f"openbb 返回字段异常: {list(df.columns)}")

    values: Dict[str, float] = {}
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).upper().strip()
        if symbol not in TICKERS:
            continue
        last_price = safe_float(row.get("last_price"))
        bid = safe_float(row.get("bid"))
        ask = safe_float(row.get("ask"))
        prev_close = safe_float(row.get("prev_close"))

        px = None
        if last_price is not None:
            px = last_price
        elif bid is not None and ask is not None:
            px = (bid + ask) / 2
        elif bid is not None:
            px = bid
        elif ask is not None:
            px = ask
        elif prev_close is not None:
            px = prev_close

        if px is not None:
            values[symbol] = float(px)

    missing = [x for x in TICKERS if x not in values]
    if missing:
        print(f"[WARN] openbb 本次快照缺失: {missing}")
    return values


def fetch_yfinance_snapshot() -> Dict[str, float]:
    try:
        import yfinance as yf  # pyright: ignore[reportMissingImports]
    except Exception as e:
        raise RuntimeError(f"yfinance 不可用: {e}") from e

    out: Dict[str, float] = {}
    for sym in TICKERS:
        try:
            ticker = yf.Ticker(sym)
            fast_info = getattr(ticker, "fast_info", {})
            px = safe_float(fast_info.get("lastPrice"))
            if px is None:
                # 备用：最近 1 天 1 分钟收盘
                hist = ticker.history(period="1d", interval="1m", auto_adjust=False)
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    px = safe_float(hist["Close"].iloc[-1])
            if px is not None:
                out[sym] = float(px)
        except Exception as e:
            print(f"[WARN] yfinance 获取 {sym} 失败: {e}")
    missing = [x for x in TICKERS if x not in out]
    if missing:
        print(f"[WARN] yfinance 本次快照缺失: {missing}")
    return out


def fetch_gold_ohlc_yfinance(preferred_symbols: Optional[List[str]] = None) -> pd.DataFrame:
    preferred_symbols = preferred_symbols or ["GC=F", "GLD"]
    try:
        import yfinance as yf  # pyright: ignore[reportMissingImports]
    except Exception as e:
        raise RuntimeError(f"yfinance 不可用: {e}") from e

    last_err = None
    for sym in preferred_symbols:
        try:
            df = yf.Ticker(sym).history(period="10d", interval="15m", auto_adjust=False)
            if df is None or df.empty:
                continue
            need_cols = {"Open", "High", "Low", "Close", "Volume"}
            if not need_cols.issubset(set(df.columns)):
                continue
            out = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            out.columns = ["open", "high", "low", "close", "volume"]
            out = out.dropna()
            if not out.empty:
                return out
        except Exception as e:
            last_err = e
    if last_err is not None:
        raise RuntimeError(f"拉取黄金OHLC失败: {last_err}") from last_err
    raise RuntimeError("拉取黄金OHLC失败: 无可用symbol")


def fetch_demo_snapshot(history_df: pd.DataFrame) -> Dict[str, float]:
    base = {
        "GC=F": 2350.0,
        "GLD": 240.0,
        "IEF": 93.0,
        "UUP": 30.0,
        "EURUSD=X": 1.08,
        "JPY=X": 157.0,
        "CNY=X": 7.25,
        "TIP": 107.0,
        "TLT": 90.0,
        "SHY": 82.0,
        "BIL": 91.0,
        "CL=F": 79.0,
        "HG=F": 4.6,
        "ES=F": 5300.0,
        "NQ=F": 18600.0,
        "RTY=F": 2100.0,
        "BTC-USD": 69000.0,
        "LQD": 107.0,
        "^VIX": 14.0,
        "^VVIX": 89.0,
        "^MOVE": 102.0,
        "SPY": 530.0,
        "QQQ": 460.0,
        "IWM": 205.0,
        "HYG": 77.0,
        "JNK": 95.0,
        "DBC": 24.0,
        "FXI": 27.0,
        "KWEB": 31.0,
        "EWJ": 67.0,
    }
    if not history_df.empty:
        last = history_df.iloc[-1].to_dict()
        for k in TICKERS:
            v = safe_float(last.get(k))
            if v is not None:
                base[k] = v

    out: Dict[str, float] = {}
    for k in TICKERS:
        drift = random.uniform(-0.0035, 0.0035)  # 约 +/-0.35%
        out[k] = round(base[k] * (1 + drift), 4)
    return out


def load_history(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def bootstrap_history_with_openbb(path: Path, lookback_days: int = 5) -> None:
    """首次运行时补齐历史 15m 数据，避免 1h/4h 信号都为 Neutral。"""
    try:
        from openbb import obb  # pyright: ignore[reportMissingImports]
    except Exception as e:
        print(f"[WARN] 无法预热历史（openbb 不可用）: {e}")
        return

    start_date = (datetime.now() - timedelta(days=lookback_days)).date().isoformat()
    merged: Optional[pd.DataFrame] = None

    for sym in TICKERS:
        try:
            df = obb.equity.price.historical(
                symbol=sym,
                provider="yfinance",
                interval="15m",
                start_date=start_date,
            ).to_df()
            if df is None or df.empty or "close" not in df.columns:
                continue
            s = df[["close"]].copy()
            s.index = pd.to_datetime(s.index)
            s = s.rename(columns={"close": sym})
            merged = s if merged is None else merged.join(s, how="outer")
        except Exception as e:
            print(f"[WARN] 预热 {sym} 失败: {e}")

    if merged is None or merged.empty:
        print("[WARN] openbb 历史预热未拿到有效数据")
        return

    merged = merged.sort_index().ffill().dropna(how="all")
    out = merged.reset_index()
    first_col = out.columns[0]
    out = out.rename(columns={first_col: "ts"})
    out["ts"] = pd.to_datetime(out["ts"], errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S")
    out = out[out["ts"].notna()]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    print(f"[INFO] 历史预热完成: {path}，行数={len(out)}")


def bootstrap_history_with_yfinance(path: Path, lookback_days: int = 5) -> None:
    try:
        import yfinance as yf  # pyright: ignore[reportMissingImports]
    except Exception as e:
        print(f"[WARN] 无法预热历史（yfinance 不可用）: {e}")
        return

    start = (datetime.now() - timedelta(days=lookback_days)).date().isoformat()
    end = datetime.now().date().isoformat()

    try:
        raw = yf.download(
            tickers=TICKERS,
            start=start,
            end=end,
            interval="15m",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as e:
        print(f"[WARN] yfinance 历史预热失败: {e}")
        return

    if raw is None or raw.empty:
        print("[WARN] yfinance 历史预热为空")
        return

    merged: Optional[pd.DataFrame] = None
    for sym in TICKERS:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if sym in raw.columns.get_level_values(0):
                    s = raw[sym][["Close"]].rename(columns={"Close": sym})
                else:
                    continue
            else:
                if sym == TICKERS[0] and "Close" in raw.columns:
                    s = raw[["Close"]].rename(columns={"Close": sym})
                else:
                    continue
            s.index = pd.to_datetime(s.index)
            merged = s if merged is None else merged.join(s, how="outer")
        except Exception as e:
            print(f"[WARN] yfinance 处理 {sym} 历史失败: {e}")

    if merged is None or merged.empty:
        print("[WARN] yfinance 历史预热未拿到有效数据")
        return

    merged = merged.sort_index().ffill().dropna(how="all")
    out = merged.reset_index()
    first_col = out.columns[0]
    out = out.rename(columns={first_col: "ts"})
    out["ts"] = pd.to_datetime(out["ts"], errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S")
    out = out[out["ts"].notna()]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    print(f"[INFO] yfinance 历史预热完成: {path}，行数={len(out)}")


def append_snapshot(path: Path, snapshot: Dict[str, float], ts: datetime) -> None:
    row = {"ts": ts.isoformat(timespec="seconds")}
    row.update(snapshot)
    df_new = pd.DataFrame([row])
    if path.exists():
        df_old = pd.read_csv(path)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    # 保留最近 10 天快照即可
    if "ts" in df.columns:
        ts_col = pd.to_datetime(df["ts"], errors="coerce")
        cutoff = datetime.now() - timedelta(days=10)
        mask = ts_col >= cutoff
        df = df[mask.fillna(False)]
    df.to_csv(path, index=False)


def nearest_past_row(df: pd.DataFrame, target_time: datetime) -> Optional[pd.Series]:
    if df.empty:
        return None
    df2 = df.copy()
    df2["ts"] = pd.to_datetime(df2["ts"])
    past = df2[df2["ts"] <= target_time]
    if past.empty:
        return None
    return past.iloc[-1]


def pct_change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return (cur / prev - 1.0) * 100.0


def get_window_change(
    history_df: pd.DataFrame,
    latest: Dict[str, float],
    now: datetime,
    mins: int,
) -> Dict[str, Optional[float]]:
    prev_row = nearest_past_row(history_df, now - timedelta(minutes=mins))
    out: Dict[str, Optional[float]] = {}
    for k in TICKERS:
        cur = latest.get(k)
        prev = None
        if prev_row is not None and k in prev_row.index:
            prev = safe_float(prev_row[k])
        out[k] = pct_change(cur, prev)
    return out


def to_sign(v: Optional[float], th: float = 0.10) -> str:
    if v is None:
        return "Neutral"
    if v > th:
        return "Bull"
    if v < -th:
        return "Bear"
    return "Neutral"


def calc_trend_state(gold_chg_15: Optional[float], gold_chg_60: Optional[float], gold_chg_240: Optional[float]) -> TrendState:
    return TrendState(
        t15=to_sign(gold_chg_15),
        t60=to_sign(gold_chg_60),
        t240=to_sign(gold_chg_240),
    )


def trend_combo_advice(trend: TrendState) -> str:
    key = (trend.t15, trend.t60, trend.t240)
    table = {
        ("Bull", "Bull", "Bull"): "顺势持有 / 趋势加仓",
        ("Bear", "Bull", "Bull"): "止盈部分，不轻易反手空",
        ("Bull", "Neutral", "Bull"): "可重新试多",
        ("Bull", "Bear", "Bull"): "最重要的小仓试多结构",
        ("Bull", "Bear", "Bear"): "短线反弹，趋势偏空",
        ("Bull", "Neutral", "Bear"): "观察是否升级为1h转多",
        ("Bull", "Bull", "Bear"): "可逐步加仓",
        ("Bear", "Bear", "Bear"): "顺势做空 / 持空",
        ("Bear", "Neutral", "Bull"): "先观察，不急着追空",
        ("Bear", "Bull", "Bull"): "止盈，不轻易反手空",
        ("Bear", "Bull", "Bear"): "可考虑反手空",
        ("Bear", "Bear", "Bull"): "观察是否升级为4h转空，或15m转多",
    }
    return table.get(key, "观察等待：组合尚未形成高确定性结构")


def calc_trend_state_from_ohlc(ohlc: pd.DataFrame, lb: int = 5) -> TrendState:
    def _roc(series: pd.Series, bars: int) -> Optional[float]:
        s = series.dropna()
        if len(s) <= bars:
            return None
        prev = float(s.iloc[-1 - bars])
        cur = float(s.iloc[-1])
        if prev == 0:
            return None
        return (cur / prev - 1.0) * 100.0

    idx = pd.to_datetime(ohlc.index)
    c = ohlc["close"].copy()
    c.index = idx
    c15 = c
    c1h = c.resample("1h").last().dropna()
    c4h = c.resample("4h").last().dropna()

    return TrendState(
        t15=to_sign(_roc(c15, lb)),
        t60=to_sign(_roc(c1h, lb)),
        t240=to_sign(_roc(c4h, lb)),
    )


def calc_liquidity_score(chg_15: Dict[str, Optional[float]]) -> Tuple[int, str]:
    # 对齐 Pine: Realtime Liquidity 3 - Global Dollar Risk Proxy
    gold_chg = first_valid(chg_15, ["GC=F", "GLD"])
    dxy_pressure = first_valid(chg_15, ["UUP"])
    cnh_pressure = first_valid(chg_15, ["CNY=X"])
    jpy_pressure = first_valid(chg_15, ["JPY=X"])
    hyg_chg = first_valid(chg_15, ["HYG"])
    jnk_chg = first_valid(chg_15, ["JNK"])
    lqd_chg = first_valid(chg_15, ["LQD"])
    vix_stress = first_valid(chg_15, ["^VIX"])
    vvix_stress = first_valid(chg_15, ["^VVIX"])
    move_stress = first_valid(chg_15, ["^MOVE"])
    spy_chg = first_valid(chg_15, ["SPY"])
    qqq_chg = first_valid(chg_15, ["QQQ", "NQ=F"])

    credit_stress = None
    if hyg_chg is not None and jnk_chg is not None:
        credit_stress = ((-hyg_chg) + (-jnk_chg)) / 2
    elif hyg_chg is not None:
        credit_stress = -hyg_chg
    elif jnk_chg is not None:
        credit_stress = -jnk_chg

    ig_stress = -lqd_chg if lqd_chg is not None else None
    gold_stress = -gold_chg if gold_chg is not None else None
    spy_stress = -spy_chg if spy_chg is not None else None
    qqq_stress = -qqq_chg if qqq_chg is not None else None

    score_raw = 0
    for v in [dxy_pressure, cnh_pressure, credit_stress, ig_stress, vix_stress, vvix_stress, move_stress, gold_stress]:
        score_raw += 1 if (v is not None and v > 0) else 0

    dollar_shock = (
        dxy_pressure is not None
        and credit_stress is not None
        and move_stress is not None
        and gold_stress is not None
        and dxy_pressure > 0
        and credit_stress > 0
        and move_stress > 0
        and gold_stress > 0
    )
    equity_still_holding = (
        spy_stress is not None
        and qqq_stress is not None
        and credit_stress is not None
        and spy_stress <= 0
        and qqq_stress <= 0
        and credit_stress > 0
    )

    if dollar_shock and score_raw >= 5:
        state = "Dollar Liquidity Shock"
    elif score_raw >= 5:
        state = "Cross-Asset Risk-Off"
    elif equity_still_holding:
        state = "Credit Weak / Equity Holding"
    elif score_raw >= 3:
        state = "Risk Pressure Building"
    elif score_raw >= 1:
        state = "Watch"
    else:
        state = "Calm"

    score_100 = int(round(score_raw / 8 * 100))
    return score_100, state


def calc_regime(chg_15: Dict[str, Optional[float]]) -> Tuple[str, Dict[str, int | str]]:
    # 对齐 Pine: Gold Futures Regime Machine v2 - Theme Ranking
    gold_chg = first_valid(chg_15, ["GC=F", "GLD"])
    y10_pressure = -first_valid(chg_15, ["IEF"]) if first_valid(chg_15, ["IEF"]) is not None else None
    y20_pressure = -first_valid(chg_15, ["TLT"]) if first_valid(chg_15, ["TLT"]) is not None else None
    y30_pressure = -first_valid(chg_15, ["TLT"]) if first_valid(chg_15, ["TLT"]) is not None else None
    real_pressure = -first_valid(chg_15, ["TIP"]) if first_valid(chg_15, ["TIP"]) is not None else None
    tlt_stress = -first_valid(chg_15, ["TLT"]) if first_valid(chg_15, ["TLT"]) is not None else None

    dxy_chg = first_valid(chg_15, ["UUP"])
    eur_chg = first_valid(chg_15, ["EURUSD=X"])
    if eur_chg is None and dxy_chg is not None:
        eur_chg = -dxy_chg
    jpy_chg = first_valid(chg_15, ["JPY=X"])
    cnh_chg = first_valid(chg_15, ["CNY=X"])

    oil_chg = first_valid(chg_15, ["CL=F"])
    cu_chg = first_valid(chg_15, ["HG=F"])
    dbc_chg = first_valid(chg_15, ["DBC"])

    es_chg = first_valid(chg_15, ["ES=F", "SPY"])
    nq_chg = first_valid(chg_15, ["NQ=F", "QQQ"])
    btc_chg = first_valid(chg_15, ["BTC-USD"])

    hyg_stress = -first_valid(chg_15, ["HYG"]) if first_valid(chg_15, ["HYG"]) is not None else None
    jnk_stress = -first_valid(chg_15, ["JNK"]) if first_valid(chg_15, ["JNK"]) is not None else None
    vix_stress = first_valid(chg_15, ["^VIX"])
    move_stress = first_valid(chg_15, ["^MOVE"])

    fxi_chg = first_valid(chg_15, ["FXI"])
    kweb_chg = first_valid(chg_15, ["KWEB"])
    _ewj_chg = first_valid(chg_15, ["EWJ"])

    def gt0(x: Optional[float]) -> bool:
        return x is not None and x > 0

    def lt0(x: Optional[float]) -> bool:
        return x is not None and x < 0

    gold_up = gt0(gold_chg)
    gold_down = lt0(gold_chg)
    real_tightening = gt0(real_pressure)
    real_relief = lt0(real_pressure)
    dollar_strong = gt0(dxy_chg) and lt0(eur_chg)
    dollar_relief = lt0(dxy_chg) and gt0(eur_chg)
    yen_stress = gt0(jpy_chg)
    cnh_stress = gt0(cnh_chg)
    global_dollar_pressure = dollar_strong and (yen_stress or cnh_stress)

    s10s30_proxy = None
    if y30_pressure is not None and y10_pressure is not None:
        s10s30_proxy = y30_pressure - y10_pressure

    long_end_pressure = (
        y30_pressure is not None
        and y10_pressure is not None
        and s10s30_proxy is not None
        and y30_pressure > y10_pressure
        and y30_pressure > 0
        and s10s30_proxy > 0
    )
    long_bond_stress = gt0(tlt_stress) and long_end_pressure

    risk_on = gt0(es_chg) and gt0(nq_chg) and gt0(btc_chg)
    risk_off = lt0(es_chg) and lt0(nq_chg) and lt0(btc_chg)
    credit_stress = gt0(hyg_stress) and gt0(jnk_stress)
    vol_stress = gt0(vix_stress) or gt0(move_stress)
    asia_risk_on = gt0(fxi_chg) and gt0(kweb_chg) and (cnh_chg is not None and cnh_chg <= 0)
    gold_outperform_bonds = gold_up and gt0(tlt_stress)
    gold_outperform_risk = gold_up and lt0(es_chg) and lt0(nq_chg)
    cash_stress = gold_down and global_dollar_pressure and (risk_off or credit_stress) and lt0(btc_chg)

    score_fiscal_hedge = 0
    score_fiscal_hedge += 2 if long_end_pressure else 0
    score_fiscal_hedge += 1 if long_bond_stress else 0
    score_fiscal_hedge += 2 if gold_outperform_bonds else 0
    score_fiscal_hedge += 2 if gold_up else 0
    score_fiscal_hedge += 1 if not dollar_strong else 0

    score_debasement = 0
    score_debasement += 1 if long_end_pressure else 0
    score_debasement += 1 if gt0(btc_chg) else 0
    score_debasement += 2 if gold_up else 0
    score_debasement += 1 if (dxy_chg is not None and dxy_chg <= 0) else 0

    score_real_yield_relief = 0
    score_real_yield_relief += 2 if real_relief else 0
    score_real_yield_relief += 1 if dollar_relief else 0
    score_real_yield_relief += 2 if gold_up else 0
    score_real_yield_relief += 1 if (y10_pressure is not None and y10_pressure < 0) else 0

    score_reflation = 0
    score_reflation += 1 if gt0(oil_chg) else 0
    score_reflation += 1 if gt0(cu_chg) else 0
    score_reflation += 1 if gt0(dbc_chg) else 0
    score_reflation += 1 if asia_risk_on else 0
    score_reflation += 2 if gold_up else 0

    score_defensive_gold = 0
    score_defensive_gold += 2 if risk_off else 0
    score_defensive_gold += 2 if gold_outperform_risk else 0
    score_defensive_gold += 2 if gold_up else 0
    score_defensive_gold += 1 if vol_stress else 0

    score_rates_dollar_bear = 0
    score_rates_dollar_bear += 2 if real_tightening else 0
    score_rates_dollar_bear += 2 if dollar_strong else 0
    score_rates_dollar_bear += 2 if gold_down else 0
    score_rates_dollar_bear += 1 if (y10_pressure is not None and y10_pressure > 0) else 0

    score_cash_liquidation = 0
    score_cash_liquidation += 4 if cash_stress else 0
    score_cash_liquidation += 1 if global_dollar_pressure else 0
    score_cash_liquidation += 1 if risk_off else 0
    score_cash_liquidation += 1 if credit_stress else 0
    score_cash_liquidation += 1 if gold_down else 0
    score_cash_liquidation += 1 if lt0(btc_chg) else 0

    score_gold_rate_pressure = 0
    score_gold_rate_pressure += 2 if real_tightening else 0
    score_gold_rate_pressure += 2 if gold_down else 0
    score_gold_rate_pressure += 1 if (y10_pressure is not None and y10_pressure > 0) else 0
    score_gold_rate_pressure += 1 if not cash_stress else 0

    score_dollar_pressure = 0
    score_dollar_pressure += 2 if dollar_strong else 0
    score_dollar_pressure += 1 if global_dollar_pressure else 0
    score_dollar_pressure += 1 if gold_down else 0
    score_dollar_pressure += 1 if cnh_stress else 0
    score_dollar_pressure += 1 if yen_stress else 0

    bull_scores = {
        "Fiscal Hedge Bid": score_fiscal_hedge,
        "Debasement Bid": score_debasement,
        "Real Yield Relief": score_real_yield_relief,
        "Reflation Bid": score_reflation,
        "Defensive Gold Bid": score_defensive_gold,
    }
    bear_scores = {
        "Cash Liquidation": score_cash_liquidation,
        "Real Yield + Dollar Pressure": score_rates_dollar_bear,
        "Gold Rate Pressure": score_gold_rate_pressure,
        "Global Dollar Pressure": score_dollar_pressure,
    }
    bull_order = ["Fiscal Hedge Bid", "Debasement Bid", "Real Yield Relief", "Reflation Bid", "Defensive Gold Bid"]
    bear_order = ["Cash Liquidation", "Real Yield + Dollar Pressure", "Gold Rate Pressure", "Global Dollar Pressure"]

    bull_max = max(bull_scores.values()) if bull_scores else 0
    bear_max = max(bear_scores.values()) if bear_scores else 0
    dominant_bull = next((k for k in bull_order if bull_scores.get(k, 0) == bull_max and bull_max > 0), "None")
    dominant_bear = next((k for k in bear_order if bear_scores.get(k, 0) == bear_max and bear_max > 0), "None")

    if gold_up and bull_max >= bear_max - 1:
        dominant_theme = dominant_bull
    elif gold_down and bear_max >= bull_max - 1:
        dominant_theme = dominant_bear
    elif gold_up and bear_max > bull_max:
        dominant_theme = "Gold Rising Against Bearish Pressure"
    elif gold_down and bull_max > bear_max:
        dominant_theme = "Gold Falling Despite Bullish Support"
    elif bull_max > bear_max:
        dominant_theme = dominant_bull
    elif bear_max > bull_max:
        dominant_theme = dominant_bear
    else:
        dominant_theme = "Mixed / No Clear Edge"

    if dominant_theme == "Cash Liquidation":
        regime = "Cash Liquidation"
    elif dominant_theme in {"Fiscal Hedge Bid", "Debasement Bid"}:
        regime = "Fiscal / Debasement Hedge"
    elif dominant_theme == "Real Yield Relief":
        regime = "Clean Bullish Gold"
    elif dominant_theme == "Reflation Bid":
        regime = "Reflation Gold"
    elif dominant_theme == "Defensive Gold Bid":
        regime = "Defensive Gold"
    elif dominant_theme in {"Real Yield + Dollar Pressure", "Gold Rate Pressure", "Global Dollar Pressure"}:
        regime = "Rates-Dollar Bearish Gold"
    elif dominant_theme == "Gold Rising Against Bearish Pressure":
        regime = "Bullish Price Override"
    elif dominant_theme == "Gold Falling Despite Bullish Support":
        regime = "Bearish Price Override"
    else:
        regime = "Mixed"

    detail: Dict[str, int | str] = {
        "dominant_theme": dominant_theme,
        "bull_max": int(bull_max),
        "bear_max": int(bear_max),
        "score_fiscal_hedge": int(score_fiscal_hedge),
        "score_debasement": int(score_debasement),
        "score_real_yield_relief": int(score_real_yield_relief),
        "score_reflation": int(score_reflation),
        "score_defensive_gold": int(score_defensive_gold),
        "score_rates_dollar_bear": int(score_rates_dollar_bear),
        "score_cash_liquidation": int(score_cash_liquidation),
        "score_gold_rate_pressure": int(score_gold_rate_pressure),
        "score_dollar_pressure": int(score_dollar_pressure),
    }
    return regime, detail


def recent_gold_series(
    history_df: pd.DataFrame,
    latest: Dict[str, float],
    limit: int = 40,
    preferred_symbols: Optional[List[str]] = None,
) -> pd.Series:
    preferred_symbols = preferred_symbols or ["GC=F", "GLD"]
    rows: List[float] = []
    chosen_col = None
    for sym in preferred_symbols:
        if (not history_df.empty) and (sym in history_df.columns):
            chosen_col = sym
            break
    if chosen_col is not None:
        rows.extend([safe_float(v) for v in history_df[chosen_col].tail(limit - 1).tolist()])
    rows = [x for x in rows if x is not None]
    latest_gold = first_valid(latest, preferred_symbols)
    if latest_gold is not None:
        rows.append(latest_gold)
    return pd.Series(rows, dtype="float64")


def calc_structure_scores_from_ohlc(ohlc: pd.DataFrame) -> Tuple[int, int, Dict[str, bool]]:
    # Pine 参数对齐
    pivot_len = 8
    sweep_lookback = 20
    near_fib_pct = 0.18
    double_touch_pct = 0.25
    extension_pct = 0.35

    if ohlc is None or ohlc.empty or len(ohlc) < max(2 * pivot_len + 2, sweep_lookback + 2):
        return 0, 0, {"insufficient_data": True}

    df = ohlc.copy()
    df = df.sort_index()
    o = df["open"].reset_index(drop=True)
    h = df["high"].reset_index(drop=True)
    l = df["low"].reset_index(drop=True)
    c = df["close"].reset_index(drop=True)
    v = df["volume"].reset_index(drop=True)
    n = len(df)
    cur = n - 1
    prev = n - 2

    # VWAP (按交易日累计近似 ta.vwap)
    dt = pd.to_datetime(df.index)
    day_key = pd.Series(dt.date).reset_index(drop=True)
    hlc3 = (h + l + c) / 3.0
    pv = hlc3 * v
    cum_pv = pv.groupby(day_key).cumsum()
    cum_v = v.groupby(day_key).cumsum().replace(0, pd.NA)
    vwap = cum_pv / cum_v

    # 最近可确认 pivot（右侧 pivot_len 根）
    last_high = None
    last_low = None
    last_high_bar = None
    last_low_bar = None
    start = pivot_len
    end = n - pivot_len
    for i in range(start, end):
        w_high = h.iloc[i - pivot_len : i + pivot_len + 1]
        w_low = l.iloc[i - pivot_len : i + pivot_len + 1]
        if h.iloc[i] == w_high.max():
            last_high = float(h.iloc[i])
            last_high_bar = i
        if l.iloc[i] == w_low.min():
            last_low = float(l.iloc[i])
            last_low_bar = i

    has_swing = last_high is not None and last_low is not None and last_high_bar is not None and last_low_bar is not None
    up_swing = bool(has_swing and last_low_bar < last_high_bar)
    down_swing = bool(has_swing and last_high_bar < last_low_bar)
    swing_range = abs(last_high - last_low) if has_swing else None

    fib382 = fib500 = fib618 = fib786 = None
    if has_swing and swing_range is not None:
        if up_swing:
            fib382 = last_high - swing_range * 0.382
            fib500 = last_high - swing_range * 0.500
            fib618 = last_high - swing_range * 0.618
            fib786 = last_high - swing_range * 0.786
        elif down_swing:
            fib382 = last_low + swing_range * 0.382
            fib500 = last_low + swing_range * 0.500
            fib618 = last_low + swing_range * 0.618
            fib786 = last_low + swing_range * 0.786

    def _near(level: Optional[float]) -> bool:
        return level is not None and abs(c.iloc[cur] - level) / c.iloc[cur] * 100 <= near_fib_pct

    near382 = _near(fib382)
    near500 = _near(fib500)
    near618 = _near(fib618)
    near786 = _near(fib786)
    near_key_fib = near382 or near500 or near618 or near786

    prior_swing_low = l.iloc[cur - sweep_lookback : cur].min()
    prior_swing_high = h.iloc[cur - sweep_lookback : cur].max()
    bull_sweep = l.iloc[cur] < prior_swing_low and c.iloc[cur] > prior_swing_low
    bear_sweep = h.iloc[cur] > prior_swing_high and c.iloc[cur] < prior_swing_high

    double_bottom = abs(l.iloc[cur] - prior_swing_low) / c.iloc[cur] * 100 <= double_touch_pct and c.iloc[cur] > o.iloc[cur]
    double_top = abs(h.iloc[cur] - prior_swing_high) / c.iloc[cur] * 100 <= double_touch_pct and c.iloc[cur] < o.iloc[cur]

    vwap_reclaim = c.iloc[cur] > vwap.iloc[cur] and c.iloc[prev] <= vwap.iloc[prev]
    vwap_reject = c.iloc[cur] < vwap.iloc[cur] and c.iloc[prev] >= vwap.iloc[prev]
    above_vwap = c.iloc[cur] > vwap.iloc[cur]
    below_vwap = c.iloc[cur] < vwap.iloc[cur]
    far_above_vwap = (c.iloc[cur] - vwap.iloc[cur]) / c.iloc[cur] * 100 > extension_pct
    far_below_vwap = (vwap.iloc[cur] - c.iloc[cur]) / c.iloc[cur] * 100 > extension_pct

    bull_candle = c.iloc[cur] > o.iloc[cur]
    bear_candle = c.iloc[cur] < o.iloc[cur]
    higher_low = (last_low is not None) and (l.iloc[cur] > last_low) and bull_candle
    lower_high = (last_high is not None) and (h.iloc[cur] < last_high) and bear_candle

    long_score = 0
    long_score += 3 if bull_sweep else 0
    long_score += 2 if double_bottom else 0
    long_score += 2 if vwap_reclaim else 0
    long_score += 2 if near618 else 0
    long_score += 1 if near500 else 0
    long_score += 1 if near382 else 0
    long_score += 1 if higher_low else 0
    long_score += 1 if above_vwap else 0
    long_score -= 2 if far_above_vwap else 0

    short_score = 0
    short_score += 3 if bear_sweep else 0
    short_score += 2 if double_top else 0
    short_score += 2 if vwap_reject else 0
    short_score += 2 if near618 else 0
    short_score += 1 if near500 else 0
    short_score += 1 if near382 else 0
    short_score += 1 if lower_high else 0
    short_score += 1 if below_vwap else 0
    short_score -= 2 if far_below_vwap else 0

    long_score = max(0, min(10, long_score))
    short_score = max(0, min(10, short_score))
    flags = {
        "vwap_reclaim": bool(vwap_reclaim),
        "vwap_reject": bool(vwap_reject),
        "near_fib_618": bool(near618),
        "near_key_fib": bool(near_key_fib),
        "bull_sweep": bool(bull_sweep),
        "bear_sweep": bool(bear_sweep),
        "double_bottom": bool(double_bottom),
        "double_top": bool(double_top),
        "higher_low": bool(higher_low),
        "lower_high": bool(lower_high),
    }
    return long_score, short_score, flags


def advice_by_rules(
    regime: str,
    liq_score: int,
    trend: TrendState,
    long_score: int,
    short_score: int,
) -> str:
    # 多头强共振
    if (
        regime in {"Clean Bullish Gold", "Reflation Gold", "Fiscal / Debasement Hedge", "Bullish Price Override", "Defensive Gold"}
        and liq_score < 45
        and trend.t15 == "Bull"
        and long_score >= 7
        and short_score <= 4
    ):
        return "偏多：满足三层共振，可分批试多，止损放在最近结构低点下。"

    # 空头强共振
    if (
        regime in {"Cash Liquidation", "Rates-Dollar Bearish Gold", "Bearish Price Override"}
        and liq_score >= 45
        and trend.t15 == "Bear"
        and short_score >= 7
        and long_score <= 4
    ):
        return "偏空：满足空头共振，可轻仓试空或减多，止损放在最近结构高点上。"

    if liq_score >= 75:
        return "风险控制优先：流动性冲击，先降杠杆，暂停新仓。"

    if liq_score >= 60:
        return "谨慎：流动性偏紧，减少频繁交易，以观察为主。"

    return "观望：当前未形成高质量共振，等待状态机/流动性/结构进一步一致。"


def format_report(
    ts: datetime,
    regime: str,
    regime_detail: Dict[str, int | str],
    liq_score: int,
    liq_state: str,
    trend: TrendState,
    long_score: int,
    short_score: int,
    flags: Dict[str, bool],
    advice: str,
    combo_advice: str,
) -> str:
    combo = f"{trend.t15}/{trend.t60}/{trend.t240}"
    struct = (
        f"Long={long_score}/10, Short={short_score}/10, "
        f"VWAP_Reclaim={flags.get('vwap_reclaim')}, "
        f"VWAP_Reject={flags.get('vwap_reject')}, "
        f"NearFib618={flags.get('near_fib_618')}"
    )
    return (
        f"\n[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 黄金宝宝巴士监控\n"
        f"- 状态机: {regime}\n"
        f"- 主题排名: {regime_detail.get('dominant_theme')} (BullMax={regime_detail.get('bull_max')}, BearMax={regime_detail.get('bear_max')})\n"
        f"- 流动性评分: {liq_score}/100 ({liq_state})\n"
        f"- 15m/1h/4h 组合: {combo}\n"
        f"- 组合建议: {combo_advice}\n"
        f"- 多空结构: {struct}\n"
        f"- 建议: {advice}\n"
    )


def analyze_once(history_path: Path, data_source: str = "auto") -> Dict[str, object]:
    ts = now_ts()
    hist = load_history(history_path)

    if data_source == "demo":
        latest = fetch_demo_snapshot(hist)
    elif data_source == "openbb":
        latest = fetch_openbb_snapshot()
    elif data_source == "yfinance":
        latest = fetch_yfinance_snapshot()
    else:
        raise ValueError(f"不支持的数据源: {data_source}")

    # Pine 脚本默认 lb=5；在 15m 采样下等价于约 75 分钟 ROC
    chg_15 = get_window_change(hist, latest, ts, 75)     # 15m * 5 bars
    chg_60 = get_window_change(hist, latest, ts, 300)    # 1h * 5 bars
    chg_240 = get_window_change(hist, latest, ts, 1200)  # 4h * 5 bars

    regime, regime_detail = calc_regime(chg_15)
    liq_score, liq_state = calc_liquidity_score(chg_15)

    ohlc = None
    try:
        ohlc = fetch_gold_ohlc_yfinance(["GC=F", "GLD"])
    except Exception as e:
        print(f"[WARN] 黄金OHLC拉取失败，趋势/结构降级: {e}")

    if ohlc is not None and not ohlc.empty:
        trend = calc_trend_state_from_ohlc(ohlc, lb=5)
    else:
        trend = calc_trend_state(
            gold_chg_15=first_valid(chg_15, ["GC=F", "GLD"]),
            gold_chg_60=first_valid(chg_60, ["GC=F", "GLD"]),
            gold_chg_240=first_valid(chg_240, ["GC=F", "GLD"]),
        )

    long_score = 0
    short_score = 0
    flags: Dict[str, bool] = {"insufficient_data": True}
    if ohlc is not None and not ohlc.empty:
        long_score, short_score, flags = calc_structure_scores_from_ohlc(ohlc)

    advice = advice_by_rules(
        regime=regime,
        liq_score=liq_score,
        trend=trend,
        long_score=long_score,
        short_score=short_score,
    )
    combo_hint = trend_combo_advice(trend)

    append_snapshot(history_path, latest, ts)
    regime_guide = REGIME_GUIDE.get(regime, REGIME_GUIDE["Mixed"])

    # 把 Optional[float] 转为 float|null 便于 JSON 序列化
    def safe_chg(d: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
        return {k: (round(v, 4) if v is not None else None) for k, v in d.items()}

    return {
        "timestamp": ts.isoformat(timespec="seconds"),
        "regime": regime,
        "regime_detail": regime_detail,
        "regime_guide": regime_guide,
        "liquidity_score": liq_score,
        "liquidity_state": liq_state,
        "trend_15m_1h_4h": {"15m": trend.t15, "1h": trend.t60, "4h": trend.t240},
        "structure": {
            "long_score": long_score,
            "short_score": short_score,
            "flags": flags,
        },
        "advice": advice,
        "combo_advice": combo_hint,
        "etf_snapshot": {
            "prices": {k: round(v, 2) for k, v in latest.items()},
            "chg_15m": safe_chg(chg_15),
            "chg_60m": safe_chg(chg_60),
            "chg_240m": safe_chg(chg_240),
        },
    }


def run_loop(
    history_path: Path,
    interval_minutes: int,
    once: bool,
    output_json: bool,
    data_source: str,
) -> None:
    def _needs_bootstrap(hist_df: pd.DataFrame) -> bool:
        if hist_df.empty or len(hist_df) < 20:
            return True
        critical = ["GC=F", "GLD", "TIP", "UUP", "SPY", "QQQ", "HYG", "JNK", "CNY=X", "JPY=X", "LQD", "^VIX"]
        present = [c for c in critical if c in hist_df.columns]
        return len(present) < 8

    if data_source == "openbb":
        hist = load_history(history_path)
        if _needs_bootstrap(hist):
            print("[INFO] 历史样本不足，先执行 openbb 历史预热...")
            bootstrap_history_with_openbb(history_path)
    elif data_source == "yfinance":
        hist = load_history(history_path)
        if _needs_bootstrap(hist):
            print("[INFO] 历史样本不足，先执行 yfinance 历史预热...")
            bootstrap_history_with_yfinance(history_path)

    print(f"[INFO] 数据源: {data_source}")
    while True:
        try:
            result = analyze_once(history_path, data_source=data_source)
            if output_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                ts = datetime.fromisoformat(result["timestamp"])
                trend = result["trend_15m_1h_4h"]
                structure = result["structure"]
                report = format_report(
                    ts=ts,
                    regime=result["regime"],
                    regime_detail=result.get("regime_detail", {}),
                    liq_score=result["liquidity_score"],
                    liq_state=result["liquidity_state"],
                    trend=TrendState(trend["15m"], trend["1h"], trend["4h"]),
                    long_score=structure["long_score"],
                    short_score=structure["short_score"],
                    flags=structure["flags"],
                    advice=f"{result['regime_guide']} | {result['advice']}",
                    combo_advice=result.get("combo_advice", "观察等待"),
                )
                print(report)
        except Exception as e:
            print(f"[ERROR] {datetime.now().strftime('%F %T')} 监控失败: {e}")

        if once:
            return

        time.sleep(max(1, interval_minutes) * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="黄金宝宝巴士监控器（yfinance主数据源）")
    parser.add_argument("--interval", type=int, default=15, help="轮询间隔（分钟），默认 15")
    parser.add_argument("--history-file", type=str, default="gold_bus_history.csv", help="本地快照文件路径")
    parser.add_argument("--once", action="store_true", help="只执行一次")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--data-source", type=str, default="yfinance", choices=["openbb", "yfinance", "demo"], help="数据源")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    history_path = Path(args.history_file).expanduser().resolve()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 启动监控: interval={args.interval}m, history={history_path}, once={args.once}")
    run_loop(history_path, args.interval, args.once, args.json, args.data_source)


if __name__ == "__main__":
    main()

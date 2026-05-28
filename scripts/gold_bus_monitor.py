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
    "GLD",  # gold proxy
    "UUP",  # dollar proxy
    "TIP",  # real-yield proxy
    "TLT",  # long-end bond proxy
    "SHY",  # short-end bond proxy
    "SPY",
    "QQQ",
    "IWM",
    "HYG",
    "JNK",
    "USO",  # oil proxy
    "DBC",  # commodity proxy
    "FXI",
    "KWEB",
    "EWJ",
]

REGIME_GUIDE = {
    "Cash Liquidation": "减杠杆，等强平/现金化抛售结束，不急于抄底。",
    "Rates-Dollar Bearish Gold": "降低做多频率，等真实利率或美元压力缓和后再评估。",
    "Clean Bullish Gold": "偏多，回调分批试多，优先等结构确认。",
    "Reflation Gold": "持多为主，关注油和商品是否持续共振。",
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


def fetch_demo_snapshot(history_df: pd.DataFrame) -> Dict[str, float]:
    base = {
        "GLD": 240.0,
        "UUP": 30.0,
        "TIP": 107.0,
        "TLT": 90.0,
        "SHY": 82.0,
        "SPY": 530.0,
        "QQQ": 460.0,
        "IWM": 205.0,
        "HYG": 77.0,
        "JNK": 95.0,
        "USO": 83.0,
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
    """
    首次运行时补齐历史 15m 数据，避免 1h/4h 信号都为 Neutral。
    """
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
    """获取 mins 分钟前的参考价格，计算变化率。
    
    优先用位置索引（每行≈15min间隔），更鲁棒，不受盘后时间真空影响。
    若位置索引无足够数据，回退到墙钟时间查找。
    """
    steps_back = max(1, mins // 15)
    prev_row = None

    # 主逻辑：位置索引（每行≈15min间隔）
    if len(history_df) > steps_back:
        prev_row = history_df.iloc[-steps_back]
    # 回退：墙钟时间
    if prev_row is None:
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


def calc_liquidity_score(chg_15: Dict[str, Optional[float]]) -> Tuple[int, str]:
    score = 0
    # 分值越高，流动性越差
    rules = [
        ("UUP", lambda x: x is not None and x > 0, 12),   # 美元走强
        ("SHY", lambda x: x is not None and x < 0, 8),    # 短端债承压
        ("TLT", lambda x: x is not None and x < 0, 10),   # 长端债承压
        ("HYG", lambda x: x is not None and x < 0, 12),   # 信用承压
        ("JNK", lambda x: x is not None and x < 0, 10),
        ("SPY", lambda x: x is not None and x < 0, 12),   # 股市风险偏好下行
        ("IWM", lambda x: x is not None and x < 0, 8),    # 小盘更弱
        ("GLD", lambda x: x is not None and x < 0, 8),    # 黄金也跌 -> 现金化抛售风险
        ("USO", lambda x: x is not None and x > 0.5, 5),  # 油冲击
        ("DBC", lambda x: x is not None and x > 0.3, 5),  # 再通胀/成本冲击
    ]
    for k, fn, w in rules:
        if fn(chg_15.get(k)):
            score += w
    score = max(0, min(100, score))

    if score >= 75:
        state = "FAST LIQUIDITY SHOCK"
    elif score >= 60:
        state = "LIQUIDITY TIGHTENING"
    elif score >= 45:
        state = "CAUTION"
    elif score >= 30:
        state = "WATCH"
    else:
        state = "NORMAL"
    return score, state


def calc_regime(chg_15: Dict[str, Optional[float]]) -> str:
    gold = chg_15.get("GLD")
    uup = chg_15.get("UUP")
    tip = chg_15.get("TIP")
    tlt = chg_15.get("TLT")
    uso = chg_15.get("USO")
    dbc = chg_15.get("DBC")
    spy = chg_15.get("SPY")
    qqq = chg_15.get("QQQ")
    hyg = chg_15.get("HYG")

    dollar_strong = uup is not None and uup > 0
    risk_off = (spy is not None and spy < 0) and (qqq is not None and qqq < 0)
    credit_stress = hyg is not None and hyg < 0

    if gold is not None and gold < 0 and dollar_strong and (risk_off or credit_stress):
        return "Cash Liquidation"

    if gold is not None and gold < 0 and dollar_strong and (tip is not None and tip < 0):
        return "Rates-Dollar Bearish Gold"

    if gold is not None and gold > 0 and (tip is not None and tip > 0) and (uup is not None and uup <= 0):
        return "Clean Bullish Gold"

    if gold is not None and gold > 0 and (uso is not None and uso > 0) and (dbc is not None and dbc > 0):
        return "Reflation Gold"

    if gold is not None and gold > 0 and (tlt is not None and tlt < 0):
        return "Fiscal / Debasement Hedge"

    if gold is not None and gold > 0 and dollar_strong:
        return "Bullish Price Override"

    if gold is not None and gold < 0 and (tip is not None and tip > 0):
        return "Bearish Price Override"

    return "Mixed"


def recent_gold_series(history_df: pd.DataFrame, latest: Dict[str, float], limit: int = 40) -> pd.Series:
    rows: List[float] = []
    if not history_df.empty and "GLD" in history_df.columns:
        rows.extend([safe_float(v) for v in history_df["GLD"].tail(limit - 1).tolist()])
    rows = [x for x in rows if x is not None]
    if "GLD" in latest:
        rows.append(latest["GLD"])
    return pd.Series(rows, dtype="float64")


def calc_structure_scores(gold_close: pd.Series) -> Tuple[int, int, Dict[str, bool]]:
    if len(gold_close) < 12:
        return 0, 0, {"insufficient_data": True}

    c = gold_close.reset_index(drop=True)
    prev = c.shift(1)
    vwap_like = c.tail(20).mean()
    rng_high = c.tail(20).max()
    rng_low = c.tail(20).min()
    fib618 = rng_low + 0.618 * (rng_high - rng_low)
    near_fib_618 = abs(c.iloc[-1] - fib618) / c.iloc[-1] * 100 <= 0.20

    vwap_reclaim = prev.iloc[-1] <= vwap_like and c.iloc[-1] > vwap_like
    vwap_reject = prev.iloc[-1] >= vwap_like and c.iloc[-1] < vwap_like
    above_vwap = c.iloc[-1] > vwap_like
    below_vwap = c.iloc[-1] < vwap_like

    mom3 = pct_change(c.iloc[-1], c.iloc[-4]) if len(c) >= 4 else 0.0
    bullish_mom = mom3 is not None and mom3 > 0
    bearish_mom = mom3 is not None and mom3 < 0

    last5 = c.tail(5)
    higher_low = last5.iloc[-1] > last5.min()
    lower_high = last5.iloc[-1] < last5.max()

    near_top = abs(c.iloc[-1] - rng_high) / c.iloc[-1] * 100 <= 0.20
    near_bottom = abs(c.iloc[-1] - rng_low) / c.iloc[-1] * 100 <= 0.20

    long_score = 0
    long_score += 2 if vwap_reclaim else 0
    long_score += 2 if near_fib_618 and bullish_mom else 0
    long_score += 1 if above_vwap else 0
    long_score += 1 if higher_low else 0
    long_score += 2 if near_bottom and bullish_mom else 0
    long_score += 1 if bullish_mom else 0

    short_score = 0
    short_score += 2 if vwap_reject else 0
    short_score += 2 if near_fib_618 and bearish_mom else 0
    short_score += 1 if below_vwap else 0
    short_score += 1 if lower_high else 0
    short_score += 2 if near_top and bearish_mom else 0
    short_score += 1 if bearish_mom else 0

    long_score = max(0, min(10, long_score))
    short_score = max(0, min(10, short_score))
    flags = {
        "vwap_reclaim": bool(vwap_reclaim),
        "vwap_reject": bool(vwap_reject),
        "near_fib_618": bool(near_fib_618),
        "above_vwap": bool(above_vwap),
        "below_vwap": bool(below_vwap),
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
        regime in {"Clean Bullish Gold", "Reflation Gold", "Fiscal / Debasement Hedge", "Bullish Price Override"}
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
    liq_score: int,
    liq_state: str,
    trend: TrendState,
    long_score: int,
    short_score: int,
    flags: Dict[str, bool],
    advice: str,
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
        f"- 流动性评分: {liq_score}/100 ({liq_state})\n"
        f"- 15m/1h/4h 组合: {combo}\n"
        f"- 多空结构: {struct}\n"
        f"- 建议: {advice}\n"
    )


def analyze_once(history_path: Path, data_source: str = "yfinance") -> Dict[str, object]:
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

    chg_15 = get_window_change(hist, latest, ts, 15)
    chg_60 = get_window_change(hist, latest, ts, 60)
    chg_240 = get_window_change(hist, latest, ts, 240)

    regime = calc_regime(chg_15)
    liq_score, liq_state = calc_liquidity_score(chg_15)

    trend = calc_trend_state(
        gold_chg_15=chg_15.get("GLD"),
        gold_chg_60=chg_60.get("GLD"),
        gold_chg_240=chg_240.get("GLD"),
    )

    gold_series = recent_gold_series(hist, latest, limit=40)
    long_score, short_score, flags = calc_structure_scores(gold_series)

    advice = advice_by_rules(
        regime=regime,
        liq_score=liq_score,
        trend=trend,
        long_score=long_score,
        short_score=short_score,
    )

    append_snapshot(history_path, latest, ts)
    regime_guide = REGIME_GUIDE.get(regime, REGIME_GUIDE["Mixed"])

    # 把 Optional[float] 转为 float|null 便于 JSON 序列化
    def safe_chg(d: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
        return {k: (round(v, 4) if v is not None else None) for k, v in d.items()}

    return {
        "timestamp": ts.isoformat(timespec="seconds"),
        "regime": regime,
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
    if data_source == "openbb":
        hist = load_history(history_path)
        if hist.empty or len(hist) < 20:
            print("[INFO] 历史样本不足，先执行 openbb 历史预热...")
            bootstrap_history_with_openbb(history_path)
    elif data_source == "yfinance":
        hist = load_history(history_path)
        if hist.empty or len(hist) < 20:
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
                    liq_score=result["liquidity_score"],
                    liq_state=result["liquidity_state"],
                    trend=TrendState(trend["15m"], trend["1h"], trend["4h"]),
                    long_score=structure["long_score"],
                    short_score=structure["short_score"],
                    flags=structure["flags"],
                    advice=f"{result['regime_guide']} | {result['advice']}",
                )
                print(report)
        except Exception as e:
            print(f"[ERROR] {datetime.now().strftime('%F %T')} 监控失败: {e}")

        if once:
            return

        time.sleep(max(1, interval_minutes) * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="黄金宝宝巴士监控器（yfinance主数据源）")
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="轮询间隔（分钟），默认 15",
    )
    parser.add_argument(
        "--history-file",
        type=str,
        default="gold_bus_history.csv",
        help="本地快照文件路径，默认 gold_bus_history.csv",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只执行一次",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 输出",
    )
    parser.add_argument(
        "--data-source",
        type=str,
        default="yfinance",
        choices=["openbb", "yfinance", "demo"],
        help="数据源: yfinance(默认) / openbb / demo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    history_path = Path(args.history_file).expanduser().resolve()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"[INFO] 启动监控: interval={args.interval}m, history={history_path}, once={args.once}"
    )
    run_loop(history_path, args.interval, args.once, args.json, args.data_source)


if __name__ == "__main__":
    main()

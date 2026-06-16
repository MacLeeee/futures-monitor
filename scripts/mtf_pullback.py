#!/usr/bin/env python3
# ============================================================
# H-005 MTF Pullback — 多周期结构回踩状态机
#
# 状态机: IDLE → ARMED(等回踩) → QUALIFYING(质量审查) → TRIGGER_WAIT → SIGNAL
#
# 用法（在 fetch_and_calc.py 中集成）:
#   from mtf_pullback import evaluate, get_default_config
#   sig = evaluate(symbol, df_daily, df_30m, macd_15m, vol_15m,
#                  daily_entry=d_entry, cfg=get_default_config())
#
# 依赖: pandas numpy tet_indicators (TET三元组)
# ============================================================

from __future__ import annotations

import numpy as np
import pandas as pd

from tet_indicators import compute_tet_context


# ── 默认参数表 ─────────────────────────────────────────────────
def get_default_config() -> dict:
    return {
        "zone_tol_atr30":   0.3,
        "zone_tol_atr_d":   0.5,
        "overheat_atr_d":   2.0,
        "max_retrace":      0.618,
        "shrink_ratio":     0.8,
        "max_oi_increase":  3.0,
        "min_pb_bars":      2,
        "max_pb_bars":      20,
        "trigger_wait":     8,
        "stop_buffer_atr":  0.5,
        "swing_lookback":   5,

        # TET 闸门
        "use_tet":          True,
        "ats_min":          0.30,
        "ei_washout":       0.30,
        "ti_entry":         0.50,
        "trend_score_version": 2,
        "tet_variant":      "V1",

        # 结构性增强 (H-007)
        "fib_zones":        True,
        "sweep_trigger":    True,
        "sweep_pierce_atr": 0.1,
    }


# ── 工具 ──────────────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return 0.0
    h, l, c = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return float(tr.iloc[-period:].mean())


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def find_last_swing_high(df: pd.DataFrame, lookback: int) -> tuple[int, float] | None:
    h = df["high"].astype(float).values
    n = len(h)
    for i in range(n - lookback - 1, lookback - 1, -1):
        if all(h[i] >= h[i - j] for j in range(1, lookback + 1)) and \
           all(h[i] >= h[i + j] for j in range(1, min(lookback, n - 1 - i) + 1)):
            return i, float(h[i])
    return None


def find_leg_low_before(df: pd.DataFrame, swing_idx: int, lookback: int = 60) -> tuple[int, float]:
    lo = df["low"].astype(float).iloc[max(0, swing_idx - lookback):swing_idx + 1]
    return int(lo.idxmin()), float(lo.min())


# ── 状态机各阶段 ──────────────────────────────────────────────

def daily_trend_filter(daily_entry: dict | None, df_daily: pd.DataFrame | None,
                       close: float, cfg: dict) -> dict | None:
    """
    状态0: 日线趋势过滤。返回 {"direction": "long"/"short", "atrD","emaD20"} 或 None。
    """
    if df_daily is None or len(df_daily) < 70:
        return None
    c = df_daily["close"].astype(float)
    e20, e60 = ema(c, 20), ema(c, 60)
    s20 = float(e20.iloc[-1] - e20.iloc[-4])
    s60 = float(e60.iloc[-1] - e60.iloc[-4])
    atr_d = atr(df_daily)
    if atr_d <= 0:
        return None

    bull = float(e20.iloc[-1]) > float(e60.iloc[-1]) and s20 > 0 and s60 > 0
    bear = float(e20.iloc[-1]) < float(e60.iloc[-1]) and s20 < 0 and s60 < 0

    if not bull and not bear:
        return None
    if abs(close - float(e20.iloc[-1])) > cfg["overheat_atr_d"] * atr_d:
        return None
    return {"direction": "long" if bull else "short",
            "atrD": round(atr_d, 4), "emaD20": round(float(e20.iloc[-1]), 4)}


def pullback_zones(direction: str, df_30m: pd.DataFrame, ema_d20: float,
                   atr_30: float, atr_d: float,
                   breakout_level: float | None = None,
                   cfg: dict | None = None) -> list[dict]:
    """状态1: 回踩目标区列表（按优先级）。"""
    if cfg is None:
        cfg = {}
    zones = []
    if breakout_level:
        zones.append({"name": "breakout_retest", "level": breakout_level,
                      "tol": cfg.get("zone_tol_atr30", 0.3) * atr_30})
    piv = _broken_pivot(direction, df_30m, cfg)
    if piv:
        zones.append({"name": "pivot_retest", "level": piv,
                      "tol": cfg.get("zone_tol_atr30", 0.3) * atr_30})
    zones.append({"name": "daily_ema20", "level": ema_d20,
                  "tol": cfg.get("zone_tol_atr_d", 0.5) * atr_d})
    return zones


def _broken_pivot(direction: str, df: pd.DataFrame, cfg: dict) -> float | None:
    lb = cfg.get("swing_lookback", 5)
    close = float(df["close"].iloc[-1])
    if direction == "long":
        sw = find_last_swing_high(df.iloc[:-1], lb)
        if sw and close > sw[1]:
            return sw[1]
    else:
        l = df["low"].astype(float).values
        n = len(l)
        for i in range(n - lb - 2, lb - 1, -1):
            if all(l[i] <= l[i - j] for j in range(1, lb + 1)) and \
               all(l[i] <= l[i + j] for j in range(1, min(lb, n - 2 - i) + 1)):
                if close < l[i]:
                    return float(l[i])
                break
    return None


def qualify_pullback(direction: str, df_30m: pd.DataFrame, cfg: dict) -> dict | None:
    """
    状态2: 识别并审查最近一段回调。
    返回 {"pbBars","retrace","volRatio","oiChgPct","pbExtreme","swingPx","legBase"} 或 None。
    """
    n = len(df_30m)
    if n < 30:
        return None
    h = df_30m["high"].astype(float)
    l = df_30m["low"].astype(float)
    v = df_30m["volume"].astype(float)
    oi = pd.to_numeric(df_30m.get("open_interest"), errors="coerce") \
        if "open_interest" in df_30m.columns else None

    if direction == "long":
        sw = find_last_swing_high(df_30m, cfg.get("swing_lookback", 5))
        if not sw:
            return None
        sw_idx, sw_px = sw
        pb = df_30m.iloc[sw_idx + 1:]
        pb_bars = len(pb)
        if not (cfg["min_pb_bars"] <= pb_bars <= cfg["max_pb_bars"]):
            return None
        pb_low = float(pb["low"].min())
        leg_lo_idx, leg_lo = find_leg_low_before(df_30m, sw_idx)
        leg = sw_px - leg_lo
        leg_base = leg_lo
        if leg <= 0:
            return None
        retrace = (sw_px - pb_low) / leg
        if retrace > cfg["max_retrace"]:
            return None
        up_vol = float(v.iloc[leg_lo_idx:sw_idx + 1].mean())
        pb_vol = float(pb["volume"].mean())
        extreme = pb_low
    else:
        # 空头: 找分型低点, 价格反抽
        lows = l.values
        lb = cfg.get("swing_lookback", 5)
        sw_idx = None
        for i in range(n - lb - 1, lb - 1, -1):
            if all(lows[i] <= lows[i - j] for j in range(1, lb + 1)) and \
               all(lows[i] <= lows[i + j] for j in range(1, min(lb, n - 1 - i) + 1)):
                sw_idx = i
                break
        if sw_idx is None:
            return None
        sw_px = float(lows[sw_idx])
        pb = df_30m.iloc[sw_idx + 1:]
        pb_bars = len(pb)
        if not (cfg["min_pb_bars"] <= pb_bars <= cfg["max_pb_bars"]):
            return None
        pb_high = float(pb["high"].max())
        hi = h.iloc[max(0, sw_idx - 60):sw_idx + 1]
        leg_hi_idx, leg_hi = int(hi.idxmax()), float(hi.max())
        leg = leg_hi - sw_px
        leg_base = leg_hi
        if leg <= 0:
            return None
        retrace = (pb_high - sw_px) / leg
        if retrace > cfg["max_retrace"]:
            return None
        up_vol = float(v.iloc[leg_hi_idx:sw_idx + 1].mean())
        pb_vol = float(pb["volume"].mean())
        extreme = pb_high

    if up_vol <= 0:
        return None
    vol_ratio = pb_vol / up_vol
    if vol_ratio > cfg["shrink_ratio"]:
        return None

    oi_chg = 0.0
    if oi is not None and len(pb) >= 2:
        o0, o1 = float(oi.iloc[sw_idx]), float(oi.iloc[-1])
        if o0 > 0:
            oi_chg = (o1 - o0) / o0 * 100
            if oi_chg > cfg["max_oi_increase"]:
                return None

    return {"pbBars": pb_bars, "retrace": round(retrace, 3),
            "volRatio": round(vol_ratio, 3), "oiChgPct": round(oi_chg, 2),
            "pbExtreme": round(extreme, 4),
            "swingPx": round(sw_px, 4),
            "legBase": round(leg_base, 4)}


def fib_zones(direction: str, q: dict, atr_30: float, cfg: dict) -> list[dict]:
    if not cfg.get("fib_zones"):
        return []
    leg = abs(q["swingPx"] - q["legBase"])
    if leg <= 0:
        return []
    out = []
    tol = cfg.get("zone_tol_atr30", 0.3) * atr_30
    for f in (0.382, 0.5, 0.618):
        level = (q["swingPx"] - f * leg) if direction == "long" else (q["swingPx"] + f * leg)
        out.append({"name": f"fib_{f}", "level": round(level, 4), "tol": tol})
    return out


def in_zone(price_extreme: float, zones: list[dict]) -> dict | None:
    for z in zones:
        if abs(price_extreme - z["level"]) <= z["tol"]:
            return z
    return None


def detect_sweep(direction: str, df_30m: pd.DataFrame, q: dict,
                 atr_30: float, cfg: dict) -> bool:
    """
    扫损收回（H-007 最高级触发）：
    多头：回调段末端某根K插破段内前低 ≥0.1×ATR 后，最新收盘收回该低点上方；
         扫损K需放量（>近20根均量）。空头镜像。
    """
    if not cfg.get("sweep_trigger"):
        return False
    seg = df_30m.iloc[-(q["pbBars"] + 1):]
    if len(seg) < 3:
        return False
    vol_ma20 = float(df_30m["volume"].iloc[-20:].mean())
    last_close = float(seg["close"].iloc[-1])
    pierce = cfg.get("sweep_pierce_atr", 0.1) * atr_30

    for k in (1, 2):
        if len(seg) <= k + 1:
            break
        bar = seg.iloc[-k]
        prior = seg.iloc[:-k]
        if direction == "long":
            ref = float(prior["low"].min())
            swept = float(bar["low"]) < ref - pierce and last_close > ref
        else:
            ref = float(prior["high"].max())
            swept = float(bar["high"]) > ref + pierce and last_close < ref
        if swept and float(bar["volume"]) > vol_ma20:
            return True
    return False


def check_trigger(direction: str, df_30m: pd.DataFrame,
                  macd_15m: dict, vol_15m: dict) -> bool:
    """状态3: 右侧触发。结构+MACD模式。"""
    c = df_30m["close"].astype(float)
    e20 = ema(c, 20)
    close = float(c.iloc[-1])
    prev_high = float(df_30m["high"].iloc[-2])
    prev_low = float(df_30m["low"].iloc[-2])

    vol_ok = (vol_15m.get("status") == "Surge"
              and (vol_15m.get("aboveVolMa") or vol_15m.get("prevAboveVolMa")))
    if direction == "long":
        structure = close > float(e20.iloc[-1]) or close > prev_high
        macd_ok = macd_15m.get("sign") == "positive" and macd_15m.get("rapidExpanding")
    else:
        structure = close < float(e20.iloc[-1]) or close < prev_low
        macd_ok = macd_15m.get("sign") == "negative" and macd_15m.get("rapidExpanding")
    return structure and macd_ok and vol_ok


# ── 顶层评估 ─────────────────────────────────────────────────

def evaluate(symbol: str, df_daily: pd.DataFrame, df_30m: pd.DataFrame,
             macd_15m: dict, vol_15m: dict,
             daily_entry: dict | None = None,
             breakout_level: float | None = None,
             cfg: dict | None = None) -> dict | None:
    """
    全状态机一次通过式评估。满足全部条件返回信号 dict，否则 None。

    信号 dict:
      signal, symbol, type, trigger, zone, zoneLevel,
      entry, stopLoss, riskPct, quality, tet, time
    """
    if cfg is None:
        cfg = get_default_config()

    close = float(df_30m["close"].iloc[-1])
    trend = daily_trend_filter(daily_entry, df_daily, close, cfg)
    if not trend:
        return None
    direction = trend["direction"]

    atr_30 = atr(df_30m)
    if atr_30 <= 0:
        return None
    q = qualify_pullback(direction, df_30m, cfg)
    if not q:
        return None
    zones_base = pullback_zones(direction, df_30m, trend["emaD20"],
                                atr_30, trend["atrD"], breakout_level, cfg)
    zones = zones_base[:-1] + fib_zones(direction, q, atr_30, cfg) + zones_base[-1:]
    z = in_zone(q["pbExtreme"], zones)
    if not z:
        return None

    # ── 状态3 触发 ──
    if detect_sweep(direction, df_30m, q, atr_30, cfg):
        trigger_type = "sweep"
    elif check_trigger(direction, df_30m, macd_15m, vol_15m):
        trigger_type = "structure_macd"
    else:
        return None

    # ── TET 闸门 ──
    tet: dict | None = None
    if cfg.get("use_tet"):
        ctx = compute_tet_context(df_daily, df_30m,
                                  score_version=cfg.get("trend_score_version", 2),
                                  variant=cfg.get("tet_variant", "V1"))
        ei = ctx["eiSeries"]
        ats, ti = ctx["ats"], ctx["ti"]
        pb_window = min(q["pbBars"] + 1, len(ei))
        ei_pb_min = float(ei.iloc[-pb_window:].min())
        ei_pb_max = float(ei.iloc[-pb_window:].max())
        if direction == "long":
            if ats < cfg["ats_min"]:
                return None
            if ei_pb_min > -cfg["ei_washout"]:
                return None
            if ti < cfg["ti_entry"]:
                return None
        else:
            if ats > -cfg["ats_min"]:
                return None
            if ei_pb_max < cfg["ei_washout"]:
                return None
            if ti > -cfg["ti_entry"]:
                return None
        tet = {"ats": ats, "trendNow": ctx["trendNow"], "eiNow": ctx["eiNow"],
               "eiPbExtreme": round(ei_pb_min if direction == "long" else ei_pb_max, 4),
               "ti": ti,
               "variant": cfg.get("tet_variant", "V1"),
               "allVariants": ctx["variants"]}

    if direction == "long":
        stop = q["pbExtreme"] - cfg["stop_buffer_atr"] * atr_30
        risk = close - stop
    else:
        stop = q["pbExtreme"] + cfg["stop_buffer_atr"] * atr_30
        risk = stop - close
    if risk <= 0:
        return None

    return {
        "signal":     "mtf_pullback",
        "symbol":     symbol,
        "type":       direction,
        "trigger":    trigger_type,
        "zone":       z["name"],
        "zoneLevel":  round(z["level"], 4),
        "entry":      round(close, 4),
        "stopLoss":   round(stop, 4),
        "riskPct":    round(risk / close * 100, 3),
        "quality":    q,
        "tet":        tet,
        "time":       str(df_30m["time"].iloc[-1]) if "time" in df_30m.columns
                      else pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    }

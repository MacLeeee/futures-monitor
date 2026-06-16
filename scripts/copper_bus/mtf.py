"""
mtf.py — 铜多周期状态机 + 危险评分(移植 Copper_MTF_StateMachine.pine)

compute_trend_state(close): 单周期趋势 1/0/-1(EMA21/55 + RSI14)
compute_danger(...): 0-100 危险评分 + regime + action
"""
from __future__ import annotations
import math
import pandas as pd
import numpy as np


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def compute_trend_state(close: pd.Series | None,
                        ema_fast=21, ema_slow=55, rsi_len=14,
                        bull_rsi=55.0, bear_rsi=45.0) -> int:
    if close is None or len(close) < max(ema_slow, rsi_len) + 2:
        return 0
    c = close.iloc[-1]
    ef = ema(close, ema_fast).iloc[-1]
    es = ema(close, ema_slow).iloc[-1]
    r = rsi(close, rsi_len).iloc[-1]
    if any(pd.isna(x) for x in (c, ef, es, r)):
        return 0
    if c > ef and ef > es and r > bull_rsi:
        return 1
    if c < ef and ef < es and r < bear_rsi:
        return -1
    return 0


def _ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def compute_danger(states: dict, f: dict, th: float = 0.05) -> dict:
    g = f.get
    stFast, stMid, stSlow = states.get("fast", 0), states.get("mid", 0), states.get("slow", 0)
    bullCount = sum(1 for v in (stFast, stMid, stSlow) if v == 1)
    bearCount = sum(1 for v in (stFast, stMid, stSlow) if v == -1)

    cu = g("copper"); gold = g("gold")
    rRatio = (cu - gold) if (_ok(cu) and _ok(gold)) else math.nan
    copx = g("copx")

    def up(x): return _ok(x) and x > th
    def dn(x): return _ok(x) and x < -th

    dxyUp = up(g("dxy")); frontUp = up(g("us05y")); longUp = up(g("us10y"))
    ratioDown = dn(rRatio); ratioUp = up(rRatio)
    chinaWeak = dn(g("fxi")); cnhStress = up(g("usdcnh")); clpWeak = up(g("usdclp"))
    oilWeak = dn(g("oil")); esWeak = dn(g("es"))
    cuWeak = dn(cu); cuStrong = up(cu)
    copxLag = _ok(copx) and _ok(cu) and copx < cu and copx < -th
    creditStress = dn(g("hyg")); volStress = up(g("vix"))
    backwardation = _ok(g("term_spread")) and g("term_spread") > 0

    danger = 0
    danger += 10 if dxyUp else 0
    danger += 8 if frontUp else 0
    danger += 7 if longUp else 0
    danger += 12 if ratioDown else 0
    danger += 12 if chinaWeak else 0
    danger += 8 if cnhStress else 0
    danger += 5 if oilWeak else 0
    danger += 5 if esWeak else 0
    danger += 4 if clpWeak else 0
    danger += 4 if (not backwardation) else 0
    danger += 4 if copxLag else 0
    danger += 6 if creditStress else 0
    danger += 5 if volStress else 0
    danger += 20 if bearCount == 3 else 12 if bearCount == 2 else 5 if bearCount == 1 else 0
    danger = min(danger, 100)

    cyclicalExpansion = stFast == 1 and stMid == 1 and stSlow == 1 and ratioUp and not dxyUp
    supplySqueeze = backwardation and cuStrong
    chinaScare = chinaWeak and cnhStress and cuWeak
    growthScare = dxyUp and ratioDown and cuWeak
    if danger >= 60:
        regime = "LIQUIDITY / RISK-OFF"
    elif cyclicalExpansion:
        regime = "CYCLICAL EXPANSION"
    elif supplySqueeze:
        regime = "SUPPLY SQUEEZE"
    elif chinaScare:
        regime = "CHINA DEMAND SCARE"
    elif growthScare:
        regime = "GROWTH SCARE"
    elif bullCount >= 2 and danger < 45:
        regime = "COPPER BULLISH"
    elif bearCount >= 2:
        regime = "COPPER BEARISH"
    else:
        regime = "MIXED / WAIT"

    if danger >= 75:
        action = "Cut trading risk now"
    elif danger >= 60:
        action = "Reduce risk"
    elif stFast == 1 and stMid == 1 and stSlow == 1 and danger < 45:
        action = "Hold / add on pullback"
    elif stFast == -1 and stMid == 1 and stSlow == 1:
        action = "Take profit, don't short early"
    elif stFast == 1 and stMid == -1 and stSlow == -1:
        action = "Bounce only, wait to short"
    elif stFast == -1 and stMid == -1 and stSlow == -1:
        action = "Short trend / defensive"
    elif bullCount >= 2 and danger < 45:
        action = "Bull bias"
    elif bearCount >= 2:
        action = "Bear bias"
    else:
        action = "Wait"

    danger_state = ("SHOCK" if danger >= 75 else "HIGH" if danger >= 60
                    else "CAUTION" if danger >= 45 else "WATCH" if danger >= 30 else "LOW")

    return {
        "danger": danger, "danger_state": danger_state,
        "regime": regime, "action": action,
        "states": {"fast": stFast, "mid": stMid, "slow": stSlow},
        "bull_count": bullCount, "bear_count": bearCount,
    }

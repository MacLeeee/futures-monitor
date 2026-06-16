"""
regime.py — 铜状态机第一层(主题打分 → 主导排序 → 价格 override → DO/DON'T)

忠实移植 Copper_Regime_Machine v2 的 Pine 逻辑,NaN 安全:任何缺失特征不计分、不报错。
"""
from __future__ import annotations
import math


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))

def gt(x, th=0.0) -> bool:
    return _ok(x) and x > th

def lt(x, th=0.0) -> bool:
    return _ok(x) and x < th

def ge(x, th=0.0) -> bool:
    return _ok(x) and x >= th

def le(x, th=0.0) -> bool:
    return _ok(x) and x <= th


def compute_regime(f: dict) -> dict:
    g = f.get

    cu   = g("copper");  gold = g("gold");  alu = g("alu")
    ratioChg    = (cu - gold) if (_ok(cu) and _ok(gold)) else math.nan
    aluRatioChg = (cu - alu)  if (_ok(cu) and _ok(alu))  else math.nan
    y10Pressure  = g("us10y")
    realPressure = -g("tip") if _ok(g("tip")) else math.nan
    term_spread  = g("term_spread")
    inv_trend    = g("inv_trend")
    cross_prem   = g("cross_premium")

    cuUp = gt(cu); cuDown = lt(cu)
    ratioUp = gt(ratioChg); ratioDown = lt(ratioChg)
    cuBeatsAlu = gt(aluRatioChg)
    copperResilient = ge(cu, 0.0) and lt(g("es"))
    utilStrong = gt(g("xlu")); gridStrong = gt(g("grid"))
    crossExPremium = gt(cross_prem); crossExDiscount = lt(cross_prem)
    backwardation = gt(term_spread)
    destocking = gt(inv_trend)
    restocking = lt(inv_trend)
    realTightening = gt(realPressure); realRelief = lt(realPressure)
    dollarStrong = gt(g("dxy")) and lt(g("eurusd"))
    dollarRelief = lt(g("dxy")) and gt(g("eurusd"))
    cnhStress = gt(g("usdcnh"))
    producerFXWeak = gt(g("usdclp")); producerFXStrong = lt(g("usdclp"))
    growthFXStrong = gt(g("audusd"))
    reflation = gt(g("oil")) and gt(g("dbc")) and gt(cu)
    chinaBid = gt(g("fxi")) and gt(g("kweb")) and le(g("usdcnh"))
    chinaWeak = lt(g("fxi")) and lt(g("kweb"))
    copxChg = g("copx")
    minersLead = _ok(copxChg) and _ok(cu) and copxChg > cu and copxChg > 0
    minersLag  = _ok(copxChg) and _ok(cu) and copxChg < cu and copxChg < 0
    riskOn = gt(g("es")) and gt(g("nq"))
    riskOff = lt(g("es")) and lt(g("nq"))
    creditStress = lt(g("hyg"))
    volStress = gt(g("vix")) or gt(g("move"))
    globalDollarPressure = dollarStrong and (cnhStress or producerFXWeak)
    cashLiquidation = cuDown and globalDollarPressure and (riskOff or creditStress)
    easing = lt(g("us05y"))

    s = {}
    s["Structural Demand"] = (2*cuBeatsAlu + 2*copperResilient + 1*utilStrong
                              + 1*gridStrong + 1*minersLead)
    s["Growth / Reflation"] = (2*reflation + 2*ratioUp + 1*gt(g("oil"))
                               + 1*growthFXStrong + 2*cuUp)
    s["China Demand"] = (2*chinaBid + 1*gt(g("fxi")) + 1*le(g("usdcnh"))
                         + 1*gt(g("a50")) + 2*cuUp)
    s["Supply Squeeze"] = (2*backwardation + 1*destocking + 1*minersLead
                           + 1*producerFXStrong + 1*crossExPremium + 2*cuUp)
    s["Weak Dollar"] = (2*dollarRelief + 1*producerFXStrong + 1*realRelief + 2*cuUp)
    s["Risk-On Growth"] = (2*riskOn + 1*ratioUp + 1*(not creditStress) + 1*cuUp)
    s["Easing / Relief"] = (1*easing + 1*realRelief + 1*le(g("dxy")) + 2*cuUp)

    s["Growth Scare"] = (2*riskOff + 2*ratioDown + 1*chinaWeak + 2*cuDown)
    s["Dollar+Rates"] = (2*realTightening + 2*dollarStrong + 1*gt(y10Pressure) + 2*cuDown)
    s["Cash Liquidation"] = (4*cashLiquidation + 1*globalDollarPressure + 1*riskOff
                             + 1*creditStress + 1*cuDown)
    s["China Slowdown"] = (2*chinaWeak + 1*cnhStress + 1*producerFXWeak + 2*cuDown)
    s["Supply Glut"] = (1*(not backwardation) + 1*restocking + 1*minersLag
                        + 1*crossExDiscount + 2*cuDown)

    bull_keys = ["Structural Demand", "Growth / Reflation", "China Demand",
                 "Supply Squeeze", "Weak Dollar", "Risk-On Growth", "Easing / Relief"]
    bear_keys = ["Growth Scare", "Dollar+Rates", "Cash Liquidation",
                 "China Slowdown", "Supply Glut"]

    bull_max = max(s[k] for k in bull_keys)
    bear_max = max(s[k] for k in bear_keys)

    def _dom(keys, mx):
        if mx <= 0:
            return "None"
        for k in keys:
            if s[k] == mx:
                return k
        return "None"

    dominantBull = _dom(["Structural Demand", "Growth / Reflation", "China Demand",
                         "Supply Squeeze", "Weak Dollar", "Risk-On Growth", "Easing / Relief"], bull_max)
    dominantBear = _dom(["Cash Liquidation", "Growth Scare", "Dollar+Rates",
                         "China Slowdown", "Supply Glut"], bear_max)

    if cuUp and bull_max >= bear_max - 1:
        dominant = dominantBull
    elif cuDown and bear_max >= bull_max - 1:
        dominant = dominantBear
    elif cuUp and bear_max > bull_max:
        dominant = "Copper Rising vs Bearish Pressure"
    elif cuDown and bull_max > bear_max:
        dominant = "Copper Falling Despite Bullish Support"
    elif bull_max > bear_max:
        dominant = dominantBull
    elif bear_max > bull_max:
        dominant = dominantBear
    else:
        dominant = "Mixed / No Edge"

    if cuUp and bear_max > 0:
        secondary = dominantBear
    elif cuDown and bull_max > 0:
        secondary = dominantBull
    elif bull_max > bear_max and bear_max > 0:
        secondary = dominantBear
    elif bear_max > bull_max and bull_max > 0:
        secondary = dominantBull
    else:
        secondary = "None"

    REG = {
        "Cash Liquidation": ("Cash Liquidation", "red",
            "减杠杆,等强制抛售出清后再找多", "别把抢现金式抛售当需求转弱去抄底"),
        "Structural Demand": ("Structural Bull Copper", "green",
            "结构性买盘(AI/电网),回调买入", "别只用中美PMI判铜,会踏空"),
        "Growth / Reflation": ("Cyclical Bull Copper", "green",
            "顺势做多/回调买入,需油+工业金属确认", "别在美元/真实利率反转时还追多"),
        "Risk-On Growth": ("Cyclical Bull Copper", "green",
            "顺势做多,确认风险偏好", "别在美元/真实利率反转时还追多"),
        "China Demand": ("China-Driven Bull", "green",
            "持多,盯FXI/KWEB/A50与人民币", "别忽略人民币突然走贬"),
        "Supply Squeeze": ("Supply-Driven Bull", "green",
            "持多,盯back结构/跨市溢价/矿企", "别只因宏观弱就空现货紧的铜"),
        "Weak Dollar": ("Macro-Relief Copper", "green",
            "可做多,确认增长侧未走弱", "别把弱美元当唯一理由"),
        "Easing / Relief": ("Macro-Relief Copper", "green",
            "可做多,确认增长侧未走弱", "别把宽松当唯一理由"),
        "Growth Scare": ("Demand-Bearish Copper", "red",
            "减多/观望,优先做空铜或顺周期", "别在增长恐慌+铜跑输金时抄底"),
        "China Slowdown": ("Demand-Bearish Copper", "red",
            "减多/观望", "别在中国走弱+人民币贬时抄底"),
        "Dollar+Rates": ("Rates-Dollar Bearish Copper", "red",
            "减多/等待", "别在美元+真实利率双升时加多"),
        "Supply Glut": ("Supply-Bearish Copper", "orange",
            "结构转contango/累库,逢高减多", "别在库存回流时硬扛多单"),
        "Copper Rising vs Bearish Pressure": ("Bullish Price Override", "green",
            "尊重价格,空方未掌控", "别把美元压力当主导力量"),
        "Copper Falling Despite Bullish Support": ("Bearish Price Override", "red",
            "尊重弱势,支撑尚未生效", "别在价格确认反转前加多"),
        "Mixed / No Edge": ("Mixed", "gray", "等更干净的确认", "别硬讲一个铜的故事"),
    }
    regime, color, do, dont = REG.get(dominant, ("Mixed", "gray", "等更干净的确认", "别硬讲一个铜的故事"))

    return {
        "regime": regime, "color": color,
        "dominant": dominant, "secondary": secondary,
        "bull_max": int(bull_max), "bear_max": int(bear_max),
        "bias": int(bull_max - bear_max),
        "scores": {k: int(v) for k, v in s.items()},
        "do": do, "dont": dont,
        "derived": {
            "copper%": cu, "copper/gold%": ratioChg, "copper/alu%": aluRatioChg,
            "term_spread": term_spread, "inv_trend": inv_trend, "cross_premium": cross_prem,
            "dxy%": g("dxy"), "real_pressure": realPressure, "usdcnh%": g("usdcnh"),
        },
    }

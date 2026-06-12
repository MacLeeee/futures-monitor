#!/usr/bin/env python3
# ============================================================
# TET 三元指标组（Trend-Emotion-Timing）
#
# H-006 (Emotion), H-007 (Trend Score v2.1 正交家族投票), H-008 (TI择时)
#
# 架构:
#   ATS — 锚定趋势分 (Anchor Trend Score)  [-1, +1]
#         正交家族投票 v2.1: 4族×4票=16票，弱相关指标族并行
#   EI  — 情绪指数 (Emotion Index)          [-1, +1]
#         -1=恐惧/洗仓  +1=贪婪/FOMO  0=中性
#   TI  — 择时指标 = ATS - EI
#         趋势强度扣除情绪阻力后的净动力
#
# 变体 (variant):
#   V1 — 期货最优 (IC5≈0, IC20=-0.018最小, 翻转率8.6%)
#        标准16票等权 ATS + 标准5分量等权 EI
#   V2 — 变体2: ATS加权(结构族×1.5, 流量族×0.75) + EI双倍价偏/收盘位
#   V3 — 变体3: ATS更细粒8族×2票 + EI三倍量峰+OI分量
#         指数预实验最优, 跨资产不稳定, 已按事前规则改用V1
#
# 用法:
#   from tet_indicators import compute_tet_context
#   ctx = compute_tet_context(df_daily, df_30m, score_version=2, variant="V1")
#   ats, ei_series, ti = ctx["ats"], ctx["eiSeries"], ctx["ti"]
# ============================================================

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _tanh_scale(x: float, scale: float = 1.0) -> float:
    """tanh 压缩到 [-1, 1]，scale 控制敏感度。"""
    return float(np.tanh(x / (scale + 1e-9)))


# ═══════════════════════════════════════════════════════════════
# ATS — 锚定趋势分（正交家族投票）
# ═══════════════════════════════════════════════════════════════

def _ats_v1(df_daily: pd.DataFrame, df_30m: pd.DataFrame) -> float:
    """V1: 标准16票等权。"""
    return _ats_core(df_daily, df_30m, weights=None)


def _ats_v2(df_daily: pd.DataFrame, df_30m: pd.DataFrame) -> float:
    """V2: 结构族×1.5, 流量族×0.75。"""
    return _ats_core(df_daily, df_30m, weights={
        "trend_structure": 1.5,
        "macd": 1.0,
        "market_structure": 1.0,
        "flow": 0.75,
    })


def _ats_v3(df_daily: pd.DataFrame, df_30m: pd.DataFrame) -> float:
    """V3: 8族×2票, 更细粒。"""
    return _ats_core_v3(df_daily, df_30m)


def _ats_core(df_daily: pd.DataFrame, df_30m: pd.DataFrame,
              weights: dict | None = None) -> float:
    """
    正交家族投票 v2.1: 4族×4票=16票，每票 ∈ {-1, 0, +1}。
    总票数归一化到 [-1, 1]。
    """
    if weights is None:
        weights = {}
    c_d, h_d, l_d, v_d = (df_daily["close"].astype(float),
                           df_daily["high"].astype(float),
                           df_daily["low"].astype(float),
                           df_daily["volume"].astype(float))
    c_30, h_30, l_30, v_30 = (df_30m["close"].astype(float),
                               df_30m["high"].astype(float),
                               df_30m["low"].astype(float),
                               df_30m["volume"].astype(float))
    n_d, n_30 = len(df_daily), len(df_30m)
    if n_d < 60 or n_30 < 30:
        return 0.0

    e20_d, e60_d = ema(c_d, 20), ema(c_d, 60)
    atr_d = _atr_series(h_d, l_d, c_d, 14)

    votes: list[float] = []
    fam: list[str] = []

    # ── Family 1: 趋势结构（日线）4票 ──
    w1 = weights.get("trend_structure", 1.0)
    fam.append("trend_structure")
    # 1. EMA20 > EMA60
    votes.append(w1 * (1 if float(e20_d.iloc[-1]) > float(e60_d.iloc[-1]) else -1))
    # 2. EMA20 斜率 (5日)
    s20 = float(e20_d.iloc[-1]) - float(e20_d.iloc[-5])
    votes.append(w1 * (1 if s20 > 0 else -1))
    # 3. EMA60 斜率 (5日)
    s60 = float(e60_d.iloc[-1]) - float(e60_d.iloc[-5])
    votes.append(w1 * (1 if s60 > 0 else -1))
    # 4. 价格在 EMA20 上方 (ATR 归一化)
    dist = (float(c_d.iloc[-1]) - float(e20_d.iloc[-1])) / (float(atr_d.iloc[-1]) + 1e-9)
    votes.append(w1 * (1 if dist > 0.2 else (-1 if dist < -0.2 else 0)))

    # ── Family 2: MACD（跨周期）4票 ──
    w2 = weights.get("macd", 1.0)
    fam.append("macd")
    macd_d = _macd_diff(c_d)
    macd_30 = _macd_diff(c_30)
    # 5. 日线 MACD diff 方向
    votes.append(w2 * (1 if float(macd_d.iloc[-1]) > 0 else -1))
    # 6. 日线 MACD diff 5日斜率
    md_slope = float(macd_d.iloc[-1]) - float(macd_d.iloc[-5])
    votes.append(w2 * (1 if md_slope > 0 else -1))
    # 7. 30m MACD diff 方向
    votes.append(w2 * (1 if float(macd_30.iloc[-1]) > 0 else -1))
    # 8. 30m MACD diff 5bar 斜率
    m30_slope = float(macd_30.iloc[-1]) - float(macd_30.iloc[-5])
    votes.append(w2 * (1 if m30_slope > 0 else -1))

    # ── Family 3: 市场结构 4票 ──
    w3 = weights.get("market_structure", 1.0)
    fam.append("market_structure")
    # 9. 日线 higher high (10日窗口)
    hh10 = float(h_d.iloc[-10:].max())
    votes.append(w3 * (1 if float(h_d.iloc[-1]) >= hh10 * 0.995 else -1))
    # 10. 日线 higher low (10日窗口)
    ll10 = float(l_d.iloc[-10:].min())
    votes.append(w3 * (1 if float(l_d.iloc[-1]) > ll10 * 1.005 else -1))
    # 11. 30m 价格在 Donchian 中轴上方 (20bar)
    hh20_30 = float(h_30.iloc[-20:].max())
    ll20_30 = float(l_30.iloc[-20:].min())
    mid_30 = (hh20_30 + ll20_30) / 2
    votes.append(w3 * (1 if float(c_30.iloc[-1]) > mid_30 else -1))
    # 12. 日线收盘位 (close - low) / (high - low) 均值
    cl_daily = (c_d - l_d) / (h_d - l_d + 1e-9)
    avg_cl = float(cl_daily.iloc[-5:].mean())
    votes.append(w3 * (1 if avg_cl > 0.55 else (-1 if avg_cl < 0.45 else 0)))

    # ── Family 4: 流量（Volume/OI）4票 ──
    w4 = weights.get("flow", 1.0)
    fam.append("flow")
    v_ma_d = v_d.rolling(20).mean()
    v_ma_30 = v_30.rolling(20).mean()
    # 13. 日线量 > MA
    votes.append(w4 * (1 if float(v_d.iloc[-1]) > float(v_ma_d.iloc[-1]) else -1))
    # 14. 量在涨日扩大 vs 跌日
    up_vol = v_d[c_d.diff() > 0].iloc[-20:].mean()
    dn_vol = v_d[c_d.diff() < 0].iloc[-20:].mean()
    if pd.notna(up_vol) and pd.notna(dn_vol) and dn_vol > 0:
        votes.append(w4 * (1 if float(up_vol) > float(dn_vol) else -1))
    else:
        votes.append(0.0)
    # 15. 30m 量 > MA
    votes.append(w4 * (1 if float(v_30.iloc[-1]) > float(v_ma_30.iloc[-1]) else -1))
    # 16. 30m 成交量趋势 (5bar 斜率)
    v_trend = float(v_30.iloc[-1]) - float(v_30.iloc[-5:].mean())
    votes.append(w4 * (1 if v_trend > 0 else -1))

    total_w = sum(abs(v) for v in votes)
    return round(sum(votes) / (total_w + 1e-9), 4)


def _ats_core_v3(df_daily: pd.DataFrame, df_30m: pd.DataFrame) -> float:
    """V3: 8族×2票=16票。更细粒但也更噪。"""
    c_d, h_d, l_d, v_d = (df_daily["close"].astype(float),
                           df_daily["high"].astype(float),
                           df_daily["low"].astype(float),
                           df_daily["volume"].astype(float))
    c_30 = df_30m["close"].astype(float)
    n_d = len(df_daily)
    if n_d < 60:
        return 0.0

    e20_d, e60_d = ema(c_d, 20), ema(c_d, 60)
    macd_d = _macd_diff(c_d)
    atr_d = _atr_series(h_d, l_d, c_d, 14)

    def vote(cond: bool) -> float: return 1.0 if cond else -1.0

    # 1. EMA排列
    v1 = [vote(float(e20_d.iloc[-1]) > float(e60_d.iloc[-1])),
          vote(float(e20_d.iloc[-1]) - float(e20_d.iloc[-3]) > 0)]
    # 2. 价格位置
    dist = (float(c_d.iloc[-1]) - float(e20_d.iloc[-1])) / (float(atr_d.iloc[-1]) + 1e-9)
    v2 = [vote(dist > 0.1), vote(float(c_d.iloc[-1]) > float(c_d.iloc[-5]))]
    # 3. MACD
    v3 = [vote(float(macd_d.iloc[-1]) > 0),
          vote(float(macd_d.iloc[-1]) - float(macd_d.iloc[-3]) > 0)]
    # 4. 高低结构
    hh, ll = float(h_d.iloc[-10:].max()), float(l_d.iloc[-10:].min())
    v4 = [vote(float(h_d.iloc[-1]) >= hh * 0.99),
          vote(float(l_d.iloc[-1]) > ll * 1.01)]
    # 5. 收盘位
    cl = (c_d - l_d) / (h_d - l_d + 1e-9)
    v5 = [vote(float(cl.iloc[-1]) > 0.5),
          vote(float(cl.iloc[-5:].mean()) > 0.5)]
    # 6. 量的趋势
    v_ma = v_d.rolling(20).mean()
    v6 = [vote(float(v_d.iloc[-1]) > float(v_ma.iloc[-1])),
          vote(float(v_d.iloc[-1]) - float(v_d.iloc[-3]) > 0)]
    # 7. 波动收敛
    atr_d_10 = atr_d.iloc[-10:].mean()
    atr_d_20 = atr_d.iloc[-20:-10].mean()
    v7 = [vote(float(atr_d_10) < float(atr_d_20)),   # ATR收敛 → 蓄力
          vote(float(c_d.iloc[-1]) - float(c_d.iloc[-10]) > 0)]
    # 8. 30m辅助
    e20_30 = ema(c_30, 20)
    v8 = [vote(float(c_30.iloc[-1]) > float(e20_30.iloc[-1])),
          vote(float(c_30.iloc[-1]) - float(c_30.iloc[-5]) > 0)]

    all_votes = v1 + v2 + v3 + v4 + v5 + v6 + v7 + v8
    return round(sum(all_votes) / len(all_votes), 4)


# ═══════════════════════════════════════════════════════════════
# EI — 情绪指数（30m 逐根计算）
# ═══════════════════════════════════════════════════════════════

def _ei_v1(df_30m: pd.DataFrame) -> pd.Series:
    """V1: 标准5分量等权。"""
    return _ei_core(df_30m)


def _ei_v2(df_30m: pd.DataFrame) -> pd.Series:
    """V2: 价偏+收盘位双倍权重。"""
    return _ei_core(df_30m, weights={"dev": 2.0, "cl_loc": 2.0, "vol": 1.0,
                                      "range": 1.0, "mom": 1.0})


def _ei_v3(df_30m: pd.DataFrame) -> pd.Series:
    """V3: 量峰三倍权重。"""
    return _ei_core(df_30m, weights={"dev": 1.0, "cl_loc": 1.0, "vol": 3.0,
                                      "range": 1.0, "mom": 1.0})


def _ei_core(df_30m: pd.DataFrame, weights: dict | None = None) -> pd.Series:
    """
    5分量情绪指数, 每根30mK一个值 ∈ [-1, 1]。
    -1 = 极端恐惧/洗仓  +1 = 极端贪婪/FOMO

    分量:
      1. 价格偏离 (close-EMA20)/ATR → tanh缩放
      2. 收盘位置 (close-low)/(high-low) → 映射到[-1,1]
      3. 量峰 (vol-MA)/std → tanh缩放
      4. 波幅扩张 (range-MA)/std → tanh缩放
      5. 动量极端 5bar ROC → tanh缩放
    """
    if weights is None:
        weights = {}
    c = df_30m["close"].astype(float)
    h = df_30m["high"].astype(float)
    l = df_30m["low"].astype(float)
    v = df_30m["volume"].astype(float)
    n = len(df_30m)
    if n < 30:
        return pd.Series([0.0] * n, index=df_30m.index)

    e20 = ema(c, 20)
    atr = _atr_series(h, l, c, 14)

    # 1. 价格偏离 (正=过热, 负=恐慌)
    w1 = weights.get("dev", 1.0)
    dev_raw = (c - e20) / (atr + 1e-9)
    dev = dev_raw.apply(lambda x: _tanh_scale(x, 1.5))

    # 2. 收盘位置 (高收=贪婪, 低收=恐惧)
    w2 = weights.get("cl_loc", 1.0)
    cl_raw = 2 * (c - l) / (h - l + 1e-9) - 1   # 已在[-1,1]
    cl_loc = cl_raw

    # 3. 量峰
    w3 = weights.get("vol", 1.0)
    v_ma = v.rolling(20).mean()
    v_std = v.rolling(20).std()
    vol_raw = (v - v_ma) / (v_std + 1e-9)
    vol_sig = vol_raw.apply(lambda x: _tanh_scale(x, 2.0))

    # 4. 波幅扩张
    w4 = weights.get("range", 1.0)
    rng = h - l
    r_ma = rng.rolling(20).mean()
    r_std = rng.rolling(20).std()
    rng_raw = (rng - r_ma) / (r_std + 1e-9)
    rng_sig = rng_raw.apply(lambda x: _tanh_scale(x, 2.0))

    # 5. 动量极端 (5bar ROC)
    w5 = weights.get("mom", 1.0)
    roc5 = c.pct_change(5) * 100
    mom_sig = roc5.apply(lambda x: _tanh_scale(x, 3.0))

    total_w = w1 + w2 + w3 + w4 + w5
    ei = (w1 * dev + w2 * cl_loc + w3 * vol_sig + w4 * rng_sig + w5 * mom_sig) / total_w

    # 3-bar EMA 平滑
    return ei.ewm(span=3, adjust=False).mean().clip(-1, 1)


# ═══════════════════════════════════════════════════════════════
# 主入口: compute_tet_context
# ═══════════════════════════════════════════════════════════════

def compute_tet_context(
    df_daily: pd.DataFrame,
    df_30m: pd.DataFrame,
    score_version: int = 2,
    variant: str = "V1",
) -> dict:
    """
    计算 TET 三元组完整上下文。

    返回:
      ats:       锚定趋势分 (当前值)       [-1, +1]
      trendNow:  趋势族原始分 (正=强牛)    float
      eiSeries:  情绪指数序列 (30m逐根)    pd.Series
      eiNow:     当前情绪指数               [-1, +1]
      ti:        择时指标 = ATS - EI        float
      variants:  {V1/V2/V3: {ats,trendNow,eiNow,ti}}  全变体留痕
    """
    # ── 全变体计算（留痕 → 事后陈旧性尸检）──────────────
    ats_fns = {"V1": _ats_v1, "V2": _ats_v2, "V3": _ats_v3}
    ei_fns  = {"V1": _ei_v1, "V2": _ei_v2, "V3": _ei_v3}

    ei_cache: dict[str, pd.Series] = {}
    variants: dict[str, dict] = {}

    for v in ("V1", "V2", "V3"):
        ats_val = ats_fns[v](df_daily, df_30m)
        if v not in ei_cache:
            ei_cache[v] = ei_fns[v](df_30m)
        ei_series = ei_cache[v]
        ei_now = round(float(ei_series.iloc[-1]), 4)
        ti_val = round(ats_val - ei_now, 4)
        variants[v] = {"ats": ats_val, "trendNow": ats_val,
                        "eiNow": ei_now, "ti": ti_val}

    # ── 选中的变体 ──────────────────────────────────
    if variant not in ats_fns:
        variant = "V1"
    ats = ats_fns[variant](df_daily, df_30m)
    ei_series = ei_cache.get(variant) or ei_fns[variant](df_30m)
    ei_now = round(float(ei_series.iloc[-1]), 4)
    ti = round(ats - ei_now, 4)

    return {
        "ats": ats,
        "trendNow": ats,       # trendNow = ats（当前趋势强度即锚定分）
        "eiSeries": ei_series,
        "eiNow": ei_now,
        "ti": ti,
        "variants": variants,
    }


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _atr_series(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _macd_diff(close: pd.Series, fast: int = 12, slow: int = 26) -> pd.Series:
    return ema(close, fast) - ema(close, slow)

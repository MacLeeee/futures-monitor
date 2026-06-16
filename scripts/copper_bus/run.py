"""
run.py — 铜宝宝巴士编排:取数 → 算分 → 渲染仪表盘 → 输出 JSON

被 run_copper_bus.py 调用,也可独立运行。
"""
from __future__ import annotations
import argparse
import json
import math
import datetime as dt
import os

from . import data_sources as ds
from . import regime as rg
from . import mtf as mt

NAMES = ["copper", "gold", "alu", "oil", "dbc",
         "us10y", "us30y", "us05y", "tip",
         "dxy", "eurusd", "audusd", "usdcnh", "usdclp",
         "xlu", "grid", "copx", "fxi", "kweb", "a50",
         "es", "nq", "hyg", "vix", "move"]


def _roc_of(series, lookback):
    if series is None or len(series) <= lookback:
        return math.nan
    prev = series.iloc[-1 - lookback]
    if prev == 0 or (isinstance(prev, float) and math.isnan(prev)):
        return math.nan
    return float((series.iloc[-1] / prev - 1.0) * 100.0)


def run(interval="30m", period="60d", lookback=5) -> dict:
    """运行完整管线,返回 state dict。"""
    rocs = ds.fetch_all_roc(NAMES, lookback, interval, period)

    comex = ds._fetch_yf("HG=F", interval, period)
    shfe = ds._fetch_ak_cn_fut("CU0", interval)
    cross = math.nan
    rc, rs = _roc_of(comex, lookback), _roc_of(shfe, lookback)
    if not (math.isnan(rc) or math.isnan(rs)):
        cross = rc - rs

    term = ds.get_term_spread()
    inv = ds.get_copper_inventory_trend()

    f = dict(rocs)
    f["term_spread"] = term
    f["inv_trend"] = inv
    f["cross_premium"] = cross

    reg = rg.compute_regime(f)

    fast = ds.get_close("copper", "15m", "30d")
    mid = ds.get_close("copper", "60m", "60d")
    slow = ds.get_close("copper", "1d", "2y")
    states = {
        "fast": mt.compute_trend_state(fast),
        "mid": mt.compute_trend_state(mid),
        "slow": mt.compute_trend_state(slow),
    }
    mtf_out = mt.compute_danger(states, f)

    avail = ds.availability_report(NAMES, interval, period)

    return {
        "meta": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "interval": interval,
        },
        "regime": reg,
        "mtf": mtf_out,
        "features": f,
        "avail": avail,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="30m")
    ap.add_argument("--period", default="60d")
    ap.add_argument("--lookback", type=int, default=5)
    ap.add_argument("--out", default="state.json")
    args = ap.parse_args()

    state = run(args.interval, args.period, args.lookback)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, default=str)

    reg = state["regime"]
    mtf_out = state["mtf"]
    avail = state["avail"]
    n_ok = sum(1 for v in avail.values() if v)

    print(f"完成 → {os.path.abspath(args.out)}")
    print(f"  Regime: {reg['regime']} | Dominant: {reg['dominant']} | "
          f"Danger: {mtf_out['danger']}/100 ({mtf_out['danger_state']})")
    print(f"  数据可用: {n_ok}/{len(avail)}")


if __name__ == "__main__":
    main()

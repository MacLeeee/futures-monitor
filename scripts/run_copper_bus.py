#!/usr/bin/env python3
"""
铜宝宝巴士 - 数据采集 wrapper
25 序列 · 铜状态机 · 多周期危险评分
被 run_local.sh / cron 调用，输出 copper_bus.json 到 public/
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
PUBLIC_DIR = ROOT / "futures-monitor" / "public"
OUTPUT_FILE = PUBLIC_DIR / "copper_bus.json"

sys.path.insert(0, str(SCRIPTS_DIR))

from copper_bus.run import run as copper_run


def _sanitize(obj):
    """递归将 NaN/Inf 替换为 None，确保 JSON 合法。"""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    try:
        state = copper_run(interval="1d", period="90d", lookback=5)
        # 精简输出:只保留前端需要的字段
        reg = state["regime"]
        mtf_out = state["mtf"]
        avail = state["avail"]
        features = state["features"]
        meta = state["meta"]

        # 驱动指标(前端展示用)
        drivers = {
            "copper": features.get("copper"),
            "gold": features.get("gold"),
            "copper_gold_ratio": reg["derived"].get("copper/gold%"),
            "copper_alu_ratio": reg["derived"].get("copper/alu%"),
            "cross_premium": features.get("cross_premium"),
            "term_spread": features.get("term_spread"),
            "inv_trend": features.get("inv_trend"),
            "dxy": features.get("dxy"),
            "real_pressure": reg["derived"].get("real_pressure"),
            "us10y": features.get("us10y"),
            "usdcnh": features.get("usdcnh"),
            "usdclp": features.get("usdclp"),
            "oil": features.get("oil"),
            "copx": features.get("copx"),
            "fxi": features.get("fxi"),
            "es": features.get("es"),
            "vix": features.get("vix"),
        }

        n_ok = sum(1 for v in avail.values() if v)
        n_tot = len(avail)
        missing = [k for k, v in avail.items() if not v]

        result = _sanitize({
            "timestamp": meta["timestamp"],
            "interval": meta["interval"],
            # 状态机
            "regime": reg["regime"],
            "regime_color": reg["color"],
            "dominant_theme": reg["dominant"],
            "secondary": reg["secondary"],
            "bull_max": reg["bull_max"],
            "bear_max": reg["bear_max"],
            "bias": reg["bias"],
            "do": reg["do"],
            "dont": reg["dont"],
            "scores": reg["scores"],
            # 多周期
            "mtf_regime": mtf_out["regime"],
            "mtf_danger": mtf_out["danger"],
            "mtf_danger_state": mtf_out["danger_state"],
            "mtf_action": mtf_out["action"],
            "mtf_states": mtf_out["states"],
            # 驱动指标
            "drivers": drivers,
            # 数据可用性
            "data_ok": n_ok,
            "data_total": n_tot,
            "data_missing": missing,
        })

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[COPPER_BUS] ✓ 已写入 {OUTPUT_FILE}")
        print(f"  状态机: {reg['regime']} ({reg['dominant']})")
        print(f"  危险评分: {mtf_out['danger']}/100 ({mtf_out['danger_state']})")
        print(f"  数据: {n_ok}/{n_tot} 可用")

    except Exception as e:
        print(f"[COPPER_BUS] 失败: {e}")
        result = {
            "timestamp": "",
            "error": str(e),
            "regime": "Mixed",
            "regime_color": "gray",
            "dominant_theme": "数据获取失败",
            "secondary": "None",
            "bull_max": 0, "bear_max": 0, "bias": 0,
            "do": "等待数据恢复", "dont": "不要在数据缺失时交易",
            "scores": {},
            "mtf_regime": "N/A", "mtf_danger": 0, "mtf_danger_state": "N/A",
            "mtf_action": "Wait", "mtf_states": {"fast": 0, "mid": 0, "slow": 0},
            "drivers": {},
            "data_ok": 0, "data_total": 0, "data_missing": [],
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    sys.exit(0)


if __name__ == "__main__":
    main()

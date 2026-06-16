#!/usr/bin/env python3
"""
铜宝宝巴士 - 数据采集 wrapper
25 序列 · 铜状态机 · 多周期危险评分
被 run_local.sh / cron 调用，输出 copper_bus.json 到 public/
出现明确多/空信号时推送到 Telegram
"""
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
PUBLIC_DIR = ROOT / "futures-monitor" / "public"
OUTPUT_FILE = PUBLIC_DIR / "copper_bus.json"
STATE_FILE = SCRIPTS_DIR / ".copper_bus_last_signal"

sys.path.insert(0, str(SCRIPTS_DIR))
from copper_bus.run import run as copper_run


# ── Telegram 推送 ─────────────────────────────────────────────

def tg_send(token: str, chat_id: str, text: str, label: str = "") -> None:
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
        tag = f"[{label}] " if label else ""
        print(f"[TG] {tag}推送成功 ({len(text)} chars)")
    except Exception as e:
        print(f"[TG] {label} 推送失败: {e}")


def tg_send_all(text: str) -> int:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        tg_send(token, chat_id, text, "Bot1")
        return 1
    print("[TG] 未配置 Bot Token，跳过推送")
    return 0


def detect_signal(regime_color: str) -> str | None:
    """从 regime_color 判定信号方向。"""
    if regime_color == "green":
        return "LONG"
    if regime_color in ("red", "orange"):
        return "SHORT"
    return None


def build_telegram_message(result: dict) -> str:
    regime = result.get("regime", "?")
    color = result.get("regime_color", "gray")
    dominant = result.get("dominant_theme", "?")
    secondary = result.get("secondary", "None")
    bull_max = result.get("bull_max", 0)
    bear_max = result.get("bear_max", 0)
    danger = result.get("mtf_danger", 0)
    danger_state = result.get("mtf_danger_state", "?")
    mtf_regime = result.get("mtf_regime", "?")
    action = result.get("mtf_action", "?")
    do = result.get("do", "")
    dont = result.get("dont", "")

    if color == "green":
        sig = "🟢 铜做多"
        sig_color = "Bull"
    elif color in ("red", "orange"):
        sig = "🔴 铜做空"
        sig_color = "Bear"
    else:
        sig = "⚪ 铜中性"
        sig_color = "Neutral"

    msg = (
        f"<b>{sig} · 铜宝宝巴士</b>\n"
        f"\n"
        f"状态机: <b>{regime}</b>\n"
        f"主逻辑: {dominant}"
    )
    if secondary != "None":
        msg += f" | 次要: {secondary}"
    msg += f" (Bull={bull_max} Bear={bear_max})\n"
    msg += (
        f"MTF: <b>{mtf_regime}</b> | 危险评分 <b>{danger}/100</b> ({danger_state})\n"
        f"Action: {action}\n"
        f"\n"
        f"✅ {do}\n"
        f"❌ {dont}"
    )
    return msg


def load_last_signal() -> str | None:
    try:
        if STATE_FILE.exists():
            return STATE_FILE.read_text().strip() or None
    except Exception:
        pass
    return None


def save_last_signal(signal: str) -> None:
    try:
        STATE_FILE.write_text(signal)
    except Exception:
        pass


# ── 数据清洗 ──────────────────────────────────────────────────

def _sanitize(obj):
    """递归将 NaN/Inf 替换为 None，确保 JSON 合法。"""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


# ── 主逻辑 ────────────────────────────────────────────────────

def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    try:
        state = copper_run(interval="1d", period="90d", lookback=5)
        reg = state["regime"]
        mtf_out = state["mtf"]
        avail = state["avail"]
        features = state["features"]
        meta = state["meta"]

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
            "mtf_regime": mtf_out["regime"],
            "mtf_danger": mtf_out["danger"],
            "mtf_danger_state": mtf_out["danger_state"],
            "mtf_action": mtf_out["action"],
            "mtf_states": mtf_out["states"],
            "drivers": drivers,
            "data_ok": n_ok,
            "data_total": n_tot,
            "data_missing": missing,
        })

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        signal = detect_signal(reg["color"])

        print(f"[COPPER_BUS] ✓ 已写入 {OUTPUT_FILE}")
        print(f"  状态机: {reg['regime']} ({reg['dominant']}) — {reg['color']}")
        print(f"  危险评分: {mtf_out['danger']}/100 ({mtf_out['danger_state']})")
        print(f"  数据: {n_ok}/{n_tot} 可用")
        print(f"  信号: {signal or '无明确信号'}")

        # ── TG 推送 ──
        if signal:
            last = load_last_signal()
            if last == signal:
                print(f"[TG] 信号未变化 ({signal})，跳过推送")
            else:
                msg = build_telegram_message(result)
                tg_send_all(msg)
                save_last_signal(signal)
        else:
            last = load_last_signal()
            if last:
                print(f"[TG] 信号已消失 (上次: {last})，清除状态")
                save_last_signal("")

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

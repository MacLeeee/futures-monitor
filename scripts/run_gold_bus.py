#!/usr/bin/env python3
"""
黄金宝宝巴士 - 数据采集 wrapper
被 run_local.sh / cron 调用，输出 JSON 到 public/gold_bus.json
出现明确多/空信号时推送到 Telegram
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
PUBLIC_DIR = ROOT / "futures-monitor" / "public"
HISTORY_FILE = SCRIPTS_DIR / "gold_bus_history.csv"
OUTPUT_FILE = PUBLIC_DIR / "gold_bus.json"
STATE_FILE = SCRIPTS_DIR / ".gold_bus_last_signal"

# 确保 scripts 目录在 path 中
sys.path.insert(0, str(SCRIPTS_DIR))

from gold_bus_monitor import analyze_once, load_history, bootstrap_history_with_yfinance


# ── Telegram 推送 ─────────────────────────────────────────────

def tg_send(token: str, chat_id: str, text: str, label: str = "") -> None:
    """发送 Telegram 消息，失败不崩溃。"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
        tag = f"[{label}] " if label else ""
        print(f"[TG] {tag}推送成功 ({len(text)} chars)")
    except Exception as e:
        tag = f"[{label}] " if label else ""
        print(f"[TG] {tag}推送失败: {e}")


def tg_send_all(text: str) -> int:
    """向所有配置的 Telegram Bot 发送同一条消息。返回发送成功的 bot 数。"""
    bots = [
        (os.environ.get("TELEGRAM_BOT_TOKEN", ""),
         os.environ.get("TELEGRAM_CHAT_ID", ""),
         "Bot1"),
        (os.environ.get("TELEGRAM_BOT_TOKEN_2", ""),
         os.environ.get("TELEGRAM_CHAT_ID_2", ""),
         "Bot2"),
    ]
    sent = 0
    for token, chat_id, label in bots:
        if token and chat_id:
            tg_send(token, chat_id, text, label)
            sent += 1
    if sent == 0:
        print("[TG] 未配置任何 Bot Token，跳过推送")
    return sent


# ── 信号判定 ──────────────────────────────────────────────────

def detect_signal(advice: str) -> str | None:
    """从 advice 中提取信号方向，只在明确共振时返回。"""
    advice_lower = advice.strip()
    if advice_lower.startswith("偏多"):
        return "LONG"
    if advice_lower.startswith("偏空"):
        return "SHORT"
    return None


def build_telegram_message(result: dict) -> str:
    """构造 Telegram 推送消息。"""
    regime = result.get("regime", "?")
    liq_score = result.get("liquidity_score", 0)
    liq_state = result.get("liquidity_state", "?")
    trend = result.get("trend_15m_1h_4h", {})
    struct = result.get("structure", {})
    advice = result.get("advice", "")

    trend_str = f"{trend.get('15m','?')}/{trend.get('1h','?')}/{trend.get('4h','?')}"
    sig = "🟢 做多" if advice.startswith("偏多") else "🔴 做空"

    msg = (
        f"<b>{sig} · 黄金宝宝巴士信号</b>\n"
        f"\n"
        f"状态机: <b>{regime}</b>\n"
        f"流动性: <b>{liq_score}/100</b> ({liq_state})\n"
        f"趋势 15m/1h/4h: <b>{trend_str}</b>\n"
        f"结构: Long={struct.get('long_score',0)}/10  Short={struct.get('short_score',0)}/10\n"
        f"\n"
        f"<b>{advice}</b>"
    )
    return msg


def load_last_signal() -> str | None:
    """读上次推送的信号（防重复）。"""
    try:
        if STATE_FILE.exists():
            return STATE_FILE.read_text().strip() or None
    except Exception:
        pass
    return None


def save_last_signal(signal: str) -> None:
    """保存本次推送的信号。"""
    try:
        STATE_FILE.write_text(signal)
    except Exception:
        pass


# ── 主逻辑 ────────────────────────────────────────────────────

def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    # 首次运行：自动补齐 5 天历史数据
    hist = load_history(HISTORY_FILE)
    if hist.empty or len(hist) < 20:
        print("[GOLD_BUS] 历史样本不足，先补齐 5 天 15min K 线...")
        bootstrap_history_with_yfinance(HISTORY_FILE, lookback_days=5)
        hist = load_history(HISTORY_FILE)
        if hist.empty:
            print("[GOLD_BUS] ⚠️ 历史预热失败，本次信号可能全 Neutral")
        else:
            print(f"[GOLD_BUS] ✓ 历史预热完成: {len(hist)} 行")

    try:
        result = analyze_once(HISTORY_FILE, data_source="yfinance")
    except Exception as e:
        print(f"[GOLD_BUS] 分析失败: {e}")
        result = {
            "timestamp": "",
            "error": str(e),
            "regime": "Mixed",
            "regime_guide": "数据获取失败，请稍后刷新。",
            "liquidity_score": 0,
            "liquidity_state": "N/A",
            "trend_15m_1h_4h": {"15m": "Neutral", "1h": "Neutral", "4h": "Neutral"},
            "structure": {"long_score": 0, "short_score": 0, "flags": {}},
            "advice": "数据暂不可用",
        }

    # 写入 JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    advice = result.get("advice", "")
    signal = detect_signal(advice)

    print(f"[GOLD_BUS] ✓ 已写入 {OUTPUT_FILE}")
    print(f"  状态机: {result.get('regime', 'N/A')}")
    print(f"  流动性: {result.get('liquidity_score', 0)}/100 ({result.get('liquidity_state', 'N/A')})")
    trend = result.get("trend_15m_1h_4h", {})
    print(f"  趋势: {trend.get('15m','-')}/{trend.get('1h','-')}/{trend.get('4h','-')}")
    print(f"  信号: {signal or '无明确信号'}")

    # Telegram 推送：仅在有明确多空信号且与上次不同时推送
    if signal:
        last = load_last_signal()
        if last == signal:
            print(f"[TG] 信号未变化 ({signal})，跳过推送")
        else:
            msg = build_telegram_message(result)
            tg_send_all(msg)
            save_last_signal(signal)
    else:
        # 信号消失时清除记录（下次出现相同信号仍会推送）
        last = load_last_signal()
        if last:
            print(f"[TG] 信号已消失 (上次: {last})，清除状态")
            save_last_signal("")


if __name__ == "__main__":
    main()

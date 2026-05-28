#!/usr/bin/env python3
"""
黄金宝宝巴士 - 数据采集 wrapper
被 run_local.sh 调用，输出 JSON 到 public/gold_bus.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
PUBLIC_DIR = ROOT / "futures-monitor" / "public"
HISTORY_FILE = SCRIPTS_DIR / "gold_bus_history.csv"
OUTPUT_FILE = PUBLIC_DIR / "gold_bus.json"

# 确保 scripts 目录在 path 中
sys.path.insert(0, str(SCRIPTS_DIR))

from gold_bus_monitor import analyze_once, load_history, bootstrap_history_with_yfinance


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    # 首次运行：自动补齐 5 天历史数据，避免信号全 Neutral
    hist = load_history(HISTORY_FILE)
    if hist.empty or len(hist) < 20:
        print("[GOLD_BUS] 历史样本不足，先补齐 5 天 15min K 线...")
        bootstrap_history_with_yfinance(HISTORY_FILE, lookback_days=5)
        # 预热后重新加载，确认数据到位
        hist = load_history(HISTORY_FILE)
        if hist.empty:
            print("[GOLD_BUS] ⚠️ 历史预热失败，本次信号可能全 Neutral")
        else:
            print(f"[GOLD_BUS] ✓ 历史预热完成: {len(hist)} 行")

    try:
        result = analyze_once(HISTORY_FILE, data_source="yfinance")
    except Exception as e:
        print(f"[GOLD_BUS] 分析失败: {e}")
        # 写入错误状态，避免网页端报 404
        error_result = {
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
        result = error_result

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[GOLD_BUS] ✓ 已写入 {OUTPUT_FILE}")
    print(f"  状态机: {result.get('regime', 'N/A')}")
    print(f"  流动性: {result.get('liquidity_score', 0)}/100 ({result.get('liquidity_state', 'N/A')})")
    trend = result.get("trend_15m_1h_4h", {})
    print(f"  趋势: {trend.get('15m','-')}/{trend.get('1h','-')}/{trend.get('4h','-')}")


if __name__ == "__main__":
    main()

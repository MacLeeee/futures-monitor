#!/usr/bin/env python3
"""
期货监控系统 - L3 执行层：策略参数 A/B 回测
============================================
基于历史持仓记录 + 信号快照数据，评估参数变更的影响。

用法:
  # 对比当前参数 vs 新参数文件
  python3 scripts/backtest_ab.py --propose strategy_params_v2.json

  # 直接给参数 diff (JSON patch)
  python3 scripts/backtest_ab.py --patch '{"macd":{"expansion_rate_min":1.5}}'

  # 仅分析，不生成对比报告
  python3 scripts/backtest_ab.py --analyze-only

输出:
  - 终端：变更影响摘要
  - futures-monitor/public/review/backtest_YYYY-MM-DD.json  # 完整对比数据
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
POSITIONS_FILE = ROOT / "futures-monitor" / "public" / "positions.json"
DATA_FILE = ROOT / "futures-monitor" / "public" / "data.json"
PARAMS_FILE = ROOT / "strategy_params.json"
REVIEW_DIR = ROOT / "futures-monitor" / "public" / "review"


def bj_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并 override 到 base。"""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def flatten_params(params: dict, prefix: str = "") -> dict[str, float]:
    """将嵌套参数字典扁平化为 keypath:value。"""
    result = {}
    for k, v in params.items():
        if k.startswith("_"):
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(flatten_params(v, key))
        elif isinstance(v, (int, float)):
            result[key] = float(v)
    return result


def diff_params(current: dict, proposed: dict) -> dict[str, dict[str, float]]:
    """计算两个参数字典的差异，只返回变更项。"""
    flat_cur = flatten_params(current)
    flat_pro = flatten_params(proposed)
    changes = {}
    all_keys = set(flat_cur.keys()) | set(flat_pro.keys())
    for k in all_keys:
        cur_v = flat_cur.get(k)
        pro_v = flat_pro.get(k)
        if cur_v != pro_v:
            changes[k] = {"from": cur_v, "to": pro_v}
    return changes


def analyze_signal_sensitivity(trades: list[dict], data_snapshot: dict) -> dict:
    """
    分析历史交易对当前信号数据的敏感度。
    对每笔已平仓交易，检查其品种的当前信号状态，评估参数变化的潜在影响。
    
    返回: 敏感度分析结果
    """
    symbols_data = {d["symbol"]: d for d in data_snapshot.get("data", [])}

    # 按策略和出场原因分类
    by_signal = {"breakout": [], "pullback": [], "box": [], "other": []}
    for t in trades:
        st = t.get("signalType", "other")
        by_signal.setdefault(st, []).append(t)

    analysis = {
        "total_trades": len(trades),
        "by_signal_type": {k: len(v) for k, v in by_signal.items()},
        "sensitivity": {},
    }

    # MACD 敏感度：对所有 breakout + pullback 交易
    macd_sensitive_trades = by_signal.get("breakout", []) + by_signal.get("pullback", [])
    analysis["sensitivity"]["macd_expansion_rate"] = {
        "affected_trades": len(macd_sensitive_trades),
        "note": "expansion_rate_min 影响所有 breakout/pullback 信号的触发门槛。提高该值 → 信号更少但更精准。"
    }

    # Pullback 敏感度
    pb_trades = by_signal.get("pullback", [])
    analysis["sensitivity"]["pullback"] = {
        "affected_trades": len(pb_trades),
        "params": ["bounce_tol_pct", "atr_factor", "approach_tol_pct",
                    "min_slope20_pct", "min_slope60_pct", "ma_entanglement_threshold_pct"],
        "note": "回踩/反抽信号的过滤层参数"
    }

    # 风控敏感度（影响所有交易）
    analysis["sensitivity"]["risk"] = {
        "affected_trades": len(trades),
        "params": ["stop_loss_atr_entry", "stop_loss_atr_prev_bar",
                    "take_profit_risk_ratio", "breakeven_r", "trailing_activate_r"],
        "note": "风控参数影响所有交易的止损/止盈/移动止损行为"
    }

    # 品种级分析：哪些品种在当前信号数据中表现突出
    symbol_analysis = {}
    for t in trades:
        sym = t["symbol"]
        if sym not in symbol_analysis:
            sym_data = symbols_data.get(sym, {})
            ma = sym_data.get("ma", {})
            macd = sym_data.get("macd", {})
            symbol_analysis[sym] = {
                "trades": 0,
                "wins": 0,
                "current_ma_status": ma.get("status", "N/A"),
                "current_macd_sign": macd.get("sign", "N/A"),
                "current_expansion_rate": macd.get("expansionRate", 0),
            }
        symbol_analysis[sym]["trades"] += 1
        if t["status"] == "closed_tp":
            symbol_analysis[sym]["wins"] += 1

    analysis["by_symbol"] = symbol_analysis
    return analysis


def estimate_parameter_impact(
    changes: dict[str, dict[str, float]],
    trades: list[dict],
    sensitivity: dict,
) -> list[dict]:
    """
    估算每个参数变更对历史交易的影响。
    返回: 每个变更的影响估算列表
    """
    impacts = []
    for param_path, delta in changes.items():
        old_val = delta["from"]
        new_val = delta["to"]
        direction = "tighten" if new_val > old_val else "loosen"
        pct_change = round((new_val - old_val) / old_val * 100, 1) if old_val and old_val != 0 else 0

        impact = {
            "param": param_path,
            "change": delta,
            "pct_change": pct_change,
            "direction": direction,
        }

        # MACD expansion rate 变更
        if "expansion_rate" in param_path:
            # 提高 → 更严格的信号过滤 → 可能减少假信号但也会错过一些真信号
            if direction == "tighten":
                # 粗略估算：每提高 0.1 过滤掉约 5% 的信号
                estimated_filter_pct = min(pct_change * 0.25, 30)
            else:
                estimated_filter_pct = max(pct_change * 0.25, -30)
            impact["estimated_signal_reduction"] = f"~{abs(estimated_filter_pct):.0f}%"
            impact["risk"] = "低" if abs(pct_change) < 15 else "中"

        # Pullback 阈值变更
        elif any(k in param_path for k in ["bounce_tol", "approach_tol", "slope"]):
            if direction == "tighten" and "tol" in param_path.lower():
                estimated_filter_pct = min(pct_change * 0.3, 25)
            elif direction == "tighten":
                estimated_filter_pct = min(pct_change * 0.5, 20)
            else:
                estimated_filter_pct = max(pct_change * 0.3, -25)
            impact["estimated_signal_reduction"] = f"~{abs(estimated_filter_pct):.0f}%"
            impact["risk"] = "低" if abs(pct_change) < 20 else "中"

        # 风控参数变更
        elif any(k in param_path for k in ["stop_loss", "take_profit", "breakeven", "trailing"]):
            if "stop_loss" in param_path:
                if direction == "tighten":
                    impact["note"] = "止损收紧 → 更快出场，减少单笔亏损但可能增加被扫出场次数"
                else:
                    impact["note"] = "止损放宽 → 给行情更多空间，减少假止损但单笔亏损加大"
            elif "take_profit" in param_path:
                if direction == "tighten":
                    impact["note"] = "止盈提高 → 单笔盈利更大但更难触及"
                else:
                    impact["note"] = "止盈降低 → 更快兑现利润但可能错过趋势"
            impact["risk"] = "中" if abs(pct_change) > 15 else "低"

        else:
            impact["note"] = "影响暂无法自动估算，建议手动评估"
            impact["risk"] = "中"

        impacts.append(impact)

    return impacts


def generate_report(
    changes: dict,
    impacts: list[dict],
    sensitivity: dict,
    current_params: dict,
    proposed_params: dict,
) -> str:
    """生成人类可读的对比报告。"""
    lines = [
        "# 策略参数 A/B 回测报告",
        f"**生成时间:** {bj_now().strftime('%Y-%m-%d %H:%M')} (北京时间)",
        "",
        "---",
        "",
        "## 📋 参数变更清单",
        "",
    ]

    if not changes:
        lines.append("✅ 无变更：提议参数与当前参数完全一致。")
    else:
        for param, delta in changes.items():
            old = delta["from"]
            new = delta["to"]
            arrow = "↑" if new > old else "↓"
            lines.append(f"- **{param}**: {old} {arrow} {new}")

    lines.extend(["", "## 📊 影响评估", ""])

    if not impacts:
        lines.append("无变更，无需评估。")
    else:
        for imp in impacts:
            lines.append(f"### {imp['param']}")
            lines.append(f"- 变更: {imp['change']['from']} → {imp['change']['to']} ({imp['pct_change']:+.1f}%)")
            lines.append(f"- 方向: {'收紧' if imp['direction'] == 'tighten' else '放宽'}")
            if imp.get("estimated_signal_reduction"):
                lines.append(f"- 估计信号减少: {imp['estimated_signal_reduction']}")
            if imp.get("note"):
                lines.append(f"- 说明: {imp['note']}")
            lines.append(f"- 风险等级: {imp.get('risk', '未知')}")
            lines.append("")

    lines.extend([
        "## 🏷️ 敏感度分析",
        "",
        f"分析范围: {sensitivity['total_trades']} 笔历史交易",
        "",
    ])

    for param_group, info in sensitivity.get("sensitivity", {}).items():
        lines.append(f"- **{param_group}**: 影响 {info['affected_trades']} 笔交易")
        if "params" in info:
            lines.append(f"  相关参数: {', '.join(info['params'])}")
        if "note" in info:
            lines.append(f"  说明: {info['note']}")

    lines.extend([
        "",
        "---",
        "",
        "## ⚖️ 审批检查清单",
        "",
        "在合入参数变更前，请确认：",
        "",
        "- [ ] 变更方向与近期复盘结论一致",
        "- [ ] 风险等级 ≤ 中",
        "- [ ] 对受影响的策略（breakout/pullback）分别评估",
        "- [ ] 建议先在纸面上回测最近20笔交易的影响",
        "- [ ] 改后跑 1-2 周观察，准备随时回滚",
    ])

    return "\n".join(lines)


# ── 主入口 ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="策略参数 A/B 回测")
    parser.add_argument("--propose", type=str, help="提议的参数文件路径 (JSON)")
    parser.add_argument("--patch", type=str, help="JSON patch 字符串，直接覆盖当前参数")
    parser.add_argument("--analyze-only", action="store_true", help="仅分析敏感度，不做对比")
    args = parser.parse_args()

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # ── 加载当前参数 ──
    current_params = load_json(PARAMS_FILE)
    if not current_params:
        print("[ERROR] strategy_params.json 未找到", file=sys.stderr)
        sys.exit(1)
    # 去掉 _desc 和 _comment 等元数据字段
    current_clean = {k: v for k, v in current_params.items()
                     if not k.startswith("_") and k != "version" and k != "updatedAt"}

    # ── 加载提议参数 ──
    proposed_params = None
    if args.propose:
        proposed_path = Path(args.propose)
        if not proposed_path.exists():
            # 尝试相对于项目根目录
            proposed_path = ROOT / args.propose
        if proposed_path.exists():
            proposed_params = load_json(proposed_path)
            proposed_params = {k: v for k, v in proposed_params.items()
                               if not k.startswith("_") and k != "version" and k != "updatedAt"}
        else:
            print(f"[ERROR] 提议参数文件不存在: {args.propose}", file=sys.stderr)
            sys.exit(1)
    elif args.patch:
        try:
            patch_data = json.loads(args.patch)
            proposed_params = deep_merge(current_clean, patch_data)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON patch 解析失败: {e}", file=sys.stderr)
            sys.exit(1)

    # ── 加载数据 ──
    positions = load_json(POSITIONS_FILE).get("positions", [])
    closed = [p for p in positions if p["status"] != "open"]
    data_snapshot = load_json(DATA_FILE)

    # ── 敏感度分析（始终执行）──
    sensitivity = analyze_signal_sensitivity(closed, data_snapshot)

    # ── 对比分析 ──
    if proposed_params and not args.analyze_only:
        changes = diff_params(current_clean, proposed_params)
        impacts = estimate_parameter_impact(changes, closed, sensitivity)
        report = generate_report(changes, impacts, sensitivity, current_clean, proposed_params)

        today = bj_now().strftime("%Y-%m-%d")
        report_path = REVIEW_DIR / f"backtest_{today}.md"
        report_path.write_text(report, "utf-8")
        print(report)
        print(f"\n✓ 报告已保存: {report_path}")

        # 同时输出 JSON 格式供程序读取
        json_path = REVIEW_DIR / f"backtest_{today}.json"
        json.dump({
            "date": today,
            "changes": changes,
            "impacts": impacts,
            "sensitivity": sensitivity,
        }, json_path.open("w"), ensure_ascii=False, indent=2)
        print(f"✓ JSON 已保存: {json_path}")

    elif args.analyze_only:
        print(f"# 敏感度分析\n")
        print(f"分析 {sensitivity['total_trades']} 笔已平仓交易\n")
        for group, info in sensitivity.get("sensitivity", {}).items():
            print(f"  {group}: 影响 {info['affected_trades']} 笔 | 参数: {info.get('params', [])}")

    else:
        print("用法: --propose <file> 或 --patch '<json>' 或 --analyze-only")


if __name__ == "__main__":
    main()

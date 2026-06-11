#!/usr/bin/env python3
"""
期货监控系统 - L1 数据层：每日收盘复盘
========================================
用法:
  python3 scripts/daily_review.py                    # 标准复盘（默认最近30天滚动窗口）
  python3 scripts/daily_review.py --full             # 全历史复盘
  python3 scripts/daily_review.py --window 90        # 最近90天窗口
  python3 scripts/daily_review.py --no-tg            # 不推送TG

输出:
  futures-monitor/public/review/review_YYYY-MM-DD.md     # Markdown 复盘报告
  futures-monitor/public/review/llm_review_prompt.md     # LLM 复盘 prompt（每次覆盖）
  futures-monitor/public/review/review_history.csv       # 指标历史（每次追加一行）
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
POSITIONS_FILE = ROOT / "futures-monitor" / "public" / "positions.json"
PARAMS_FILE = ROOT / "strategy_params.json"
REVIEW_DIR = ROOT / "futures-monitor" / "public" / "review"
CSV_FILE = REVIEW_DIR / "review_history.csv"

# ── 工具函数 ────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}

def bj_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))

def bj_fmt(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return dt.strftime(fmt)

def pnl_points(p: dict) -> float:
    """统一计算盈亏点数（正=盈利，负=亏损）"""
    if p.get("pnl") is not None:
        return float(p["pnl"])
    # fallback
    entry = float(p["entryPrice"])
    exit_px = float(p.get("exitPrice", entry))
    return (exit_px - entry) if p["direction"] == "long" else (entry - exit_px)


def tg_send(text: str) -> None:
    """推送到 Telegram（Bot1）"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[TG] 未配置 Bot，跳过推送")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=payload, method="POST"), timeout=10)
        print(f"[TG] 推送成功 ({len(text)} chars)")
    except Exception as e:
        print(f"[TG] 推送失败: {e}", file=sys.stderr)


# ── 统计计算 ────────────────────────────────────────────────

def compute_stats(closed_trades: list[dict]) -> dict:
    """对一组已平仓交易计算核心指标。"""
    n = len(closed_trades)
    if n == 0:
        return {"count": 0}

    wins = [t for t in closed_trades if t["status"] == "closed_tp"]
    losses = [t for t in closed_trades if t["status"] == "closed_sl"]
    n_win, n_loss = len(wins), len(losses)

    win_rate = n_win / n * 100 if n > 0 else 0
    avg_win = sum(pnl_points(t) for t in wins) / n_win if n_win > 0 else 0
    avg_loss = sum(abs(pnl_points(t)) for t in losses) / n_loss if n_loss > 0 else 0
    profit_factor = sum(pnl_points(t) for t in wins) / sum(abs(pnl_points(t)) for t in losses) if n_loss > 0 and sum(abs(pnl_points(t)) for t in losses) > 0 else float("inf")
    total_pnl = sum(pnl_points(t) for t in closed_trades)
    total_pnl_pct = sum(float(t.get("pnlPct", 0)) for t in closed_trades if t.get("pnlPct"))

    # 盈亏比（avg_win / avg_loss）
    rr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # 最大连胜/连亏
    max_consec_win, max_consec_loss = 0, 0
    cur_win, cur_loss = 0, 0
    for t in sorted(closed_trades, key=lambda x: x.get("exitTime", "")):
        if t["status"] == "closed_tp":
            cur_win += 1; cur_loss = 0
            max_consec_win = max(max_consec_win, cur_win)
        else:
            cur_loss += 1; cur_win = 0
            max_consec_loss = max(max_consec_loss, cur_loss)

    # 期望值
    ev = win_rate / 100 * avg_win - (1 - win_rate / 100) * avg_loss

    return {
        "count": n,
        "n_win": n_win, "n_loss": n_loss,
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "∞",
        "rr": round(rr, 2) if rr != float("inf") else "∞",
        "ev": round(ev, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "max_consec_win": max_consec_win,
        "max_consec_loss": max_consec_loss,
    }


def rolling_stats(closed_trades: list[dict], window: int = 20) -> list[dict]:
    """滚动窗口统计：每新增一笔交易计算一次累计指标。"""
    sorted_trades = sorted(closed_trades, key=lambda x: x.get("exitTime", ""))
    results = []
    for i in range(max(1, min(window, len(sorted_trades))), len(sorted_trades) + 1):
        start = max(0, i - window)
        stats = compute_stats(sorted_trades[start:i])
        stats["trade_idx"] = i
        stats["window_start"] = start
        results.append(stats)
    return results


# ── 分维度统计 ──────────────────────────────────────────────

def by_dimension(closed_trades: list[dict], key: str, label_map=None) -> list[dict]:
    """按某一维度（策略/方向/品种）分组统计。"""
    groups = defaultdict(list)
    for t in closed_trades:
        groups[t.get(key, "unknown")].append(t)
    result = []
    for k, trades in sorted(groups.items(), key=lambda x: -len(x[1])):
        stats = compute_stats(trades)
        label = label_map.get(k, k) if label_map else k
        stats["group"] = label
        result.append(stats)
    return result


# ── 品种连亏检测 ────────────────────────────────────────────

def detect_losing_streaks(closed_trades: list[dict], threshold: int = 3) -> list[dict]:
    """检测各品种的连续亏损情况，超过阈值生成经验规则建议。"""
    from collections import Counter
    by_sym = defaultdict(list)
    for t in closed_trades:
        by_sym[t["symbol"]].append(t)

    warnings = []
    for symbol, trades in by_sym.items():
        trades_sorted = sorted(trades, key=lambda x: x.get("exitTime", ""))
        streak = 0
        streak_trades = []
        for t in trades_sorted:
            if t["status"] == "closed_sl":
                streak += 1
                streak_trades.append(t)
            else:
                if streak >= threshold:
                    directions = Counter(t["direction"] for t in streak_trades)
                    reasons = Counter(t.get("exitReason") for t in streak_trades)
                    avg_risk = sum(abs(pnl_points(t)) for t in streak_trades) / streak
                    warnings.append({
                        "symbol": symbol,
                        "streak": streak,
                        "pnl_sum": round(sum(pnl_points(t) for t in streak_trades), 2),
                        "avg_risk": round(avg_risk, 2),
                        "directions": dict(directions),
                        "exit_reasons": dict(reasons),
                        "last_trade": streak_trades[-1].get("exitTime", ""),
                    })
                streak = 0
                streak_trades = []
        if streak >= threshold:
            directions = Counter(t["direction"] for t in streak_trades)
            warnings.append({
                "symbol": symbol, "streak": streak,
                "pnl_sum": round(sum(pnl_points(t) for t in streak_trades), 2),
                "avg_risk": round(sum(abs(pnl_points(t)) for t in streak_trades) / streak, 2),
                "directions": dict(directions),
                "last_trade": streak_trades[-1].get("exitTime", ""),
            })
    return warnings


# ── Markdown 报告生成 ────────────────────────────────────────

def generate_markdown(
    all_stats: dict,
    strategy_stats: list,
    direction_stats: list,
    symbol_stats: list,
    losing_streaks: list,
    rolling: list,
    date_range: tuple[str, str],
    params: dict,
    window: int,
) -> str:
    s = all_stats
    lines = [
        f"# 期货监控 · 每日复盘报告",
        f"",
        f"**生成时间:** {bj_fmt(bj_now(), '%Y-%m-%d %H:%M')} (北京时间)",
        f"**数据范围:** {date_range[0]} ~ {date_range[1]}",
        f"**统计窗口:** 最近 {window} 天 / {s['count']} 笔已平仓交易",
        f"",
        f"---",
        f"",
        f"## 📊 总体表现",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总交易笔数 | {s['count']} |",
        f"| 胜率 | {s['win_rate']}% |",
        f"| 盈利笔数 / 亏损笔数 | {s['n_win']} / {s['n_loss']} |",
        f"| 平均盈利 | {s['avg_win']} 点 |",
        f"| 平均亏损 | {s['avg_loss']} 点 |",
        f"| 盈亏比 | {s['rr']} |",
        f"| 期望值 (EV) | {s['ev']} 点/笔 |",
        f"| 盈利因子 | {s['profit_factor']} |",
        f"| 累计盈亏 | {s['total_pnl']} 点 ({s['total_pnl_pct']}%) |",
        f"| 最大连胜 | {s['max_consec_win']} 笔 |",
        f"| 最大连亏 | {s['max_consec_loss']} 笔 |",
        f"",
    ]

    if strategy_stats:
        lines.append("## 📈 分策略表现")
        lines.append("")
        for st in strategy_stats:
            lines.append(f"### {st['group']} ({st['count']}笔)")
            lines.append(f"- 胜率: {st['win_rate']}% | 盈亏比: {st['rr']} | EV: {st['ev']} | PF: {st['profit_factor']}")
            lines.append("")

    if direction_stats:
        lines.append("## 🔼🔽 分方向表现")
        lines.append("")
        for st in direction_stats:
            dir_label = "做多" if st['group'] == 'long' else "做空"
            lines.append(f"### {dir_label} ({st['count']}笔)")
            lines.append(f"- 胜率: {st['win_rate']}% | 盈亏比: {st['rr']} | EV: {st['ev']} | PF: {st['profit_factor']}")
            lines.append("")

    if symbol_stats:
        lines.append("## 🏷️ 分品种表现 (Top 10)")
        lines.append("")
        for st in symbol_stats[:10]:
            emoji = "🟢" if st['total_pnl'] > 0 else "🔴"
            lines.append(f"- {emoji} **{st['group']}** ({st['count']}笔): 胜率{st['win_rate']}% | 累计{st['total_pnl']}点 | EV{st['ev']}")
        lines.append("")

    if losing_streaks:
        lines.append("## ⚠️ 品种连亏预警 (≥3连亏)")
        lines.append("")
        for w in losing_streaks:
            dirs = ",".join(f"{k}:{v}" for k, v in w['directions'].items())
            lines.append(f"- 🔴 **{w['symbol']}**: 连亏{w['streak']}笔, 累计{w['pnl_sum']}点, 方向:{dirs}")
            lines.append(f"  → 建议: 检查该品种近期波动率/趋势结构是否异常，考虑暂停或减半仓位")
        lines.append("")

    if rolling and len(rolling) > 1:
        recent_roll = rolling[-1]
        lines.append("## 🔄 滚动窗口趋势 (最近20笔)")
        lines.append("")
        lines.append(f"- 当前胜率: {recent_roll['win_rate']}% (全期: {s['win_rate']}%)")
        lines.append(f"- 当前EV: {recent_roll['ev']} 点/笔 (全期: {s['ev']})")
        if recent_roll['win_rate'] < s['win_rate'] - 5:
            lines.append(f"- ⚠️ 近期胜率下降超过5%，需要关注策略是否在退化")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## ⚙️ 当前策略参数")
    lines.append("")
    lines.append("```json")
    # 只展示关键参数，隐藏敏感信息
    key_params = {
        "pullback": params.get("pullback", {}),
        "breakout": params.get("breakout", {}),
        "macd": params.get("macd", {}),
        "volume": params.get("volume", {}),
        "risk": params.get("risk", {}),
        "position": params.get("position", {}),
    }
    lines.append(json.dumps(key_params, ensure_ascii=False, indent=2))
    lines.append("```")

    return "\n".join(lines)


# ── LLM Prompt 生成 ─────────────────────────────────────────

def generate_llm_prompt(
    all_stats: dict,
    strategy_stats: list,
    direction_stats: list,
    losing_streaks: list,
    rolling: list,
    params: dict,
    date_range: tuple[str, str],
) -> str:
    """生成 LLM 复盘 prompt，供 L2 认知层使用。"""
    s = all_stats
    lines = [
        "# 期货监控系统 · 策略复盘 Prompt",
        "",
        f"你是期货策略的复盘分析师。请基于以下数据，给出策略参数优化建议。",
        "",
        "## 规则约束",
        "",
        "1. 你的输出必须是「建议 diff」格式，例如：",
        "   ```diff",
        '   - "expansion_rate_min": 1.2',
        '   + "expansion_rate_min": 1.4',
        "   ```",
        "2. 每个建议必须给出理由（基于数据，不是猜测）",
        "3. 参数修改必须在 strategy_params.json 的有效范围内",
        "4. 标注每个建议的「风险等级」：低/中/高",
        "5. 优先关注连亏品种的针对性优化",
        "",
        "---",
        "",
        "## 数据概览",
        "",
        f"- 统计范围: {date_range[0]} ~ {date_range[1]}",
        f"- 总交易: {s['count']} 笔",
        f"- 胜率: {s['win_rate']}%",
        f"- 盈亏比: {s['rr']}",
        f"- 盈利因子: {s['profit_factor']}",
        f"- 期望值: {s['ev']} 点/笔",
        f"- 累计盈亏: {s['total_pnl']} 点",
        f"- 最大连亏: {s['max_consec_loss']} 笔",
        "",
    ]

    if strategy_stats:
        lines.append("## 分策略统计")
        for st in strategy_stats:
            lines.append(f"- {st['group']}: {st['count']}笔, 胜率{st['win_rate']}%, "
                          f"盈亏比{st['rr']}, EV{st['ev']}, PF{st['profit_factor']}")
        lines.append("")

    if direction_stats:
        lines.append("## 分方向统计")
        for st in direction_stats:
            dir_label = "做多" if st['group'] == 'long' else "做空"
            lines.append(f"- {dir_label}: {st['count']}笔, 胜率{st['win_rate']}%, "
                          f"盈亏比{st['rr']}, EV{st['ev']}")
        lines.append("")

    if losing_streaks:
        lines.append("## ⚠️ 品种连亏预警")
        for w in losing_streaks:
            lines.append(f"- {w['symbol']}: 连亏{w['streak']}笔 ({w['pnl_sum']}点)")
        lines.append("")

    if rolling:
        recent = rolling[-1]
        lines.append("## 滚动窗口表现 (最近20笔)")
        lines.append(f"- 近期胜率: {recent['win_rate']}% (全期: {s['win_rate']}%)")
        lines.append(f"- 近期EV: {recent['ev']} (全期: {s['ev']})")
        if recent['win_rate'] < s['win_rate'] - 5:
            lines.append("- ⚠️ 近期胜率显著下降，策略可能退化")
        lines.append("")

    lines.append("## 当前参数 (完整)")
    lines.append("```json")
    lines.append(json.dumps(params, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 请输出")
    lines.append("")
    lines.append("1. **总体诊断**: 策略当前处于什么阶段（稳定/退化/进化中）？")
    lines.append("2. **参数建议 diff**: 最多5条，按优先级排序")
    lines.append("3. **连亏品种处置**: 对每个预警品种给出具体建议")
    lines.append("4. **下周关注**: 哪些品种/方向需要重点观察？")

    return "\n".join(lines)


# ── TG 摘要 ──────────────────────────────────────────────────

def generate_tg_summary(all_stats: dict, losing_streaks: list, date_range: tuple[str, str]) -> str:
    s = all_stats
    lines = [
        f"<b>📊 期货复盘 {date_range[0]} ~ {date_range[1]}</b>",
        f"",
        f"总交易: {s['count']}笔 | 胜率: {s['win_rate']}% | 盈亏比: {s['rr']}",
        f"累计盈亏: {s['total_pnl']}点 | EV: {s['ev']}点/笔",
        f"最大连亏: {s['max_consec_loss']}笔 | 盈利因子: {s['profit_factor']}",
    ]
    if losing_streaks:
        lines.append("")
        lines.append("<b>⚠️ 连亏预警:</b>")
        for w in losing_streaks[:3]:
            lines.append(f"  • {w['symbol']}: 连亏{w['streak']}笔 ({w['pnl_sum']}点)")
    return "\n".join(lines)


# ── 主入口 ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="期货监控每日复盘")
    parser.add_argument("--full", action="store_true", help="全历史复盘（不限制窗口）")
    parser.add_argument("--window", type=int, default=30, help="天数窗口 (默认30)")
    parser.add_argument("--no-tg", action="store_true", help="不推送TG")
    parser.add_argument("--no-llm-prompt", action="store_true", help="不生成 LLM prompt")
    args = parser.parse_args()

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # ── 加载数据 ──
    data = load_json(POSITIONS_FILE)
    positions = data.get("positions", [])
    if not positions:
        print("[ERROR] positions.json 为空或无数据", file=sys.stderr)
        sys.exit(1)

    params = load_json(PARAMS_FILE)

    # ── 过滤已平仓 ──
    closed = [p for p in positions if p["status"] != "open"]
    
    # 时间窗口过滤
    if not args.full:
        cutoff = bj_now() - timedelta(days=args.window)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        closed = [p for p in closed if p.get("exitTime", "") >= cutoff_str]
    
    if not closed:
        print(f"[WARN] 最近{args.window}天无已平仓交易")
        # 仍然用全量做一次
        closed = [p for p in positions if p["status"] != "open"]

    # 日期范围
    exit_times = sorted(p.get("exitTime", "") for p in closed if p.get("exitTime"))
    date_range = (exit_times[0][:10] if exit_times else "N/A",
                  exit_times[-1][:10] if exit_times else "N/A")

    print(f"[REVIEW] 已平仓: {len(closed)}笔, 范围: {date_range[0]} ~ {date_range[1]}")

    # ── 计算统计 ──
    all_stats = compute_stats(closed)
    strategy_stats = by_dimension(closed, "signalType")
    direction_stats = by_dimension(closed, "direction")
    symbol_stats = by_dimension(closed, "symbol")
    losing_streaks = detect_losing_streaks(closed)
    rolling = rolling_stats(closed, window=20)

    # ── 生成报告 ──
    md = generate_markdown(all_stats, strategy_stats, direction_stats,
                           symbol_stats, losing_streaks, rolling, date_range,
                           params, args.window)

    today = bj_now().strftime("%Y-%m-%d")
    md_path = REVIEW_DIR / f"review_{today}.md"
    md_path.write_text(md, "utf-8")
    print(f"✓ Markdown 报告: {md_path}")

    # ── LLM Prompt ──
    if not args.no_llm_prompt:
        prompt = generate_llm_prompt(all_stats, strategy_stats, direction_stats,
                                     losing_streaks, rolling, params, date_range)
        prompt_path = REVIEW_DIR / "llm_review_prompt.md"
        prompt_path.write_text(prompt, "utf-8")
        print(f"✓ LLM Prompt: {prompt_path}")

    # ── CSV 追加 ──
    csv_exists = CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not csv_exists:
            writer.writerow(["date", "total_trades", "win_rate", "rr", "ev",
                             "total_pnl", "profit_factor", "max_consec_loss",
                             "n_long", "n_short", "n_breakout", "n_pullback",
                             "top_losing_symbol", "losing_streaks"])
        n_long = sum(1 for t in closed if t["direction"] == "long")
        n_short = len(closed) - n_long
        n_bo = sum(1 for t in closed if t["signalType"] == "breakout")
        n_pb = sum(1 for t in closed if t["signalType"] == "pullback")
        top_loser = losing_streaks[0]["symbol"] if losing_streaks else ""
        n_streaks = len(losing_streaks)

        writer.writerow([today, all_stats["count"], all_stats["win_rate"],
                         all_stats["rr"], all_stats["ev"], all_stats["total_pnl"],
                         all_stats["profit_factor"], all_stats["max_consec_loss"],
                         n_long, n_short, n_bo, n_pb, top_loser, n_streaks])
    print(f"✓ CSV 追加: {CSV_FILE}")

    # ── TG 推送 ──
    if not args.no_tg:
        summary = generate_tg_summary(all_stats, losing_streaks, date_range)
        tg_send(summary)

    # 打印摘要
    print(f"\n{'='*50}")
    print(f"胜率: {all_stats['win_rate']}% | 盈亏比: {all_stats['rr']} | EV: {all_stats['ev']}")
    print(f"盈利因子: {all_stats['profit_factor']} | 最大连亏: {all_stats['max_consec_loss']}")
    if losing_streaks:
        print(f"连亏预警: {len(losing_streaks)} 个品种")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

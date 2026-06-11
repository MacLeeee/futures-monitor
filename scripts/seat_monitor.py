#!/usr/bin/env python3
# ============================================================
# 期货监控系统 - 席位（聪明钱）持仓复盘  ·  红榜式报告
#
# 数据: 四所每日前20会员持仓排名（AKShare 免费接口）
#   SHFE/CFFEX 按合约公布 → 自动按品种聚合
#   DCE/CZCE   按品种公布
#
# 席位分组（可在 FACTIONS 中自由增删）:
#   杭州帮 / 外资 / 机构 / 家人(散户系)
#
# 每品种×每分组输出: 多/空持仓、当日增减 → 加多/减多/加空/减空 标签
# 并标记 ⚡背离: 家人与(机构|外资)方向相反的品种
#
# 输出:
#   futures-monitor/public/seat_positions.json
#   reports/seat_report_YYYYMMDD.md
#   --push 时推送 TG 摘要
#
# 用法（收盘后运行，约17:00后数据才全）:
#   python3 scripts/seat_monitor.py
#   python3 scripts/seat_monitor.py --date 20260610
#   python3 scripts/seat_monitor.py --push
# ============================================================

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import pandas as pd
    import akshare as ak
except ImportError:
    print("[FATAL] 需要 akshare/pandas: pip install akshare pandas", file=sys.stderr)
    sys.exit(1)

# ── 路径 ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = ROOT / "futures-monitor" / "public" / "seat_positions.json"
REPORTS_DIR = ROOT / "reports"

# ── 席位分组：按需修改（子串匹配，"永安"可匹配"永安期货"）──────
FACTIONS: dict[str, list[str]] = {
    "杭州帮": ["永安", "浙商", "南华", "物产中大"],
    "外资":   ["乾坤", "摩根大通", "瑞银", "摩根士丹利", "高盛", "星展"],
    "机构":   ["中信期货", "国泰君安", "华泰", "银河", "中粮", "五矿"],
    "家人":   ["东方财富", "徽商", "平安"],
}

# 品种代码 → 中文名（仅监控这些；与主系统品种对齐，可增删）
VARIETIES = {
    "AU": "黄金", "AG": "白银", "CU": "铜", "AL": "铝", "NI": "镍", "SN": "锡",
    "LC": "碳酸锂", "I": "铁矿石", "RB": "螺纹钢", "JM": "焦煤", "J": "焦炭",
    "SM": "锰硅", "SF": "硅铁", "LH": "生猪", "C": "玉米", "CF": "棉花",
    "SR": "白糖", "Y": "豆油", "OI": "菜油", "P": "棕榈油", "M": "豆粕",
    "RM": "菜粕", "SC": "原油", "FU": "燃油", "EB": "苯乙烯", "SH": "烧碱",
    "RU": "橡胶", "V": "PVC", "MA": "甲醇", "PX": "对二甲苯", "EG": "乙二醇",
    "BR": "合成橡胶", "LU": "低硫燃油", "FG": "玻璃", "SA": "纯碱", "IM": "中证1000",
}

# 增减标签的最小变动手数（过滤噪声）
MIN_CHG_LOTS = 100


def variety_of(key: str) -> str | None:
    """合约/品种键 → 品种代码（'cu2412'→'CU', 'rb'→'RB', '豆粕2509'→None靠中文匹配）。"""
    m = re.match(r"^([A-Za-z]+)", str(key).strip())
    if m:
        code = m.group(1).upper()
        if code in VARIETIES:
            return code
    # 中文键（部分接口直接返回品种中文名）
    for code, name in VARIETIES.items():
        if name and name in str(key):
            return code
    return None


def fetch_all_rank_tables(date: str) -> dict[str, pd.DataFrame]:
    """抓取四所+广期所排名表，返回 {原始键: DataFrame}。
    每个交易所调用有独立超时保护（15s），超时/失败不阻塞其余交易所。"""
    import threading

    fetchers = [
        ("SHFE",  lambda: ak.get_shfe_rank_table(date=date)),
        ("DCE",   lambda: ak.futures_dce_position_rank(date=date)),
        ("CZCE",  lambda: ak.get_rank_table_czce(date=date)),
        ("CFFEX", lambda: ak.get_cffex_rank_table(date=date)),
    ]
    # 广期所（碳酸锂）：不同版本接口名不同，尽力而为
    if hasattr(ak, "futures_gfex_position_rank"):
        fetchers.append(("GFEX", lambda: ak.futures_gfex_position_rank(date=date)))

    tables: dict[str, pd.DataFrame] = {}
    for ex, fn in fetchers:
        result_holder: list = []
        exc_holder: list = []

        def _worker():
            try:
                result_holder.append(fn())
            except Exception as e:
                exc_holder.append(e)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=15)

        if t.is_alive():
            print(f"[WARN] {ex} 超时(>15s)，跳过", file=sys.stderr)
            continue
        if exc_holder:
            print(f"[WARN] {ex} 抓取失败: {exc_holder[0]}", file=sys.stderr)
            continue

        res = result_holder[0]
        if isinstance(res, dict):
            for k, df in res.items():
                if isinstance(df, pd.DataFrame) and len(df):
                    tables[f"{ex}:{k}"] = df
        elif isinstance(res, pd.DataFrame) and len(res):
            tables[f"{ex}:all"] = res
        elif isinstance(res, list):
            # DCE 备选接口可能返回 list[DataFrame]
            for i, df in enumerate(res):
                if isinstance(df, pd.DataFrame) and len(df):
                    tables[f"{ex}:{i}"] = df

        n_tables = len(res) if isinstance(res, (dict, list)) else (1 if isinstance(res, pd.DataFrame) and len(res) else 0)
        print(f"[{ex}] {n_tables} 张表")
    return tables


def _col(df: pd.DataFrame, *cands: str) -> str | None:
    for c in cands:
        if c in df.columns:
            return c
    return None


def aggregate(tables: dict[str, pd.DataFrame]) -> dict:
    """
    聚合为: {品种代码: {分组: {long, longChg, short, shortChg}}}
    自动把同品种多个合约（SHFE/CFFEX）累加。
    """
    agg: dict[str, dict[str, dict[str, float]]] = {}
    for key, df in tables.items():
        var = variety_of(key.split(":", 1)[1])
        sym_col = _col(df, "symbol", "variety")
        for _, row in df.iterrows():
            v = var or (variety_of(str(row[sym_col])) if sym_col else None)
            if not v:
                continue
            for side, name_c, oi_c, chg_c in [
                ("long",  _col(df, "long_party_name"),
                          _col(df, "long_open_interest"),
                          _col(df, "long_open_interest_chg")),
                ("short", _col(df, "short_party_name"),
                          _col(df, "short_open_interest"),
                          _col(df, "short_open_interest_chg")),
            ]:
                if not name_c or not oi_c:
                    continue
                broker = str(row.get(name_c, "")).strip()
                if not broker or broker in ("nan", "None"):
                    continue
                try:
                    oi = float(row.get(oi_c) or 0)
                    chg = float(row.get(chg_c) or 0) if chg_c else 0.0
                except (TypeError, ValueError):
                    continue
                for faction, members in FACTIONS.items():
                    if any(m in broker for m in members):
                        slot = agg.setdefault(v, {}).setdefault(
                            faction, {"long": 0, "longChg": 0, "short": 0, "shortChg": 0})
                        slot[side] += oi
                        slot[side + "Chg"] += chg
                        break
    return agg


def label(slot: dict) -> str:
    """按当日增减生成红榜式标签：加多/减多/加空/减空（可组合）。"""
    parts = []
    lc, sc = slot["longChg"], slot["shortChg"]
    if lc >= MIN_CHG_LOTS:
        parts.append("加多")
    elif lc <= -MIN_CHG_LOTS:
        parts.append("减多")
    if sc >= MIN_CHG_LOTS:
        parts.append("加空")
    elif sc <= -MIN_CHG_LOTS:
        parts.append("减空")
    return "".join(parts) if parts else "–"


def bias_of(slot: dict) -> int:
    """分组当日动作的方向倾向: +1偏多 / -1偏空 / 0中性。
    加多、减空=偏多；加空、减多=偏空。以净变化判断。"""
    net_chg = slot["longChg"] - slot["shortChg"]
    if net_chg >= MIN_CHG_LOTS:
        return 1
    if net_chg <= -MIN_CHG_LOTS:
        return -1
    return 0


def build_outputs(agg: dict, date: str) -> tuple[dict, str, list[str]]:
    rows = []
    divergences: list[str] = []
    for code, name in VARIETIES.items():
        fr = agg.get(code)
        if not fr:
            continue
        entry: dict = {"symbol": name, "code": code, "factions": {}}
        for faction in FACTIONS:
            slot = fr.get(faction)
            if slot:
                entry["factions"][faction] = {
                    **{k: int(v) for k, v in slot.items()},
                    "net":   int(slot["long"] - slot["short"]),
                    "netChg": int(slot["longChg"] - slot["shortChg"]),
                    "label": label(slot),
                    "bias":  bias_of(slot),
                }
        # ⚡背离: 家人与(机构|外资)当日方向相反
        fam = entry["factions"].get("家人", {}).get("bias", 0)
        inst = [entry["factions"].get(f, {}).get("bias", 0) for f in ("机构", "外资")]
        if fam != 0 and any(b != 0 and b == -fam for b in inst):
            entry["divergence"] = True
            smart = "偏空" if fam > 0 else "偏多"
            divergences.append(f"{name}: 家人{'加多' if fam > 0 else '加空'} vs 机构/外资{smart}")
        rows.append(entry)

    out_json = {
        "date": date,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "factions": {k: v for k, v in FACTIONS.items()},
        "minChgLots": MIN_CHG_LOTS,
        "data": rows,
    }

    # ── Markdown 红榜 ──
    md = [f"# 席位持仓复盘（红榜式） {date}\n",
          f"标签=当日增减（阈值 {MIN_CHG_LOTS} 手）；括号内为净持仓(多-空)。\n",
          "| 品种 | " + " | ".join(FACTIONS) + " |",
          "|---|" + "---|" * len(FACTIONS)]
    for e in rows:
        cells = []
        for f in FACTIONS:
            s = e["factions"].get(f)
            cells.append(f"{s['label']} ({s['net']:+d})" if s else "–")
        flag = " ⚡" if e.get("divergence") else ""
        md.append(f"| {e['symbol']}{flag} | " + " | ".join(cells) + " |")
    if divergences:
        md.append("\n## ⚡ 家人 vs 聪明钱 背离\n")
        md.extend(f"- {d}" for d in divergences)
    md.append("\n> 前20席位数据含经纪客户盘，仅反映倾向；接入策略前先验证 H-004（见 演绎式策略框架.md）。")
    return out_json, "\n".join(md), divergences


def tg_push(text: str) -> None:
    bots = [(os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")),
            (os.environ.get("TELEGRAM_BOT_TOKEN_2", ""), os.environ.get("TELEGRAM_CHAT_ID_2", ""))]
    for token, chat_id in bots:
        if not token or not chat_id:
            continue
        try:
            payload = urllib.parse.urlencode(
                {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=10):
                pass
            print(f"[TG] 席位报告推送成功 ({len(text)} chars)")
        except Exception as e:
            print(f"[TG] 推送失败: {e}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="席位持仓复盘")
    ap.add_argument("--date", default=None, help="YYYYMMDD，默认最近交易日")
    ap.add_argument("--push", action="store_true", help="推送 TG 摘要")
    args = ap.parse_args()

    dates = ([args.date] if args.date else
             [(datetime.now() - timedelta(days=i)).strftime("%Y%m%d") for i in range(6)])
    tables: dict = {}
    used_date = dates[0]
    for d in dates:
        tables = fetch_all_rank_tables(d)
        if tables:
            used_date = d
            break
    if not tables:
        print("[FATAL] 近 6 天均无席位数据（周末/假期或接口变动）", file=sys.stderr)
        sys.exit(1)

    agg = aggregate(tables)
    out_json, md, divergences = build_outputs(agg, used_date)

    REPORTS_DIR.mkdir(exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(out_json, ensure_ascii=False, indent=2), "utf-8")
    report_path = REPORTS_DIR / f"seat_report_{used_date}.md"
    report_path.write_text(md, "utf-8")
    print(md)
    print(f"\n✓ JSON → {OUTPUT_JSON}\n✓ 报告 → {report_path}")

    if args.push:
        head = f"<b>🧠 席位复盘</b> {used_date}\n覆盖 {len(out_json['data'])} 品种"
        body = ("\n⚡ <b>家人vs聪明钱背离</b>\n" + "\n".join(f"  {d}" for d in divergences)
                if divergences else "\n无显著背离")
        tg_push(head + body)


if __name__ == "__main__":
    main()

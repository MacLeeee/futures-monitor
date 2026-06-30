#!/usr/bin/env python3
"""
期货反指交易系统 - Inverse Trader
===================================
原理：将原系统的做多信号反转为做空，做空信号反转为做多。
止盈 = 原始止损位（原系统的1R距离）
止损 = 1:1 对称位置（入场价 ± 原始风险距离）

与主系统完全独立：
  - 读取 data.json 获取信号和行情数据
  - 独立持仓文件 inverse_positions.json
  - 独立推送（可配置不同的 Telegram chat）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

UTC = timezone.utc

# ── 路径 ─────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "futures-monitor" / "public" / "data.json"
INV_POSITIONS_FILE = ROOT / "futures-monitor" / "public" / "inverse_positions.json"
PARAMS_FILE = ROOT / "strategy_params.json"

# ── 加载参数 ─────────────────────────────────────────────────
_params_cache: Optional[dict] = None

def _load_params() -> dict:
    global _params_cache
    if _params_cache is not None:
        return _params_cache
    try:
        if PARAMS_FILE.exists():
            _params_cache = json.loads(PARAMS_FILE.read_text("utf-8"))
            return _params_cache
    except Exception:
        pass
    _params_cache = {
        "risk": {
            "stop_loss_atr_entry": 2,
            "stop_loss_atr_prev_bar": 1,
            "min_risk_pct": 0.15,
            "min_price_gap_pct": 0.01,
        }
    }
    return _params_cache


# ── 行情数据 ──────────────────────────────────────────────────

def load_data() -> list[dict]:
    """从 data.json 读取最新信号+行情数据"""
    if not DATA_FILE.exists():
        print(f"[INV] data.json 不存在: {DATA_FILE}, 跳过")
        return []
    try:
        raw = json.loads(DATA_FILE.read_text("utf-8"))
        return raw.get("data", [])
    except Exception as e:
        print(f"[INV] data.json 读取失败: {e}")
        return []


# ── 持仓管理 ──────────────────────────────────────────────────

def load_positions() -> list[dict]:
    """读取反指持仓"""
    if INV_POSITIONS_FILE.exists():
        try:
            return json.loads(INV_POSITIONS_FILE.read_text("utf-8")).get("positions", [])
        except Exception:
            return []
    return []


def save_positions(positions: list[dict]) -> None:
    """写回反指持仓文件"""
    output = {
        "updatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "openCount": sum(1 for p in positions if p["status"] == "open"),
        "totalCount": len(positions),
        "positions": positions,
    }
    INV_POSITIONS_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")


def calc_original_risk(entry: float, atr: float, direction: str,
                       prev_low: float, prev_high: float) -> float:
    """
    计算原始系统的初始风险距离（与 _open_position 逻辑一致）。
    返回正数，表示从入场价到止损的距离。
    """
    sl_entry = _load_params()["risk"]["stop_loss_atr_entry"]
    sl_prev = _load_params()["risk"]["stop_loss_atr_prev_bar"]
    min_pct = _load_params()["risk"]["min_price_gap_pct"] / 100

    if direction == "long":
        stop = max(entry - sl_entry * atr, prev_low - sl_prev * atr)
        stop = min(stop, entry * (1 - min_pct))
        return entry - stop
    else:
        stop = min(entry + sl_entry * atr, prev_high + sl_prev * atr)
        stop = max(stop, entry * (1 + min_pct))
        return stop - entry


def open_inverse_position(symbol: str, original_direction: str,
                          entry_price: float, atr: float,
                          prev_low: float, prev_high: float,
                          signal_type: str) -> Optional[dict]:
    """
    基于原始信号开反指仓位。

    原始做多 → 反指做空: SL=entry+risk, TP=entry-risk
    原始做空 → 反指做多: SL=entry-risk, TP=entry+risk
    """
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    uid = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")

    inv_direction = "short" if original_direction == "long" else "long"
    risk = calc_original_risk(entry_price, atr, original_direction, prev_low, prev_high)

    min_risk = entry_price * _load_params()["risk"]["min_risk_pct"] / 100
    if risk < min_risk:
        print(f"[INV] 跳过 {symbol} {inv_direction}: risk={risk:.4f} < min={min_risk:.4f}")
        return None

    if inv_direction == "short":
        stop_loss = entry_price + risk   # 1:1 止损在上方
        take_profit = entry_price - risk  # 止盈在原系统做多止损位
    else:
        stop_loss = entry_price - risk   # 1:1 止损在下方
        take_profit = entry_price + risk  # 止盈在原系统做空止损位

    return {
        "id": f"INV-{symbol}-{inv_direction[0].upper()}-{uid}",
        "symbol": symbol,
        "direction": inv_direction,
        "originalDirection": original_direction,
        "signalType": signal_type,
        "entryTime": bj_time,
        "entryPrice": round(entry_price, 4),
        "atr": round(atr, 4),
        "stopLoss": round(stop_loss, 4),
        "takeProfit": round(take_profit, 4),
        "riskDist": round(risk, 4),
        "status": "open",
        "exitReason": None,
        "exitTime": None,
        "exitPrice": None,
        "pnl": None,
        "pnlPct": None,
    }


def has_open_for(positions: list[dict], symbol: str, inv_direction: str) -> bool:
    """检查是否有该品种+方向的反指持仓仍 open"""
    return any(
        p["symbol"] == symbol and p["direction"] == inv_direction and p["status"] == "open"
        for p in positions
    )


def check_and_close(positions: list[dict], current_map: dict[str, dict]) -> list[dict]:
    """检查反指持仓的止损/止盈"""
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    for pos in positions:
        if pos["status"] != "open":
            continue
        sym_data = current_map.get(pos["symbol"])
        if not sym_data:
            continue

        cur_price = sym_data.get("price") or sym_data.get("close")
        cur_low = sym_data.get("curLow", cur_price)
        cur_high = sym_data.get("curHigh", cur_price)
        if not cur_price:
            continue

        direction = pos["direction"]
        entry = pos["entryPrice"]
        sl = pos["stopLoss"]
        tp = pos["takeProfit"]

        # 入场K内不触发（用30m bar_time判断）
        bar_time = sym_data.get("barTime", "")
        entry_time = pos.get("entryTime", "")
        is_entry_bar = False
        try:
            et = datetime.strptime(entry_time, "%Y-%m-%d %H:%M")
            bt = datetime.strptime(bar_time, "%Y-%m-%d %H:%M:%S")
            from datetime import timedelta
            bar_start = bt - timedelta(minutes=30)
            is_entry_bar = bar_start <= et <= bt
        except Exception:
            pass

        if is_entry_bar:
            continue

        hit_sl = False
        hit_tp = False

        if direction == "long":
            hit_sl = cur_low <= sl
            hit_tp = cur_high >= tp
        else:
            hit_sl = cur_high >= sl
            hit_tp = cur_low <= tp

        if hit_sl or hit_tp:
            if hit_sl:
                exit_px = sl
                pos["exitReason"] = "inverse_sl"
                pos["status"] = "closed_sl"
            else:
                exit_px = tp
                pos["exitReason"] = "inverse_tp"
                pos["status"] = "closed_tp"

            pos["exitTime"] = bj_time
            pos["exitPrice"] = round(exit_px, 4)
            pnl_pts = (exit_px - entry) if direction == "long" else (entry - exit_px)
            pos["pnl"] = round(pnl_pts, 4)
            pos["pnlPct"] = round(pnl_pts / entry * 100, 4) if entry else None
            print(f"[INV] {pos['id']} → {pos['status']} @ {exit_px:.4f} "
                  f"pnl={pos['pnl']:+.4f} ({pos['pnlPct']:+.2f}%)")

    return positions


def manage_positions(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    反指持仓管理主入口。
    返回: (全量持仓, 本轮新开仓)
    """
    positions = load_positions()
    current_map = {d["symbol"]: d for d in data}
    new_opened: list[dict] = []

    # Step 1: 检查现有持仓止损/止盈
    positions = check_and_close(positions, current_map)

    # Step 2: 遍历信号开反指仓
    for d in data:
        symbol = d["symbol"]
        close = d.get("price") or d.get("close")
        atr = d.get("atr", 0.0)
        prev_low = d.get("prevLow", close or 0.0)
        prev_high = d.get("prevHigh", close or 0.0)

        if not close or not atr:
            continue

        # 突破信号
        bo_sig = d.get("breakoutSignal")
        if bo_sig:
            orig_dir = bo_sig.get("type")  # "long" or "short"
            inv_dir = "short" if orig_dir == "long" else "long"
            if not has_open_for(positions, symbol, inv_dir):
                pos = open_inverse_position(
                    symbol, orig_dir, close, atr, prev_low, prev_high, "breakout"
                )
                if pos:
                    pos["triggerInfo"] = {
                        "originalSignal": "breakout",
                        "originalDirection": orig_dir,
                        "macdSign": bo_sig.get("macdSign"),
                        "expansionRate": bo_sig.get("expansionRate"),
                    }
                    positions.append(pos)
                    new_opened.append(pos)
                    print(f"[INV] 新增 {pos['id']} SL={pos['stopLoss']} TP={pos['takeProfit']} "
                          f"risk={pos['riskDist']:.4f} (1:1)")

        # 回踩信号
        pb_sig = d.get("pullbackSignal")
        if pb_sig:
            orig_dir = pb_sig.get("type")
            inv_dir = "short" if orig_dir == "long" else "long"
            if not has_open_for(positions, symbol, inv_dir):
                pos = open_inverse_position(
                    symbol, orig_dir, close, atr, prev_low, prev_high, "pullback"
                )
                if pos:
                    pos["triggerInfo"] = {
                        "originalSignal": "pullback",
                        "originalDirection": orig_dir,
                        "trigger": pb_sig.get("trigger"),
                        "zone": pb_sig.get("zone"),
                    }
                    positions.append(pos)
                    new_opened.append(pos)
                    print(f"[INV] 新增 {pos['id']} SL={pos['stopLoss']} TP={pos['takeProfit']} "
                          f"risk={pos['riskDist']:.4f} (1:1)")

    save_positions(positions)
    print(f"[INV] 持仓更新完成: total={len(positions)} open={sum(1 for p in positions if p['status']=='open')} "
          f"new={len(new_opened)}")
    return positions, new_opened


# ── Telegram 推送 ─────────────────────────────────────────────

def tg_send(token: str, chat_id: str, text: str, label: str = "") -> bool:
    import urllib.request
    import urllib.parse
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[INV TG] {label} 发送失败: {e}")
        return False


def build_inverse_message(data: list[dict], new_opened: list[dict],
                          all_positions: list[dict], bj_time: str) -> Optional[str]:
    """构建反指信号推送"""
    lines: list[str] = []
    sep = "─" * 24

    # 新开仓
    if new_opened:
        lines.append(f"<b>🔄 反指开仓</b>  {bj_time}")
        lines.append(sep)
        for pos in new_opened:
            direction = pos["direction"]
            arrow = "▼" if direction == "short" else "▲"
            action = "反指做空" if direction == "short" else "反指做多"
            orig = pos.get("originalDirection", "?")
            sig = pos.get("signalType", "?")
            orig_label = "原做多" if orig == "long" else "原做空"
            lines.append(
                f"  {arrow}{pos['symbol']} {action} @{pos['entryPrice']:.2f}  "
                f"SL{pos['stopLoss']:.2f} TP{pos['takeProfit']:.2f}  "
                f"risk={pos['riskDist']:.4f} ({orig_label}/{sig})"
            )
        lines.append(sep)

    # 信号摘要（非开仓但存在信号的品种）
    reverse_signals = []
    for d in data:
        bo = d.get("breakoutSignal")
        pb = d.get("pullbackSignal")
        sig = bo or pb
        if not sig:
            continue
        orig_dir = sig.get("type", "")
        inv_dir = "short" if orig_dir == "long" else "long"
        # 只显示尚未开反指仓的信号
        if not has_open_for(all_positions, d["symbol"], inv_dir):
            arrow = "▼" if inv_dir == "short" else "▲"
            sig_type = "突破" if bo else "回踩"
            reverse_signals.append(f"  {arrow}{d['symbol']} 原{orig_dir}→反{inv_dir} ({sig_type})")

    if reverse_signals:
        if not new_opened:
            lines.append(f"<b>🔄 反指信号</b>  {bj_time}")
            lines.append(sep)
        else:
            lines.append("<b>⏳ 待开反指仓</b>")
        lines.extend(reverse_signals)
        lines.append(sep)

    if not lines:
        return None
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────

def main():
    data = load_data()
    if not data:
        print("[INV] 无数据，退出")
        sys.exit(0)

    all_positions, new_opened = manage_positions(data)

    # 推送
    bj_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
    msg = build_inverse_message(data, new_opened, all_positions, bj_time)
    if msg:
        bots = [
            (os.environ.get("TELEGRAM_BOT_TOKEN", ""),
             os.environ.get("TELEGRAM_CHAT_ID", ""),
             "Bot1"),
            (os.environ.get("TELEGRAM_BOT_TOKEN_2", ""),
             os.environ.get("TELEGRAM_CHAT_ID_2", ""),
             "Bot2"),
        ]
        for token, chat_id, label in bots:
            if token and chat_id:
                tg_send(token, chat_id, msg, label)
                # 只发第一个 bot（避免重复）
                break
        if not any(t and c for t, c, _ in bots):
            print("[INV TG] 未配置 Bot，跳过推送")
    else:
        print("[INV TG] 无信号/无新仓，不推送")

    # Git push 可选
    if not os.environ.get("GITHUB_ACTIONS"):
        # 独立 push inverse_positions.json
        pass  # 不自动push，保持独立


if __name__ == "__main__":
    main()

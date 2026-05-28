#!/usr/bin/env bash
# ============================================================
# 本地期货 + 黄金监控数据采集脚本
# 用法：
#   ./run_local.sh          # 立即抓取一次后，每 15 分钟自动抓取
#   ./run_local.sh --once   # 只抓取一次后退出
# 停止：Ctrl+C
# ============================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$REPO_DIR/scripts/fetch_and_calc.py"
GOLD_BUS_SCRIPT="$REPO_DIR/scripts/run_gold_bus.py"
DATA_DIR="$REPO_DIR/futures-monitor/public"
INTERVAL=900   # 15 分钟（秒）——与 15min K线周期一致

# ── Telegram（可选）──────────────────────────────────────
# Bot 1（原有）
: "${TELEGRAM_BOT_TOKEN:=8052508202:***}"
: "${TELEGRAM_CHAT_ID:=6414409185}"
# Bot 2（Hajimibot @jimiikunbot）
: "${TELEGRAM_BOT_TOKEN_2:=8704990040:***}"
: "${TELEGRAM_CHAT_ID_2:=8760058696}"
export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID TELEGRAM_BOT_TOKEN_2 TELEGRAM_CHAT_ID_2

# ── 内部函数 ─────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $*"; }

run_once() {
    log "▶ 开始抓取 $(python3 -c 'from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M"))')"

    # ── 1. 期货数据 ──────────────────────────────────────────
    # 不设 FORCE_FETCH，由 fetch_and_calc.py 内的 is_trading_time() 守卫控制
    python3 "$SCRIPT"
    log "  ✓ 期货数据抓取完成"

    # ── 2. 黄金宝宝巴士 ──────────────────────────────────────
    if python3 "$GOLD_BUS_SCRIPT" 2>/dev/null; then
        log "  ✓ 黄金监控完成"
    else
        log "  ⚠️ 黄金监控失败（非致命，继续后续步骤）"
    fi

    cd "$REPO_DIR"

    # ── Git 健康检查：清理上次失败残留，确保在 main 分支（非 detached HEAD）──
    git rebase --abort 2>/dev/null || true
    git merge  --abort 2>/dev/null || true
    # 若处于 detached HEAD，切回 main
    git symbolic-ref HEAD &>/dev/null || git checkout main 2>/dev/null || true

    # 暂存所有数据文件
    git add "$DATA_DIR/data.json" "$DATA_DIR/data_daily.json" "$DATA_DIR/gold_bus.json" 2>/dev/null || true
    if git diff --staged --quiet; then
        log "✓ 数据无变化，跳过 commit"
        return 0
    fi

    git commit -m "chore: update futures data (local $(date '+%H:%M'))"

    # 拉取远端最新后推送；冲突时保留本地数据文件（本地数据最新）
    git fetch origin main
    git merge origin/main --no-edit -X ours 2>/dev/null || {
        log "⚠️  merge 冲突，强制保留本地数据文件"
        git checkout HEAD -- "$DATA_DIR/data.json" "$DATA_DIR/data_daily.json" "$DATA_DIR/gold_bus.json"
        git add "$DATA_DIR/data.json" "$DATA_DIR/data_daily.json" "$DATA_DIR/gold_bus.json"
        GIT_EDITOR=true git merge --continue 2>/dev/null || git merge --abort 2>/dev/null || true
    }

    git push origin main
    log "✓ 数据已推送到 GitHub"
}

# ── 主逻辑 ───────────────────────────────────────────────
echo "╔════════════════════════════════════════╗"
echo "║  期货 + 黄金监控 · 本地数据采集       ║"
echo "║  每 15 分钟自动抓取 + 推送 GitHub      ║"
echo "║  Ctrl+C 停止                           ║"
echo "╚════════════════════════════════════════╝"
echo ""

# 立即执行一次
run_once

if [[ "${1:-}" == "--once" ]]; then
    log "--once 模式，结束。"
    exit 0
fi

# 循环执行
while true; do
    log "⏳ 等待 15 分钟..."
    sleep $INTERVAL
    run_once
done

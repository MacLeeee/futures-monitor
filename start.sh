#!/bin/bash
# ============================================================
# 期货监控系统 — 一键启动脚本
# 同时启动 AKShare Python 微服务 + Next.js Dashboard
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NEXT_DIR="$SCRIPT_DIR/futures-monitor"
AKSHARE_SCRIPT="$NEXT_DIR/akshare_service.py"
ENV_FILE="$NEXT_DIR/.env.local"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== 期货监控系统启动 ===${NC}"

# ---- Step 1: 检查 Python 依赖 ----
echo -e "\n${YELLOW}[1/3] 检查 Python 依赖...${NC}"
python3 -c "import akshare, fastapi, uvicorn, pandas, numpy" 2>/dev/null || {
    echo -e "${YELLOW}正在安装 Python 依赖（首次运行）...${NC}"
    pip3 install akshare fastapi uvicorn pandas numpy --quiet
    echo -e "${GREEN}✓ Python 依赖安装完成${NC}"
}
echo -e "${GREEN}✓ Python 依赖就绪${NC}"

# ---- Step 2: 启动 AKShare 微服务 ----
echo -e "\n${YELLOW}[2/3] 启动 AKShare 数据服务 (端口 8000)...${NC}"

# 杀掉占用 8000 端口的旧进程
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# 后台启动
cd "$NEXT_DIR"
uvicorn akshare_service:app --host 0.0.0.0 --port 8000 > /tmp/akshare.log 2>&1 &
AKSHARE_PID=$!
echo "AKShare 服务 PID: $AKSHARE_PID"

# 等待服务就绪
echo -n "等待 AKShare 服务启动"
for i in {1..15}; do
    sleep 1
    echo -n "."
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "\n${GREEN}✓ AKShare 服务已就绪${NC}"
        break
    fi
    if [ $i -eq 15 ]; then
        echo -e "\n${RED}✗ AKShare 服务启动超时，请检查 /tmp/akshare.log${NC}"
        cat /tmp/akshare.log | tail -20
        exit 1
    fi
done

# ---- 写入 .env.local ----
echo "AKSHARE_SERVICE_URL=http://localhost:8000" > "$ENV_FILE"
echo -e "${GREEN}✓ .env.local 已更新为实盘模式${NC}"

# ---- Step 3: 启动 Next.js Dashboard ----
echo -e "\n${YELLOW}[3/3] 启动 Next.js Dashboard (端口 3000)...${NC}"

# 清理旧的 Next.js 进程和锁文件，避免 "Unable to acquire lock" 报错
lsof -ti:3000,3001 | xargs kill -9 2>/dev/null || true
rm -f "$NEXT_DIR/.next/dev/lock"

# 安装 npm 依赖（如首次）
if [ ! -d "$NEXT_DIR/node_modules" ]; then
    echo "安装 npm 依赖..."
    cd "$NEXT_DIR" && npm install --quiet
fi

cd "$NEXT_DIR"
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Dashboard:  http://localhost:3000${NC}"
echo -e "${GREEN}  AKShare:    http://localhost:8000${NC}"
echo -e "${GREEN}  健康检查:  http://localhost:8000/health${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}\n"

# 捕获退出信号，同时清理 AKShare 服务
trap "echo '正在停止服务...'; kill $AKSHARE_PID 2>/dev/null; exit 0" INT TERM

npm run dev

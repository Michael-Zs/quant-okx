#!/usr/bin/env bash
# 一键启动：后端 API (:8787) + 前端 (:5173)
# 用法：./run_dev.sh      （按 Ctrl+C 同时停止两个）
set -u
cd "$(dirname "$0")"

echo "▶ 启动后端 API (:8787)..."
python api_server.py &
API_PID=$!

echo "▶ 启动前端 (:5173)..."
(cd web && npm run dev) &
WEB_PID=$!

cleanup() {
  echo ""
  echo "■ 停止服务..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null
  wait 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo ""
echo "✓ 就绪 → 浏览器打开 http://localhost:5173"
echo "  （左侧侧边栏底部填 API Token 解锁写操作；Ctrl+C 停止全部）"
echo ""
wait

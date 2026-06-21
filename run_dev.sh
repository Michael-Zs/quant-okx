#!/usr/bin/env bash
# 一键启动：后端 API (:8787) + 前端 (:5173)
# 用法：./run_dev.sh      （按 Ctrl+C 同时停止两个）
set -u
cd "$(dirname "$0")"

API_PORT="${API_PORT:-8787}"
WEB_PORT="${WEB_PORT:-5173}"

# 杀掉占用指定端口的进程（若存在）。复用 ./run_dev.sh 时先清掉上次的残留。
kill_port() {
  local port="$1" pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "• 端口 $port 被占用，先停掉旧进程: $(echo "$pids" | tr '\n' ' ')"
    kill $pids 2>/dev/null || true
    # 给进程 2s 优雅退出，否则强杀
    sleep 2
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}

kill_port "$API_PORT"
kill_port "$WEB_PORT"

# 优先用 python3（macOS 通常只有 python3），否则回退 python
PYTHON_BIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
if [ -z "$PYTHON_BIN" ]; then
  echo "✗ 未找到 python 或 python3，请先安装 Python 3"
  exit 1
fi

echo "▶ 启动后端 API (:$API_PORT)..."
$PYTHON_BIN api_server.py > >(while IFS= read -r line; do echo "[api] $line"; done) 2>&1 &
API_PID=$!

# 短暂等待看后端是否立崩
sleep 1
if ! kill -0 "$API_PID" 2>/dev/null; then
  echo "✗ 后端启动失败（进程已退出），请检查上方 [api] 前缀的错误输出"
  exit 1
fi

echo "▶ 启动前端 (:$WEB_PORT)..."
(cd web && npm run dev 2> >(while IFS= read -r line; do echo "[vite] $line"; done) 1>&2) &
WEB_PID=$!

cleanup() {
  echo ""
  echo "■ 停止服务..."
  # 杀整个进程组，避免子进程（vite / uvicorn worker）残留
  kill -- -"$API_PID" 2>/dev/null || kill "$API_PID" 2>/dev/null || true
  kill -- -"$WEB_PID" 2>/dev/null || kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null
  # 兜底：确保端口真正释放
  kill_port "$API_PORT"
  kill_port "$WEB_PORT"
  exit 0
}
trap cleanup INT TERM EXIT

echo ""
echo "✓ 就绪 → 浏览器打开 http://localhost:$WEB_PORT"
echo "  （左侧侧边栏底部填 API Token 解锁写操作；Ctrl+C 停止全部）"
echo ""
wait

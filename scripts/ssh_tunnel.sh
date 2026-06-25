#!/usr/bin/env bash
# SSH 端口转发：把远端 mac-mini 上「只监听 127.0.0.1」的 API(8787) + 前端(5173)
# 转发到本机，让本机浏览器能访问 http://localhost:5173 用控制台。
#
# 为什么这样设计：
#   - 前端用相对 URL（fetch('/api')）+ Vite 服务端代理 /api /ws 到 127.0.0.1:8787，
#     所以浏览器只需访问 5173 这一个端口，/api /ws 由远端 Vite 内部转发，无需单独转发。
#   - 额外转发 8787 仅为了本机直接调 API / Swagger（http://localhost:8787/docs）。
#   - 没有 autossh → 用 ssh 重连循环兜底：连接断了自动重连，配合 ServerAliveInterval
#     让死掉的隧道能在 ~45s 内被 ssh 检测并退出、触发重连。
#
# 用法：
#   ./scripts/ssh_tunnel.sh start     # 后台启动隧道（带自动重连）
#   ./scripts/ssh_tunnel.sh stop      # 停止隧道
#   ./scripts/ssh_tunnel.sh status    # 查看状态
#   ./scripts/ssh_tunnel.sh restart   # 重启
#   ./scripts/ssh_tunnel.sh fg        # 前台运行（看实时日志，Ctrl+C 退出即停）
#
# 环境变量覆盖默认值：
#   REMOTE=zhangzonggang@mac-mini
#   REMOTE_API=8787  REMOTE_WEB=5173      （远端端口）
#   LOCAL_API=8787   LOCAL_WEB=5173       （本机端口）
#   TUNNEL_LOG=1                          （后台模式也打详细日志到 stderr）

set -uo pipefail

# ---------- 默认配置 ----------
REMOTE="${REMOTE:-zhangzonggang@mac-mini}"
REMOTE_API="${REMOTE_API:-8787}"   # 远端目标用 localhost（见 ssh_forward_cmd 注释），不区分 IPv4/IPv6
REMOTE_WEB="${REMOTE_WEB:-5173}"
LOCAL_API="${LOCAL_API:-8787}"
LOCAL_WEB="${LOCAL_WEB:-5173}"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/quant-okx"
PIDFILE="$STATE_DIR/ssh_tunnel.pid"
LOGFILE="$STATE_DIR/ssh_tunnel.log"
mkdir -p "$STATE_DIR"

# ---------- 颜色 ----------
if [ -t 1 ]; then
  C_B='\033[1m'; C_G='\033[32m'; C_Y='\033[33m'; C_R='\033[31m'; C_C='\033[36m'; C_0='\033[0m'
else
  C_B=''; C_G=''; C_Y=''; C_R=''; C_C=''; C_0=''
fi
ok()   { echo -e "${C_G}✓ $*${C_0}"; }
info() { echo -e "${C_C}$*${C_0}"; }
warn() { echo -e "${C_Y}⚠ $*${C_0}"; }
die()  { echo -e "${C_R}✗ $*${C_0}" >&2; exit 1; }

# 检测某 TCP 端口本机是否被占用
port_busy() {  # port_busy <port> → 0=占用 1=空闲
  local p="$1"
  if command -v lsof >/dev/null 2>&1; then
    [ -n "$(lsof -ti tcp:"$p" 2>/dev/null)" ]
  elif command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$p" 2>/dev/null | grep -q ":$p"
  else
    return 1
  fi
}

# ---------- 单个 ssh 转发命令 ----------
ssh_forward_cmd() {
  # 远端目标用 localhost（而非 127.0.0.1）：远端 API(uvicorn) 绑 IPv4，
  # Vite 默认绑 IPv6(::1)，两者不同栈。ssh 对 localhost 在远端解析后逐一尝试
  # 全部地址（IPv4+IPv6），从而两条端口都能打通。本机侧仍绑 127.0.0.1 不暴露局域网。
  echo ssh -N \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=3 \
    -o ControlMaster=no \
    -L "127.0.0.1:${LOCAL_API}:localhost:${REMOTE_API}" \
    -L "127.0.0.1:${LOCAL_WEB}:localhost:${REMOTE_WEB}" \
    "$REMOTE"
}

# ---------- 前台模式：重连循环，Ctrl+C 干净退出 ----------
run_foreground() {
  check_ports_or_die
  echo -e "${C_B}隧道（前台）${C_0}：${REMOTE} → 本机 127.0.0.1:${LOCAL_WEB}(UI) / ${LOCAL_API}(API)"
  echo "  浏览器打开 http://localhost:${LOCAL_WEB}（Ctrl+C 停止，连接断了自动重连）"
  echo ""
  trap 'echo ""; ok "隧道已停止"; exit 0' INT TERM
  while true; do
    info "$(date '+%H:%M:%S') 建立 ssh 连接…"
    # shellcheck disable=SC2046
    $(ssh_forward_cmd)
    rc=$?
    if [ $rc -eq 0 ]; then
      # ssh -N 正常不会主动返回 0，除非被信号中断后清理；继续重连
      warn "$(date '+%H:%M:%S') ssh 退出(rc=$rc)，2s 后重连…"
    else
      warn "$(date '+%H:%M:%S') ssh 退出(rc=$rc，可能是端口冲突/网络断)，2s 后重连…"
    fi
    sleep 2
  done
}

# ---------- 后台模式 ----------
start_background() {
  if is_running; then
    warn "隧道已在运行（pid $(cat "$PIDFILE")）"; exit 0
  fi
  check_ports_or_die

  # 起一个后台子 shell：内部是前台的重连循环；通过 nohup 脱离终端，写 pidfile
  info "启动隧道：${REMOTE} → 127.0.0.1:${LOCAL_WEB}(UI) / ${LOCAL_API}(API)"
  : > "$LOGFILE"
  # setsid 让子进程独立成会话，父脚本退出也不影响它
  setsid bash -c '
    trap "" HUP INT TERM
    while true; do
      '"$(ssh_forward_cmd)"'
      echo "$(date "+%H:%M:%S") ssh 退出(rc=$?), 重连中…" >> "'"$LOGFILE"'" 2>&1
      sleep 2
    done
  ' >>"$LOGFILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PIDFILE"
  disown 2>/dev/null || true

  # 等 ssh 真正建好（最多 ~8s）再健康检查
  info "等待隧道建立…"
  sleep 2
  if is_running && wait_for_api 8; then
    ok "隧道已启动（pid $pid）"
    [ "${TUNNEL_LOG:-0}" = 1 ] && { echo "--- 日志 ---"; tail -5 "$LOGFILE"; }
    echo ""
    echo "  ▶ 浏览器：http://localhost:${LOCAL_WEB}"
    echo "  ▶ Swagger：http://localhost:${LOCAL_API}/docs"
    echo "  ▶ 停止：./scripts/ssh_tunnel.sh stop   日志：$LOGFILE"
  else
    warn "隧道进程已起，但 API 健康检查未通过 —— 可能远端服务还没起来"
    echo "    查日志：tail -f $LOGFILE   查远端服务：./scripts/deploy_remote.sh --dry-run"
  fi
}

stop_tunnel() {
  if [ ! -f "$PIDFILE" ]; then
    warn "无 pidfile，隧道可能没在运行"
    # 兜底：杀掉本机由本脚本起的 ssh 转发进程（匹配特征串）
    kill_stale_ssh
    exit 0
  fi
  local pid; pid="$(cat "$PIDFILE")"
  if is_running; then
    # 杀整个进程组（重连循环 + ssh 子进程都在这个会话里）
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    ok "隧道已停止（pid $pid）"
  else
    info "隧道未在运行（pid $pid 已死）"
  fi
  rm -f "$PIDFILE"
  kill_stale_ssh
}

kill_stale_ssh() {
  # 清掉可能残留的、特征匹配的 ssh 转发进程（只杀带我们 RemoteHost + -L 端口的）
  local pids
  pids="$(pgrep -f "ssh .*-L 127.0.0.1:${LOCAL_API}:127.0.0.1:${REMOTE_API}.*${REMOTE}" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    warn "清理残留 ssh 转发进程：$pids"
    kill $pids 2>/dev/null || true
  fi
}

# ---------- 状态查询 ----------
is_running() {
  [ -f "$PIDFILE" ] || return 1
  local pid; pid="$(cat "$PIDFILE" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

show_status() {
  if is_running; then
    local pid; pid="$(cat "$PIDFILE")"
    ok "运行中（pid $pid）"
    info "  ${REMOTE} → 127.0.0.1:${LOCAL_WEB}(UI) · ${LOCAL_API}(API)"
    if command -v lsof >/dev/null 2>&1; then
      if lsof -i tcp:"${LOCAL_WEB}" -i tcp:"${LOCAL_API}" >/dev/null 2>&1; then
        ok "  本机端口 ${LOCAL_WEB}/${LOCAL_API} 已在监听"
      fi
    fi
    # 主动探活 API
    if curl -sf --max-time 3 "http://127.0.0.1:${LOCAL_API}/api/health" >/dev/null 2>&1; then
      ok "  API 健康检查通过 ✓"
    else
      warn "  API 健康检查未通过（远端服务可能没起，或隧道刚建立）"
    fi
  else
    warn "未运行"
    info "  启动：./scripts/ssh_tunnel.sh start"
    exit 1
  fi
}

# ---------- 辅助 ----------
check_ports_or_die() {
  local conflict=0
  for label in "API:${LOCAL_API}" "WEB:${LOCAL_WEB}"; do
    local name="${label%%:*}" port="${label##*:}"
    if port_busy "$port"; then
      # 但如果占用的就是我们自己的隧道进程，不算冲突
      if is_running && lsof -ti tcp:"$port" 2>/dev/null | grep -qw "$(cat "$PIDFILE")"; then
        :
      else
        warn "本机端口 $port ($name) 已被占用"
        conflict=1
      fi
    fi
  done
  if [ "$conflict" = 1 ]; then
    die "本机端口被占用，无法绑定。改用 LOCAL_API=/LOCAL_WEB= 指定空闲端口，或先停掉占用进程。"
  fi
}

wait_for_api() {  # wait_for_api <max_seconds> → 0=健康 1=超时
  local max="${1:-8}" i
  for ((i=0; i<max; i++)); do
    if curl -sf --max-time 2 "http://127.0.0.1:${LOCAL_API}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# ---------- 入口 ----------
usage() {
  sed -n '2,21p' "$0"
  exit "${1:-0}"
}

cmd="${1:-start}"
case "$cmd" in
  start) start_background ;;
  fg|foreground) run_foreground ;;
  stop) stop_tunnel ;;
  restart) stop_tunnel; sleep 1; start_background ;;
  status) show_status ;;
  -h|--help) usage 0 ;;
  *) echo "未知命令: $cmd"; usage 1 ;;
esac

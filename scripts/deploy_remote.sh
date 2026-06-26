#!/usr/bin/env bash
# 部署到远端 mac-mini：拉代码 → 装依赖 → 冒烟测试 → 重启实盘 daemon → 重启 screen 里的服务。
#
# 用法：
#   ./scripts/deploy_remote.sh                 # 交互式（trader 重启会确认）
#   ./scripts/deploy_remote.sh --dry-run       # 只读侦察，不改动任何东西
#   ./scripts/deploy_remote.sh --yes           # 跳过所有确认（含未推送提交的 push）
#   ./scripts/deploy_remote.sh --no-traders    # 只重启 API，不碰实盘 daemon
#   ./scripts/deploy_remote.sh --build         # 额外跑 npm run build（dev server 不需要）
#
# 可用环境变量覆盖默认值：
#   REMOTE=zhangzonggang@mac-mini  REMOTE_DIR=~/Prj/quant-okx
#   SCREEN_NAME=quant  START_CMD=./run_dev.sh  PY=python3
#
# 设计要点（为什么分这几步）：
#   - 实盘 daemon 是 start_new_session=True 的独立进程，重启 API 不会动它；且它在
#     启动时把 core/ 代码读进内存，git pull 后仍跑旧代码 → 必须「单独」重启才生效。
#   - 远端是系统 Python 3.9：拉完代码先 import 冒烟，失败就中止、不动在跑的服务。
#   - 依赖按需安装：仅当本次更新改了 requirements.txt / package.json 才装，避免无谓操作。

set -euo pipefail

# ---------- 默认配置 ----------
REMOTE="${REMOTE:-zhangzonggang@mac-mini}"
REMOTE_DIR="${REMOTE_DIR:-~/Prj/quant-okx}"
SCREEN_NAME="${SCREEN_NAME:-quant}"
START_CMD="${START_CMD:-./run_dev.sh}"
PY="${PY:-python3}"

# ---------- 参数解析 ----------
DRY_RUN=0; ASSUME_YES=0; NO_TRADERS=0; DO_PUSH=0; DO_BUILD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --no-traders) NO_TRADERS=1 ;;
    --push) DO_PUSH=1 ;;
    --build) DO_BUILD=1 ;;
    --screen) SCREEN_NAME="$2"; shift ;;
    --remote) REMOTE="$2"; shift ;;
    --dir) REMOTE_DIR="$2"; shift ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1（--help 查看用法）"; exit 2 ;;
  esac
  shift
done

# 颜色（终端不支持时退化为普通文本）
if [ -t 1 ]; then
  C_B='\033[1m'; C_G='\033[32m'; C_Y='\033[33m'; C_R='\033[31m'; C_C='\033[36m'; C_0='\033[0m'
else
  C_B=''; C_G=''; C_Y=''; C_R=''; C_C=''; C_0=''
fi
step() { echo -e "\n${C_B}${C_C}▶ $*${C_0}"; }
ok()   { echo -e "${C_G}✓ $*${C_0}"; }
warn() { echo -e "${C_Y}⚠ $*${C_0}"; }
die()  { echo -e "${C_R}✗ $*${C_0}" >&2; exit 1; }

confirm() {  # confirm "提示"  → 0=yes
  [ "$ASSUME_YES" = 1 ] && return 0
  local ans
  read -r -p "$(echo -e "${C_Y}$* [y/N]${C_0} ") " ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

# 把含 ~ 的 REMOTE_DIR 解析成绝对路径（远端展开 ~），后续统一带引号使用
resolve_remote_dir() {
  ssh "$REMOTE" "cd ${REMOTE_DIR} 2>/dev/null && pwd" 2>/dev/null \
    || die "远端目录不可达：$REMOTE:${REMOTE_DIR}（用 --dir 覆盖）"
}
REMOTE_DIR="$(resolve_remote_dir)"

echo -e "${C_B}部署目标${C_0}：${REMOTE}:${REMOTE_DIR}"
echo -e "${C_B}screen 会话${C_0}：${SCREEN_NAME}  ${C_B}启动命令${C_0}：${START_CMD}"
[ "$DRY_RUN" = 1 ] && warn "DRY-RUN 模式：只做只读侦察，不执行任何改动"

# ============================================================
# Phase 0：本地预检 —— 是否有未推送的提交（远端 pull 拿不到它们）
# ============================================================
step "Phase 0 · 本地预检（未推送提交）"
if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
  if git rev-parse '@{u}' >/dev/null 2>&1; then
    UNPUSHED="$(git log --oneline '@{u}..HEAD' 2>/dev/null || true)"
    if [ -n "$UNPUSHED" ]; then
      echo "$UNPUSHED"
      warn "本地有以上提交尚未 push 到 origin —— 远端 git pull 拿不到它们"
      if [ "$DO_PUSH" = 1 ] || confirm "现在 push 到 origin 吗？"; then
        [ "$DRY_RUN" = 1 ] && { warn "(dry-run) 跳过 push"; :; } || { git push; ok "已 push"; }
      else
        warn "未 push，远端将不会拿到这些提交 —— 继续（可能部署的是旧代码）"
      fi
    else
      ok "本地与 origin 同步"
    fi
  else
    warn "当前分支无上游，跳过 push 检查"
  fi
fi

# ============================================================
# Phase 1：远端拉代码（记录前后 HEAD，判断改了哪些文件）
# ============================================================
step "Phase 1 · 远端 git pull"
OLD_HEAD="$(ssh "$REMOTE" "cd '$REMOTE_DIR' && git rev-parse HEAD")"
ssh "$REMOTE" "cd '$REMOTE_DIR' && git fetch --quiet origin && git status -sb | head -1"
if [ "$DRY_RUN" = 1 ]; then
  warn "(dry-run) 跳过 pull，仅显示远端落后情况"
  ssh "$REMOTE" "cd '$REMOTE_DIR' && git log --oneline HEAD..origin/\$(git rev-parse --abbrev-ref HEAD) | head -20 || true"
  NEW_HEAD="$OLD_HEAD"
else
  # pull 可能因远端本地改动冲突失败 —— 失败就中止，不动在跑的服务
  ssh "$REMOTE" "cd '$REMOTE_DIR' && git pull --ff-only" || die "git pull 失败（远端可能有本地改动冲突）。已中止，未改动运行中的服务。"
  ok "pull 完成"
fi
NEW_HEAD="$(ssh "$REMOTE" "cd '$REMOTE_DIR' && git rev-parse HEAD")"
CHANGED="$(ssh "$REMOTE" "cd '$REMOTE_DIR' && git diff --name-only $OLD_HEAD $NEW_HEAD")"
if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
  echo "  无新提交（HEAD 未变）"
else
  echo "  本次更新的文件："
  echo "$CHANGED" | sed 's/^/    /'
fi
CORE_CHANGED="$(echo "$CHANGED" | grep -E '^core/' || true)"

# ============================================================
# Phase 2：按需装依赖（仅当本次更新动了依赖清单）
# ============================================================
step "Phase 2 · 依赖（按需）"
if echo "$CHANGED" | grep -q '^requirements.txt$'; then
  echo "  requirements.txt 有变更 → pip install"
  [ "$DRY_RUN" = 1 ] && warn "(dry-run) 跳过 pip install" \
    || ssh "$REMOTE" "cd '$REMOTE_DIR' && $PY -m pip install -q -r requirements.txt" \
      || warn "pip install 失败（可能需要 --user 或虚拟环境），请手动处理"
else
  echo "  requirements.txt 未变，跳过 pip install"
fi
if echo "$CHANGED" | grep -q '^web/package\.json$'; then
  echo "  package.json 有变更 → npm install"
  [ "$DRY_RUN" = 1 ] && warn "(dry-run) 跳过 npm install" \
    || ssh "$REMOTE" "cd '$REMOTE_DIR/web' && npm install" || warn "npm install 失败"
else
  echo "  package.json 未变，跳过 npm install"
fi
if [ "$DO_BUILD" = 1 ]; then
  echo "  --build → npm run build（校验 TS 编译）"
  [ "$DRY_RUN" = 1 ] && warn "(dry-run) 跳过 npm run build" \
    || ssh "$REMOTE" "cd '$REMOTE_DIR/web' && npm run build" || die "前端构建失败（TS 类型错误？），已中止"
fi

# ============================================================
# Phase 3：远端 import 冒烟（Python 3.9 兼容性 / 语法 / 导入错）
# ============================================================
step "Phase 3 · 远端 import 冒烟（捕获 3.9 兼容/导入错误）"
if [ "$DRY_RUN" = 1 ]; then
  warn "(dry-run) 跳过冒烟测试"
else
  if ssh "$REMOTE" "cd '$REMOTE_DIR' && $PY -c 'import api_server' 2>&1"; then
    ok "import api_server 成功（$($PY --version 2>&1 || echo python)）"
  else
    die "import api_server 失败 —— 代码在远端跑不起来（很可能是 Python 3.9 兼容问题）。已中止，运行中的服务未受影响。"
  fi
fi

# ============================================================
# Phase 4：重启实盘 daemon（独立进程，需单独重启才用上新代码）
# ============================================================
step "Phase 4 · 实盘 daemon"
# 列出 runtime 里跟踪的部署 + 它们的存活状态
TRADERS_JSON="$(ssh "$REMOTE" "cd '$REMOTE_DIR' && DEPLOY_MODE=list $PY - <<'PYEOF'
import sys, os, json
sys.path.insert(0, os.getcwd())
from core.live.runtime import list_jobs
out = []
for j in list_jobs():
    did = j.get('deployment_id') or j.get('job_id')
    if not did:
        continue
    out.append({'id': did, 'pid': j.get('pid'),
                'status': j.get('status'), 'alive': bool(j.get('alive'))})
print(json.dumps(out, ensure_ascii=False))
PYEOF
")"
if [ "$(echo "$TRADERS_JSON" | tr -d '[:space:]')" = "[]" ] || [ -z "$TRADERS_JSON" ]; then
  ok "没有跟踪中的实盘 daemon"
  TRACKED_ALIVE=0
else
  echo "  跟踪中的部署："
  echo "$TRADERS_JSON" | $PY -c "import sys,json; [print(f\"    {d['id']}  pid={d['pid']}  status={d['status']}  alive={d['alive']}\") for d in json.load(sys.stdin)]" 2>/dev/null \
    || echo "    $TRADERS_JSON"
  TRACKED_ALIVE="$(echo "$TRADERS_JSON" | $PY -c "import sys,json; print(sum(1 for d in json.load(sys.stdin) if d['alive']))" 2>/dev/null || echo 0)"
fi

# 检测孤儿 daemon（进程在跑但不在 runtime 跟踪里）—— 只警告，不自动杀
ORPHAN_PIDS="$(ssh "$REMOTE" "pgrep -f 'trader_daemon.py|executor_daemon.py' 2>/dev/null | tr '\n' ' '" || true)"
TRACKED_PIDS="$(echo "$TRADERS_JSON" | $PY -c "import sys,json; print(' '.join(str(d['pid']) for d in json.load(sys.stdin) if d.get('pid')))" 2>/dev/null || echo "")"
# executor 的 pid 单独查
EXECUTOR_PID="$(ssh "$REMOTE" "cd '$REMOTE_DIR' && $PY - <<'PYEOF'
import sys, os, json
sys.path.insert(0, os.getcwd())
from core.live.runtime import read_json, state_path, is_process_alive
st = read_json(state_path('executor')) or {}
pid = st.get('pid')
if pid and is_process_alive(pid):
    print(pid)
PYEOF
" 2>/dev/null || echo "")"
if [ -n "$EXECUTOR_PID" ]; then
  TRACKED_PIDS="$TRACKED_PIDS $EXECUTOR_PID"
fi
ORPHANS=""
for p in $ORPHAN_PIDS; do
  case " $TRACKED_PIDS " in *" $p "*) ;; *) ORPHANS="$ORPHANS $p" ;; esac
done
if [ -n "${ORPHANS// }" ]; then
  warn "发现不在 runtime 跟踪里的孤儿 daemon 进程（pid:$ORPHANS）—— 可能是重复启动。本脚本不自动处理，请手动核实（ps -fp $ORPHANS）。"
fi

if [ "$NO_TRADERS" = 1 ]; then
  warn "--no-traders：跳过实盘 daemon 重启"
elif [ "$TRACKED_ALIVE" = 0 ] && [ -z "$CORE_CHANGED" ]; then
  echo "  无运行中的 daemon，且本次未改 core/ → 无需重启"
else
  if [ -n "$CORE_CHANGED" ]; then
    echo "  本次更新改动了 core/，daemon 需重启才能用上新代码："
    echo "$CORE_CHANGED" | sed 's/^/    /'
  fi
  if [ "$DRY_RUN" = 1 ]; then
    warn "(dry-run) 跳过 daemon 重启"
  elif confirm "重启这些实盘 daemon？（会先 stop 再 start，期间不下单）"; then
    ssh "$REMOTE" "cd '$REMOTE_DIR' && DEPLOY_MODE=restart $PY - <<'PYEOF'
import sys, os, json, time
sys.path.insert(0, os.getcwd())
from core.live.runtime import list_jobs, start_deployment, stop_deployment
for j in list_jobs():
    did = j.get('deployment_id') or j.get('job_id')
    if not did:
        continue
    if not (j.get('alive') or j.get('status') == 'running'):
        continue
    print(f'  · stop  {did} (pid={j.get(\"pid\")})', flush=True)
    stop_deployment(did)
    time.sleep(1)
    start_deployment(did)
    print(f'  · start {did}', flush=True)
print('done')
PYEOF
"
    ok "实盘 daemon 已重启"

    # 等 daemon 写出第一个 intent 再启动 executor。executor 侧已 fail-safe（空 intent 时
    # 跳过不平仓），这里的 sleep 是让 executor 首轮就有 intent、正常对账，而不是空转一轮（60s）。
    echo "  等待 daemon 写出 intent（15s）..."
    sleep 15

    # 重启 executor（同 daemon，独立进程需单独重启）
    echo "  重启 executor daemon..."
    ssh "$REMOTE" "cd '${REMOTE_DIR}' && $PY -c 'import sys,os; sys.path.insert(0, os.getcwd()); from core.executor.manager import stop_executor, start_executor; print("  · stop executor", flush=True); stop_executor(); import time; time.sleep(1); print("  · start executor", flush=True); start_executor(); print("executor done")'"
    ok "executor daemon 已重启"


  else
    warn "已跳过 daemon 重启 —— 注意：运行中的 daemon 仍用旧代码"
  fi
fi

# ============================================================
# Phase 5：重启 screen 里的服务（API + vite dev）
# ============================================================
step "Phase 5 · 重启 screen『${SCREEN_NAME}』"
if [ "$DRY_RUN" = 1 ]; then
  warn "(dry-run) 跳过 screen 重启"
else
  # 优雅关掉旧 screen 会话（run_dev.sh 的 EXIT trap 会清理 8787/5173 端口）
  ssh "$REMOTE" "screen -S '${SCREEN_NAME}' -X quit 2>/dev/null; sleep 1; \
                 lsof -ti tcp:8787 2>/dev/null | xargs kill 2>/dev/null || true; sleep 1"
  # 等待端口真正释放（TIME_WAIT 可能持续数秒）
  for _ in 1 2 3 4 5; do
    if ! ssh "$REMOTE" "lsof -ti tcp:8787 >/dev/null 2>&1"; then break; fi
    sleep 1
  done
  # 拉起新的 detached 会话。用【交互式登录 shell】启动：远端 npm/node 走 Homebrew/nvm，
  # 只在交互式 rc（.zshrc/.bashrc）里加进 PATH，非交互式 bash -lc 找不到 npm 会令 vite
  # 立即退出、整个 run_dev.sh 跟着死。LAUNCH_SHELL 默认 zsh（macOS 默认登录 shell）。
  LAUNCH_SHELL="${LAUNCH_SHELL:-zsh}"
  ssh "$REMOTE" "cd '$REMOTE_DIR' && screen -dmS '${SCREEN_NAME}' ${LAUNCH_SHELL} -lic '${START_CMD}'"
  # run_dev.sh 内 kill_port 也会 sleep 2s，加上 API 启动需要时间 → 给够 5s
  for _ in 1 2 3 4 5; do
    sleep 1
    if ssh "$REMOTE" "screen -ls 2>/dev/null | grep -q '${SCREEN_NAME}'"; then
      ok "screen『${SCREEN_NAME}』已重启（${START_CMD}）"
      break
    fi
  done
  if ! ssh "$REMOTE" "screen -ls 2>/dev/null | grep -q '${SCREEN_NAME}'"; then
    die "screen 启动失败 —— 请手动检查（ssh $REMOTE 'screen -ls'）"
  fi
fi

# ============================================================
# Phase 6：健康检查
# ============================================================
step "Phase 6 · 健康检查"
if [ "$DRY_RUN" = 1 ]; then
  warn "(dry-run) 跳过健康检查"
else
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if ssh "$REMOTE" "curl -sf http://127.0.0.1:8787/api/health >/dev/null 2>&1"; then
      ok "API 健康（http://127.0.0.1:8787）"
      echo ""
      echo -e "${C_G}部署完成。${C_0}"
      echo "  • 浏览器：http://<mini-ip>:5173"
      echo "  • 看日志：ssh $REMOTE 'screen -r ${SCREEN_NAME}'（Ctrl+A D 退出）"
      exit 0
    fi
    sleep 1
  done
  die "API 10s 内未响应 —— 请 ssh $REMOTE 'screen -r ${SCREEN_NAME}' 查看错误"
fi

echo ""
echo -e "${C_G}dry-run 侦察完成。${C_0}"

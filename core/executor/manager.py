"""Executor 进程管理。

ensure_executor: 幂等拉起 executor daemon（首个部署启动时调用）。
start_executor: 启动独立进程（仿 runtime.start_deployment）。
stop_executor: 停止进程（仿 runtime.stop_job）。
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from core.utils.config import settings
from core.live.runtime import (
    write_json_atomic, read_json, state_path, _acquire_lock, _release_lock,
    is_process_alive
)


EXECUTOR_JOB_ID = "executor"


def _executor_state_path() -> Path:
    """Executor state 文件路径。"""
    return state_path(EXECUTOR_JOB_ID)


def _executor_lock_path() -> Path:
    """Executor 锁文件路径。"""
    from core.live.runtime import _lock_path
    return _lock_path(EXECUTOR_JOB_ID)


def ensure_executor() -> bool:
    """确保 executor daemon 运行中（幂等）。

    先读 state：running 且进程存活 → 返回 True。
    否则调用 start_executor。

    Returns:
        是否成功（已运行或成功启动）
    """
    st = read_json(_executor_state_path(), {})
    if st.get("status") == "running" and is_process_alive(st.get("pid")):
        return True
    return start_executor()


def start_executor() -> bool:
    """启动 executor daemon（幂等，文件锁+双重检查）。"""
    lock = _acquire_lock(EXECUTOR_JOB_ID, stale_sec=30)
    if not lock:
        # 没拿到锁：另一个请求正在启动，等它完成
        time.sleep(0.5)
        st = read_json(_executor_state_path(), {})
        return st.get("status") == "running" and is_process_alive(st.get("pid"))
    try:
        # 锁内双重检查
        existing = read_json(_executor_state_path(), {})
        if existing.get("status") == "running" and is_process_alive(existing.get("pid")):
            return True

        daemon = settings.ROOT / "scripts" / "executor_daemon.py"
        out_path = settings.LOGS_DIR / f"{EXECUTOR_JOB_ID}.out"
        proc = subprocess.Popen(
            [sys.executable, str(daemon)],
            stdout=open(out_path, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(settings.ROOT),
        )

        state = {
            "job_id": EXECUTOR_JOB_ID,
            "pid": proc.pid,
            "status": "running",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        write_json_atomic(_executor_state_path(), state)
        return True
    except Exception as e:
        write_json_atomic(_executor_state_path(), {
            "job_id": EXECUTOR_JOB_ID,
            "status": "error",
            "error": str(e),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        return False
    finally:
        _release_lock(EXECUTOR_JOB_ID, lock)


def stop_executor() -> bool:
    """停止 executor daemon（仿 runtime.stop_job）。"""
    st = read_json(_executor_state_path(), {})
    if not st:
        return False
    pid = st.get("pid")
    if pid and is_process_alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
        # 等待优雅退出（最多 5 秒）
        for _ in range(50):
            if not is_process_alive(pid):
                break
            time.sleep(0.1)
        if is_process_alive(pid):
            try:
                os.kill(int(pid), signal.SIGKILL)
            except OSError:
                pass
    st["status"] = "stopped"
    st["stopped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json_atomic(_executor_state_path(), st)
    return True


def is_executor_running() -> bool:
    """检查 executor 是否运行中。"""
    st = read_json(_executor_state_path(), {})
    return st.get("status") == "running" and is_process_alive(st.get("pid"))

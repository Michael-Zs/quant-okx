"""全局 executor daemon：独立常驻进程，聚合 intents → 对账 → 下单。

由 core.executor.manager.ensure_executor 拉起（首个部署启动时）。
进程独立于 api_server，重启控制台不影响。

每轮：
1. 加载所有 intents（按 is_demo 分组）
2. 懒构造 demo/live exchange（失败置 None，不中断另一组）
3. 调用 run_once_cycle → 写 executor state + append_log
4. sleep（可配 EXECUTOR_INTERVAL_SEC，默认 60s）
"""
from __future__ import annotations
import os
import signal as sig_module
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.utils.okx_dns  # noqa: F401  国内 DNS 污染绕行（必须在 ccxt/OKX 调用前 import）

from core.utils.config import settings
from core.live.runtime import write_json_atomic, state_path, append_log
from core.executor.engine import run_once_cycle
from core.live.exchange import get_exchange

_running = True
EXECUTOR_JOB_ID = "executor"


def _handle_sig(signum, frame):
    global _running
    _running = False


def _sleep_responsively(interval: int):
    """分段 sleep 以便及时响应 SIGTERM。"""
    for _ in range(interval):
        if not _running:
            break
        time.sleep(1)


def _lazy_exchange(is_demo: bool):
    """懒构造 exchange，失败返回 None（不中断另一组）。"""
    try:
        return get_exchange(is_demo)
    except Exception as e:
        return None


def main():
    sig_module.signal(sig_module.SIGTERM, _handle_sig)

    # 懒构造 exchange（首次启动时验证 key，失败则标 error 不崩溃）
    demo_ex = None
    live_ex = None
    try:
        demo_ex = _lazy_exchange(is_demo=True)
    except Exception as e:
        append_log(EXECUTOR_JOB_ID, {"event": "init_demo_error", "error": str(e)})

    try:
        live_ex = _lazy_exchange(is_demo=False)
    except Exception as e:
        append_log(EXECUTOR_JOB_ID, {"event": "init_live_error", "error": str(e)})

    interval = settings.EXECUTOR_INTERVAL_SEC
    append_log(EXECUTOR_JOB_ID, {
        "event": "start",
        "pid": os.getpid(),
        "demo_ready": demo_ex is not None,
        "live_ready": live_ex is not None,
        "interval_sec": interval,
    })

    while _running:
        try:
            result = run_once_cycle(demo_ex, live_ex)
            state = {
                "job_id": EXECUTOR_JOB_ID,
                "pid": os.getpid(),
                "status": "running",
                "updated_at": result["ts"],
                "demo": result.get("demo", {}),
                "live": result.get("live", {}),
                "deployment_count": result.get("deployment_count", {}),
            }
            write_json_atomic(state_path(EXECUTOR_JOB_ID), state)
            append_log(EXECUTOR_JOB_ID, {
                "event": "cycle",
                "demo_actions": len(result.get("demo", {}).get("actions", [])),
                "live_actions": len(result.get("live", {}).get("actions", [])),
                "demo_errors": len(result.get("demo", {}).get("errors", [])),
                "live_errors": len(result.get("live", {}).get("errors", [])),
            })
        except Exception as e:
            write_json_atomic(state_path(EXECUTOR_JOB_ID), {
                "job_id": EXECUTOR_JOB_ID,
                "pid": os.getpid(),
                "status": "error",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
            })
            append_log(EXECUTOR_JOB_ID, {"event": "error", "error": str(e)})

        _sleep_responsively(interval)

    append_log(EXECUTOR_JOB_ID, {"event": "stop"})
    write_json_atomic(state_path(EXECUTOR_JOB_ID), {
        "job_id": EXECUTOR_JOB_ID,
        "status": "stopped",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


if __name__ == "__main__":
    main()

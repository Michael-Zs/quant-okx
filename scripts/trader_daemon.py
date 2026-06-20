"""后台实盘 daemon：独立进程，读 job 配置，循环执行策略信号并下单。

启动：python scripts/trader_daemon.py --job <jobfile>
由 core/live/runtime.start_job 用 subprocess 拉起；每轮 try/except，错误写 state 不崩溃。
"""
from __future__ import annotations
import argparse
import os
import signal as sig_module
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.live.runtime import read_json, write_json_atomic, state_path, append_log
from core.live.exchange import get_exchange, get_balance, get_position
from core.live.trader import run_once
from core.data.symbols import okx_to_ccxt
from core.strategy.registry import StrategyRegistry
from core.strategy.ensemble import Ensemble

_running = True


def _handle_sig(signum, frame):
    global _running
    _running = False


def build_strategy(spec: dict):
    """根据 job 的 strategy 配置构建策略实例（单策略或 Ensemble）。"""
    StrategyRegistry.discover_all()
    if spec.get("type") == "ensemble":
        subs = [StrategyRegistry.get(s["name"])(**s.get("params", {})) for s in spec["subs"]]
        return Ensemble(subs, spec.get("mode", "vote"), spec.get("weights"))
    return StrategyRegistry.get(spec["name"])(**spec.get("params", {}))


def main():
    sig_module.signal(sig_module.SIGTERM, _handle_sig)

    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="job 配置文件路径")
    args = ap.parse_args()

    job = read_json(Path(args.job))
    if not job:
        print(f"无法读取 job 配置: {args.job}")
        return
    job_id = job["job_id"]
    append_log(job_id, {"event": "start", "is_demo": job.get("is_demo"),
                        "symbol": job.get("symbol"), "strategy": job.get("strategy", {}).get("name")})

    strategy = build_strategy(job["strategy"])
    ex = get_exchange(job.get("is_demo", True))
    interval = int(job.get("check_interval_sec", 3600))
    ccxt_sym = okx_to_ccxt(job["symbol"])

    while _running:
        try:
            res = run_once(ex, strategy, job["symbol"], job["bar"],
                           int(job["leverage"]), float(job["position_ratio"]),
                           invert=bool(job.get("invert", False)))
            pos = get_position(ex, ccxt_sym)
            state = {
                "job_id": job_id,
                "pid": os.getpid(),
                "status": "running",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_signal": res["signal"],
                "last_price": res["price"],
                "last_action": res["action"],
                "position_dir": pos["dir"],
                "position_contracts": pos["contracts"],
                "entry_price": pos["entry_price"],
                "unrealized_pnl": pos["unrealized_pnl"],
                "balance": get_balance(ex),
                "next_check_at": time.strftime("%Y-%m-%d %H:%M:%S",
                                               time.localtime(time.time() + interval)),
                "error": None,
            }
            write_json_atomic(state_path(job_id), state)
            append_log(job_id, {"event": "check", "signal": res["signal"],
                                "price": res["price"], "action": res["action"]})
        except Exception as e:
            write_json_atomic(state_path(job_id), {
                "job_id": job_id, "pid": os.getpid(), "status": "error",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
            })
            append_log(job_id, {"event": "error", "error": str(e)})

        # 分段 sleep 以便及时响应 SIGTERM
        for _ in range(interval):
            if not _running:
                break
            time.sleep(1)

    append_log(job_id, {"event": "stop"})
    write_json_atomic(state_path(job_id), {
        "job_id": job_id, "status": "stopped",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")})


if __name__ == "__main__":
    main()

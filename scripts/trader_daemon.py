"""后台实盘 daemon：独立进程，支持两种入口。

- 新：python scripts/trader_daemon.py --deployment <deployment_id>
      从 DB 读策略组部署，循环执行多组占比聚合 → 写 intent。
- 旧：python scripts/trader_daemon.py --job <jobfile>
      兼容历史 job（单 symbol 单策略/Ensemble）。

由 core.live.runtime.start_deployment / start_job 用 subprocess 拉起
（start_new_session=True 脱离父进程组）；每轮 try/except，错误写 state 不崩溃。
"""
from __future__ import annotations
import argparse
import os
import signal as sig_module
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.live.runtime import read_json, write_json_atomic, state_path, append_log, delete_job
from core.data.symbols import okx_to_ccxt
from core.strategy.registry import StrategyRegistry
from core.strategy.ensemble import Ensemble
from core.executor.intent import write_intent, intent_path

_running = True


def _handle_sig(signum, frame):
    global _running
    _running = False


def build_strategy(spec: dict):
    """旧 job 兼容：构建单策略或 Ensemble 实例。"""
    StrategyRegistry.discover_all()
    if spec.get("type") == "ensemble":
        subs = [StrategyRegistry.get(s["name"])(**s.get("params", {})) for s in spec["subs"]]
        return Ensemble(subs, spec.get("mode", "vote"), spec.get("weights"))
    return StrategyRegistry.get(spec["name"])(**spec.get("params", {}))


def _sleep_responsively(interval: int):
    """分段 sleep 以便及时响应 SIGTERM。"""
    for _ in range(interval):
        if not _running:
            break
        time.sleep(1)


def _run_deployment_loop(deployment_id: str):
    """新入口：从 DB 读策略组部署，循环执行多组占比聚合 → 写 intent。"""
    from core.persist import repositories as R
    from core.persist.db import init_db
    from core.live.deployment import run_deployment_round

    init_db()
    deployment = R.get_deployment(deployment_id)
    if not deployment:
        print(f"未知 deployment: {deployment_id}")
        return
    append_log(deployment_id, {"event": "start", "is_demo": deployment["is_demo"],
                               "name": deployment["name"]})
    interval = int(deployment.get("check_interval_sec", 3600))

    while _running:
        try:
            intent = run_deployment_round(deployment_id)
            if "error" in intent:
                append_log(deployment_id, {"event": "error", "error": intent["error"]})
                write_json_atomic(state_path(deployment_id), {
                    "deployment_id": deployment_id, "pid": os.getpid(), "status": "error",
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "error": intent["error"]})
                _sleep_responsively(interval)
                continue

            # 写 intent 文件（executor 读取）
            write_intent(intent)

            state = {
                "deployment_id": deployment_id, "pid": os.getpid(), "status": "running",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "signals": intent.get("signals", {}),
                "capital_weight": intent.get("capital_weight", 1.0),
                "position_ratio": intent.get("position_ratio"),
                "leverage": intent.get("leverage"),
                "is_demo": intent.get("is_demo"),
                "bar": intent.get("bar"),
            }
            write_json_atomic(state_path(deployment_id), state)
            append_log(deployment_id, {"event": "check", "signals": intent.get("signals", {})})
        except Exception as e:
            write_json_atomic(state_path(deployment_id), {
                "deployment_id": deployment_id, "pid": os.getpid(), "status": "error",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "error": str(e)})
            append_log(deployment_id, {"event": "error", "error": str(e)})
        _sleep_responsively(interval)

    append_log(deployment_id, {"event": "stop"})
    # 退出时清理 intent 文件（executor 下一轮不再读到此部署的信号）
    try:
        intent_path(deployment_id).unlink()
    except FileNotFoundError:
        pass
    write_json_atomic(state_path(deployment_id), {
        "deployment_id": deployment_id, "status": "stopped",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")})


def _run_job_loop(job_file: str):
    """旧入口兼容：读 job 配置，循环执行单 symbol 单策略/Ensemble。"""
    job = read_json(Path(job_file))
    if not job:
        print(f"无法读取 job 配置: {job_file}")
        return
    job_id = job["job_id"]
    append_log(job_id, {"event": "start", "is_demo": job.get("is_demo"),
                        "symbol": job.get("symbol"),
                        "strategy": job.get("strategy", {}).get("name")})
    strategy = build_strategy(job["strategy"])
    interval = int(job.get("check_interval_sec", 3600))

    while _running:
        try:
            # 只算信号，不碰交易所（由 executor 统一下单）
            from core.live.trader import run_once
            res = run_once(strategy, job["symbol"], job["bar"],
                           invert=bool(job.get("invert", False)))

            # 写 intent 文件（executor 读取）
            intent = {
                "deployment_id": job_id,  # 用 job_id 作 key
                "signals": {job["symbol"]: float(res["signal"])},
                "capital_weight": 1.0,  # 旧 job 默认满份额
                "position_ratio": job.get("position_ratio", 0.1),
                "leverage": job.get("leverage", 5),
                "is_demo": job.get("is_demo", True),
                "bar": job["bar"],
                "ts": time.time(),
                "prices": {job["symbol"]: res["price"]},
            }
            write_intent(intent)

            state = {
                "job_id": job_id, "pid": os.getpid(), "status": "running",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_signal": res["signal"], "last_price": res["price"],
            }
            write_json_atomic(state_path(job_id), state)
            append_log(job_id, {"event": "check", "signal": res["signal"],
                                "price": res["price"]})
        except Exception as e:
            write_json_atomic(state_path(job_id), {
                "job_id": job_id, "pid": os.getpid(), "status": "error",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "error": str(e)})
            append_log(job_id, {"event": "error", "error": str(e)})
        _sleep_responsively(interval)

    append_log(job_id, {"event": "stop"})
    # 退出时清理 intent 文件
    try:
        intent_path(job_id).unlink()
    except FileNotFoundError:
        pass
    write_json_atomic(state_path(job_id), {
        "job_id": job_id, "status": "stopped",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")})


def main():
    sig_module.signal(sig_module.SIGTERM, _handle_sig)
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="旧 job 配置文件路径（兼容历史）")
    ap.add_argument("--deployment", help="部署 ID（从 DB 读策略组部署）")
    args = ap.parse_args()

    if args.deployment:
        _run_deployment_loop(args.deployment)
    elif args.job:
        _run_job_loop(args.job)
    else:
        print("需指定 --job <file> 或 --deployment <id>")


if __name__ == "__main__":
    main()

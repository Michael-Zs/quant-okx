"""全局执行器：多部署意图聚合 → 对账 → 统一下单。

唯一 executor 进程从所有部署 daemon 收集 intent（目标仓位意图），
按 is_demo 分组聚合、与账户持仓对账、增量下单。避免多部署共享账户时
资金重复计算、持仓互相震荡。
"""
from __future__ import annotations

# 导出公开接口
from core.executor.intent import (
    intent_path, write_intent, read_intent, load_fresh_intents, aggregate
)
from core.executor.engine import reconcile_and_trade, run_once_cycle
from core.executor.manager import ensure_executor, start_executor, stop_executor

__all__ = [
    "intent_path", "write_intent", "read_intent", "load_fresh_intents", "aggregate",
    "reconcile_and_trade", "run_once_cycle",
    "ensure_executor", "start_executor", "stop_executor",
]

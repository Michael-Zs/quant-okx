"""兼容层（过渡）：旧 Portfolio 资金组合接口。

新的资金层组合抽象：
- 组合器 core/strategy/node.py::AllocationGroup（只 collect 子信号 + weight/invert，不碰回测）
- 回测消费者 core/backtest/portfolio.py::run_group

本文件保留旧 ``Allocation`` / ``run_portfolio`` 签名供 app/pages/page_compose.py
过渡使用，内部通过适配器委托 run_group（零重复逻辑），待 React 前端上线后删除。

为避免 strategy 层模块级 import backtest（分层泄漏），所有 backtest 依赖改为
函数内延迟 import。
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass
class Allocation:
    strategy: object       # 有 generate_signals(df)->df 的策略实例
    weight: float          # 相对权重，会归一化


class _StrategyInstanceNode:
    """适配器：把旧 Strategy 实例（generate_signals(df)->df）包装成 StrategyNode，
    供 run_group 消费。仅用于兼容旧 run_portfolio，不参与序列化。"""

    node_type = "leaf"

    def __init__(self, strategy, primary_symbol: str):
        self.name = getattr(strategy, "name", "?")
        self.template_name = self.name
        self.invert = False
        self._strategy = strategy
        self._sym = primary_symbol

    def generate_signals(self, ctx):
        from core.strategy.invert import invert_signals
        raw = {self._sym: self._strategy.generate_signals(ctx.data[self._sym])}
        return invert_signals(raw, self.invert)

    def universe(self):
        return []

    def to_spec(self):
        return {"node_type": "leaf", "name": self.name, "adapter": True}


def run_portfolio(allocations: list, df: pd.DataFrame, cfg, invert: bool = False):
    """旧签名：Allocation(strategy, weight) 列表 + 单 df → 组合权益报告。

    通过适配器把每个 Allocation 包成 ChildRef（旧 invert 映射到每个子的 childref.invert，
    等价「所有子反向」），委托 run_group，零重复逻辑。
    """
    from core.strategy.node import AllocationGroup, ChildRef, NodeContext
    from core.backtest.portfolio import run_group

    sym = "_portfolio_asset"
    children = [
        ChildRef(node=_StrategyInstanceNode(a.strategy, sym), weight=a.weight, invert=invert)
        for a in allocations
    ]
    group = AllocationGroup(name="portfolio", children=children)
    ctx = NodeContext(data={sym: df}, primary_symbol=sym)
    return run_group(group, ctx, cfg)

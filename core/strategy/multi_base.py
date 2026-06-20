"""多币策略基类。

与单币 Strategy 平行（不继承它），复用同一套 Param 元类机制。
generate_signals 接收 Context（多币对齐数据 + 特征），返回 {symbol: df(含 signal 列)}。
"""
from __future__ import annotations
import pandas as pd

from core.strategy.base import _StrategyMeta, Param
from core.strategy.context import Context


class MultiStrategy(metaclass=_StrategyMeta):
    name: str = ""
    display_name: str = ""
    description: str = ""
    kind: str = "multi"                 # 兼容旧字段（page_multi 等历史引用）
    strategy_kind: str = "multi"        # 与 Strategy.strategy_kind 对齐的统一标记
    universe: list[str] = []   # 空 = 用户在 UI 选中的全部币种

    def __init__(self, **kwargs):
        self.p: dict = {}
        for param in self._param_list:
            val = kwargs.get(param.name, param.default)
            setattr(self, param.name, val)
            self.p[param.name] = val

    @classmethod
    def param_schema(cls) -> list[Param]:
        return list(getattr(cls, "_param_list", []))

    @classmethod
    def default_params(cls) -> dict:
        return {p.name: p.default for p in cls.param_schema()}

    def generate_signals(self, ctx: Context) -> dict[str, pd.DataFrame]:
        """返回 {symbol: df(含 signal 列)}，每个 df 行数与 ctx.data[symbol] 一致。"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 generate_signals")

    def __repr__(self):
        return f"<MultiStrategy {self.name!r} params={self.p}>"

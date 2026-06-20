"""等权持有基准：等权买入持有全部币种，作为多币基准/对比。"""
import pandas as pd

from core.strategy.multi_base import MultiStrategy


class EqualWeight(MultiStrategy):
    name = "equal_weight"
    display_name = "等权持有（基准）"
    description = "等权买入持有全部币种，作为多币买入持有基准。"

    def generate_signals(self, ctx):
        out: dict[str, pd.DataFrame] = {}
        for s in ctx.symbols:
            df = ctx.data[s].copy()
            df["signal"] = 1
            df["trade"] = 0
            out[s] = df
        return out

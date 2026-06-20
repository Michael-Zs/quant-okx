"""动量轮动（Top-K）：按过去 N 期收益率排名，等权持有最强的 Top-K，定期再平衡。

多币策略的核心示例，基于动量截面择优。
"""
import numpy as np
import pandas as pd

from core.strategy.multi_base import MultiStrategy
from core.strategy.base import Param


class MomentumRotation(MultiStrategy):
    name = "momentum_rotation"
    display_name = "动量轮动（Top-K）"
    description = "按过去 N 期收益率排名，等权持有最强的 Top-K，每隔若干根再平衡。"
    period = Param("period", 24, 4, 120, 2, label="动量回看周期")
    top_k = Param("top_k", 1, 1, 10, 1, label="持有数量 Top-K")
    rebalance = Param("rebalance", 24, 1, 96, 1, label="再平衡间隔(根)")

    def generate_signals(self, ctx):
        symbols = ctx.symbols
        period = int(self.period)
        reb = int(self.rebalance)
        k = int(self.top_k)
        mom = ctx.cross_section("momentum", period=period)   # time×symbol

        n = len(mom)
        sym_idx = {s: i for i, s in enumerate(symbols)}
        arr = np.zeros((n, len(symbols)), dtype=int)
        last_pick: set[str] = set()

        for i in range(n):
            if i % reb == 0:
                row = mom.iloc[i].dropna()
                last_pick = set(row.nlargest(min(k, len(row))).index) if len(row) > 0 else set()
            for s in last_pick:
                arr[i, sym_idx[s]] = 1

        out: dict[str, pd.DataFrame] = {}
        for s in symbols:
            df = ctx.data[s].copy()
            df["signal"] = arr[:, sym_idx[s]]
            df["trade"] = df["signal"].diff().fillna(0).astype(int)
            out[s] = df
        return out

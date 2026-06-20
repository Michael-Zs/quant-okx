"""跨币均值回归：截面动量排名，做多最弱、做空最强（反转）。"""
import pandas as pd

from core.strategy.multi_base import MultiStrategy
from core.strategy.base import Param


class CrossReversal(MultiStrategy):
    name = "cross_reversal"
    display_name = "跨币均值回归"
    description = "做多近期最弱势币、做空最强势币（截面反转），适合震荡市。"
    period = Param("period", 24, 4, 120, 2, label="动量回看周期")

    def generate_signals(self, ctx):
        symbols = ctx.symbols
        n = len(symbols)
        mom = ctx.cross_section("momentum", period=int(self.period))
        rank = mom.rank(axis=1, method="min")   # 1=最弱, n=最强

        out: dict[str, pd.DataFrame] = {}
        for s in symbols:
            df = ctx.data[s].copy()
            r = rank[s]
            sig = pd.Series(0, index=df.index)
            sig[r <= 1] = 1        # 最弱做多
            if n >= 3:
                sig[r >= n] = -1   # 最强做空（币种>=3 时才做空，否则只做多最弱）
            df["signal"] = sig.astype(int)
            df["trade"] = df["signal"].diff().fillna(0).astype(int)
            out[s] = df
        return out

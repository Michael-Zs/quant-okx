"""相对强弱（vs BTC）：相对基准（默认 BTC）走强的币种做多。"""
import pandas as pd

from core.strategy.multi_base import MultiStrategy
from core.strategy.base import Param


class RelativeStrength(MultiStrategy):
    name = "relative_strength"
    display_name = "相对强弱（vs BTC）"
    description = "相对 BTC 走强的币种做多、走弱的不持有，BTC 本身始终持有。"
    period = Param("period", 48, 4, 240, 4, label="动量回看周期")

    def generate_signals(self, ctx):
        symbols = ctx.symbols
        bench = "BTC-USDT-SWAP" if "BTC-USDT-SWAP" in symbols else symbols[0]
        mom = ctx.cross_section("momentum", period=int(self.period))
        bench_mom = mom[bench]

        out: dict[str, pd.DataFrame] = {}
        for s in symbols:
            df = ctx.data[s].copy()
            if s == bench:
                df["signal"] = 1
            else:
                sig = pd.Series(0, index=df.index)
                sig[mom[s] > bench_mom] = 1   # 跑赢基准才持有
                df["signal"] = sig.astype(int)
            df["trade"] = df["signal"].diff().fillna(0).astype(int)
            out[s] = df
        return out

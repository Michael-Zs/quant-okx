"""MA 双线交叉策略（迁移自原项目 strategy/ma_cross.py）。

快线上穿慢线做多、下穿做空。把原项目写死的 MA_FAST/MA_SLOW 改为可调参数，
并新增 long_only 开关。
"""
import pandas as pd
from core.strategy.base import Strategy, Param


class MACross(Strategy):
    name = "ma_cross"
    display_name = "MA 双线交叉"
    description = "快线上穿慢线做多、下穿做空，经典趋势跟踪。"
    side_mode = "long_short"

    ma_fast = Param("ma_fast", 20, 2, 200, 1, label="快线周期")
    ma_slow = Param("ma_slow", 60, 5, 400, 1, label="慢线周期")
    long_only = Param("long_only", False, options=[False, True], label="仅做多")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ma_fast"] = df["close"].rolling(int(self.ma_fast)).mean()
        df["ma_slow"] = df["close"].rolling(int(self.ma_slow)).mean()
        sig = pd.Series(0, index=df.index)
        sig[df["ma_fast"] > df["ma_slow"]] = 1
        if not self.long_only:
            sig[df["ma_fast"] < df["ma_slow"]] = -1
        df["signal"] = sig.astype(int)
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df

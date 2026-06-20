"""布林带均值回归策略。

价格跌破下轨做多、突破上轨做空，状态保持。
"""
import pandas as pd
from core.strategy.base import Strategy, Param


class Bollinger(Strategy):
    name = "bollinger"
    display_name = "布林带"
    description = "价格跌破下轨做多、突破上轨做空，均值回归。"
    side_mode = "long_short"

    period = Param("period", 20, 5, 100, 1, label="周期")
    std = Param("std", 2.0, 0.5, 4.0, 0.1, label="标准差倍数")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        mid = df["close"].rolling(int(self.period)).mean()
        sd = df["close"].rolling(int(self.period)).std()
        df["bb_mid"] = mid
        df["bb_upper"] = mid + self.std * sd
        df["bb_lower"] = mid - self.std * sd

        raw = pd.Series(0, index=df.index, dtype=float)
        raw[df["close"] < df["bb_lower"]] = 1
        raw[df["close"] > df["bb_upper"]] = -1
        df["signal"] = raw.where(raw != 0).ffill().fillna(0).astype(int)
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df

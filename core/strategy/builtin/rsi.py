"""RSI 超买超卖策略（均值回归）。

RSI 跌破超卖线入场做多，涨破超买线入场做空，中间状态保持持仓。
"""
import pandas as pd
from core.strategy.base import Strategy, Param


class RSI(Strategy):
    name = "rsi"
    display_name = "RSI 超买超卖"
    description = "RSI 低于超卖线做多、高于超买线做空，均值回归。"
    side_mode = "long_short"

    period = Param("period", 14, 2, 100, 1, label="RSI 周期")
    oversold = Param("oversold", 30, 5, 50, 1, label="超卖线")
    overbought = Param("overbought", 70, 50, 95, 1, label="超买线")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(int(self.period)).mean()
        loss = (-delta.clip(upper=0)).rolling(int(self.period)).mean()
        rs = gain / loss.replace(0, pd.NA)
        df["rsi"] = (100 - 100 / (1 + rs))

        raw = pd.Series(0, index=df.index, dtype=float)
        raw[df["rsi"] < self.oversold] = 1
        raw[df["rsi"] > self.overbought] = -1
        # 状态保持：持有上一个信号直到反向信号
        df["signal"] = raw.where(raw != 0).ffill().fillna(0).astype(int)
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df

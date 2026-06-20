"""Dual Thrust 突破策略。

基于前 N 日的 HH-LC 与 HC-LL 计算上下轨，开盘价 ± 比例作为突破触发线。
"""
import pandas as pd
from core.strategy.base import Strategy, Param


class DualThrust(Strategy):
    name = "dual_thrust"
    display_name = "Dual Thrust 突破"
    description = "基于前 N 日波幅的突破策略，收盘突破上轨做多、下轨做空。"
    side_mode = "long_short"

    period = Param("period", 5, 2, 30, 1, label="回看周期")
    k_up = Param("k_up", 0.5, 0.1, 1.0, 0.05, label="上轨系数")
    k_down = Param("k_down", 0.5, 0.1, 1.0, 0.05, label="下轨系数")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        n = int(self.period)
        hh = df["high"].rolling(n).max().shift(1)
        lc = df["close"].rolling(n).min().shift(1)
        hc = df["close"].rolling(n).max().shift(1)
        ll = df["low"].rolling(n).min().shift(1)
        up_line = df["open"] + (hh - lc) * self.k_up
        down_line = df["open"] - (hc - ll) * self.k_down
        df["dt_up"] = up_line
        df["dt_down"] = down_line

        raw = pd.Series(0, index=df.index, dtype=float)
        raw[df["close"] > up_line] = 1
        raw[df["close"] < down_line] = -1
        df["signal"] = raw.where(raw != 0).ffill().fillna(0).astype(int)
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df

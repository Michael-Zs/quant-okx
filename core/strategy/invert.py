"""统一的信号反向逻辑。

历史上 invert（反转信号方向 1↔-1）在 trader.run_once、trader_daemon、
backtest/engine.run 三处各写一遍。本模块收口为一处。

链路级反向（多层 invert 叠加）语义 = XOR（奇数层反向则反向）：
    final_dir = signal * (-1) ** n_invert_layers
本模块只做「单层取负」；多层叠加由调用方在树的每一层逐层应用 apply，
即子节点的 invert 先作用于子信号、父节点的 invert 再作用于聚合结果，等价于逐层 XOR。
"""
from __future__ import annotations
import pandas as pd

Signals = dict[str, pd.DataFrame]   # 统一信号结构（与 node.py 一致）：{symbol: 含 signal 列的 OHLCV df}


def invert_df(df: pd.DataFrame) -> pd.DataFrame:
    """对单个含 'signal' 列的 df 取反向（1↔-1），返回副本（不改入参）。"""
    d = df.copy()
    d["signal"] = (-d["signal"].fillna(0)).astype(int)
    return d


def invert_signals(signals: Signals, invert: bool) -> Signals:
    """对 Signals（{symbol: df}）批量反向。

    invert=False 时原样返回（不复制，调用方不应修改返回的 df）；
    invert=True 时返回每个 df 反向后的新 dict。
    """
    if not invert:
        return signals
    return {sym: invert_df(df) for sym, df in signals.items()}

"""绩效指标：全部基于逐 K 线权益曲线的周期收益率（标准做法）。

输入约定：equity 为 pd.Series（逐 K 线权益值），trades 为含 side/pnl 列的 DataFrame。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _period_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def total_return(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] == 0:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def annual_return(equity: pd.Series, bpy: int) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    yrs = len(equity) / bpy
    if yrs <= 0:
        return 0.0
    r = equity.iloc[-1] / equity.iloc[0]
    if r <= 0:
        return -1.0
    return float(r ** (1 / yrs) - 1)


def drawdown_series(equity: pd.Series) -> pd.Series:
    if len(equity) == 0:
        return pd.Series(dtype=float)
    cummax = equity.cummax().replace(0, np.nan)
    dd = (cummax - equity) / cummax
    return dd.replace([np.inf, -np.inf], 0).fillna(0)


def max_drawdown(equity: pd.Series) -> float:
    return float(drawdown_series(equity).max())


def sharpe(equity: pd.Series, bpy: int) -> float:
    rets = _period_returns(equity)
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(bpy))


def sortino(equity: pd.Series, bpy: int) -> float:
    rets = _period_returns(equity)
    neg = rets[rets < 0]
    if len(neg) < 1:
        return 0.0
    downside = neg.std()
    if downside == 0:
        return 0.0
    return float(rets.mean() / downside * np.sqrt(bpy))


def calmar(equity: pd.Series, bpy: int) -> float:
    ar = annual_return(equity, bpy)
    mdd = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    return float(ar / mdd)


def volatility(equity: pd.Series, bpy: int) -> float:
    rets = _period_returns(equity)
    if len(rets) < 2:
        return 0.0
    return float(rets.std() * np.sqrt(bpy))


def _closed_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty or "side" not in trades.columns:
        return pd.DataFrame(columns=["pnl"])
    return trades[trades["side"] == "close"]


def win_rate(trades: pd.DataFrame) -> float:
    closed = _closed_trades(trades)
    if len(closed) == 0:
        return 0.0
    return float((closed["pnl"] > 0).mean())


def profit_factor(trades: pd.DataFrame) -> float:
    closed = _closed_trades(trades)
    if len(closed) == 0:
        return 0.0
    win = closed.loc[closed["pnl"] > 0, "pnl"].sum()
    loss = -closed.loc[closed["pnl"] < 0, "pnl"].sum()
    if loss == 0:
        return float("inf") if win > 0 else 0.0
    return float(win / loss)


def n_trades(trades: pd.DataFrame) -> int:
    closed = _closed_trades(trades)
    return int(len(closed))

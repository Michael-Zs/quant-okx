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


# ---------- 基准对比（alpha / beta / 相关性 / 超额收益）----------
#
# 这组指标用来回答「回测好到底是因为策略有 edge，还是只是跟着大盘涨」。
# 输入 benchmark 是与策略同时间轴、同复利假设的基准权益曲线（通常为同 symbol
# 的杠杆 buy & hold）。它们全部基于逐周期收益率，与上面的绝对收益指标同源。


def _aligned_returns(equity: pd.Series, benchmark: pd.Series) -> tuple[pd.Series, pd.Series]:
    """对齐策略与基准的逐周期收益率，按较短长度截断，返回 (策略收益, 基准收益)。"""
    n = min(len(equity), len(benchmark))
    if n < 2:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    er = pd.Series(equity.to_numpy()[:n]).pct_change().dropna()
    br = pd.Series(benchmark.to_numpy()[:n]).pct_change().dropna()
    m = min(len(er), len(br))
    return er.iloc[-m:].reset_index(drop=True), br.iloc[-m:].reset_index(drop=True)


def beta(equity: pd.Series, benchmark: pd.Series) -> float:
    """策略相对基准的 beta：收益对基准收益的 OLS 回归斜率。

    beta≈1 说明策略基本复刻了基准（如杠杆做多）；beta≈0 说明策略基本对冲掉了
    市场方向、收益来自真正的 alpha。
    """
    er, br = _aligned_returns(equity, benchmark)
    if len(er) < 2:
        return 0.0
    var = float(np.var(br, ddof=1))
    if var == 0:
        return 0.0
    return float(np.cov(er, br, ddof=1)[0, 1] / var)


def alpha(equity: pd.Series, benchmark: pd.Series, bpy: int) -> float:
    """年化 Jensen's alpha：回归截距年化后的超额收益（与基准无关的那部分收益）。

    这是衡量「策略本身有没有 edge」最直接的数字：alpha>0 才说明策略真的跑赢了
    「承担同等 beta 风险本该获得的收益」。
    """
    er, br = _aligned_returns(equity, benchmark)
    if len(er) < 2:
        return 0.0
    var = float(np.var(br, ddof=1))
    if var == 0:
        return 0.0
    cov = float(np.cov(er, br, ddof=1)[0, 1])
    b = cov / var
    a = float(er.mean() - b * br.mean())
    a_annual = a * bpy
    return 0.0 if not np.isfinite(a_annual) else a_annual


def correlation(equity: pd.Series, benchmark: pd.Series) -> float:
    """策略与基准的逐周期收益相关系数。高相关 + 低 alpha = 没有独立价值。"""
    er, br = _aligned_returns(equity, benchmark)
    if len(er) < 2:
        return 0.0
    sd = float(er.std(ddof=1)) * float(br.std(ddof=1))
    if sd == 0:
        return 0.0
    return float(np.corrcoef(er, br)[0, 1])


def tracking_error(equity: pd.Series, benchmark: pd.Series, bpy: int) -> float:
    """年化跟踪误差：策略与基准收益差的波动率。"""
    er, br = _aligned_returns(equity, benchmark)
    if len(er) < 2:
        return 0.0
    te = (er - br).std(ddof=1)
    return float(te * np.sqrt(bpy))


def information_ratio(equity: pd.Series, benchmark: pd.Series, bpy: int) -> float:
    """信息比率 = 年化超额收益 / 年化跟踪误差。

    比 Sharpe 更能反映「相对大盘的稳定优势」：Sharpe 高但 IR 低，往往只是
    大盘涨得好，策略本身没有独立 alpha。
    """
    er, br = _aligned_returns(equity, benchmark)
    if len(er) < 2:
        return 0.0
    diff = er - br
    te = diff.std(ddof=1)
    if te == 0:
        return 0.0
    return float(diff.mean() / te * np.sqrt(bpy))


def excess_return(equity: pd.Series, benchmark: pd.Series) -> float:
    """超额总收益 = 策略总收益 - 基准总收益。直观但未考虑风险调整。"""
    if len(equity) < 2 or len(benchmark) < 2 or equity.iloc[0] == 0 or benchmark.iloc[0] == 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0] - 1)
                 - (benchmark.iloc[-1] / benchmark.iloc[0] - 1))


def benchmark_metrics(equity: pd.Series, benchmark: pd.Series, bpy: int) -> dict:
    """基准对比指标打包：beta / alpha / correlation / IR / tracking_error / excess_return。

    benchmark 为空或不可比（长度<2）时全部返回 0，确保下游 JSON 序列化安全、
    前端可一律渲染。注意本函数已把 inf（如基准方差为 0 时回归斜率发散）归零。
    """
    return {
        "beta": beta(equity, benchmark),
        "alpha": alpha(equity, benchmark, bpy),
        "correlation": correlation(equity, benchmark),
        "tracking_error": tracking_error(equity, benchmark, bpy),
        "information_ratio": information_ratio(equity, benchmark, bpy),
        "excess_return": excess_return(equity, benchmark),
    }

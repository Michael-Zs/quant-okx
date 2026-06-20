"""资金分配组合器（Portfolio）：每个策略独立运行、独立持仓，按资金比例合成组合权益。

与 Ensemble 的区别：Ensemble 在信号层合成；Portfolio 在资金/权益层合成。
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

from core.backtest.engine import run, BacktestConfig
from core.backtest import metrics as M


@dataclass
class Allocation:
    strategy: object       # 有 generate_signals 的策略实例
    weight: float          # 相对权重，会归一化


@dataclass
class PortfolioReport:
    equity_curve: pd.DataFrame            # 合成组合权益 ts, equity
    per_strategy: list                    # [(name, weight, BacktestReport), ...]
    metrics: dict
    initial_capital: float


def run_portfolio(allocations: list[Allocation], df: pd.DataFrame,
                  cfg: BacktestConfig, invert: bool = False) -> PortfolioReport:
    total_w = sum(a.weight for a in allocations)
    if total_w <= 0:
        raise ValueError("权重总和必须 > 0")

    per: list = []
    equity_parts: list = []
    all_trades: list = []

    for a in allocations:
        w = a.weight / total_w
        sub_cfg = BacktestConfig(
            initial_capital=cfg.initial_capital * w, leverage=cfg.leverage,
            position_ratio=cfg.position_ratio, fee_rate=cfg.fee_rate,
            slippage=cfg.slippage, side_mode=cfg.side_mode,
            bars_per_year=cfg.bars_per_year)
        sig_df = a.strategy.generate_signals(df)
        rep = run(sig_df, sub_cfg, strategy_name=getattr(a.strategy, "name", "?"),
                  invert=invert)
        per.append((getattr(a.strategy, "name", "?"), w, rep))
        equity_parts.append(rep.equity_curve["equity"].values)
        if not rep.trades.empty:
            all_trades.append(rep.trades)

    combined = np.sum(np.vstack(equity_parts), axis=0)
    combined_s = pd.Series(combined)
    combined_ec = pd.DataFrame({"ts": df["ts"].values, "equity": combined})
    trades_df = (pd.concat(all_trades, ignore_index=True) if all_trades
                 else pd.DataFrame())

    metrics = {
        "total_return": M.total_return(combined_s),
        "annual_return": M.annual_return(combined_s, cfg.bars_per_year),
        "max_drawdown": M.max_drawdown(combined_s),
        "sharpe": M.sharpe(combined_s, cfg.bars_per_year),
        "sortino": M.sortino(combined_s, cfg.bars_per_year),
        "calmar": M.calmar(combined_s, cfg.bars_per_year),
        "volatility": M.volatility(combined_s, cfg.bars_per_year),
        "win_rate": M.win_rate(trades_df),
        "profit_factor": M.profit_factor(trades_df),
        "n_trades": M.n_trades(trades_df),
        "final_capital": float(combined[-1]) if len(combined) else cfg.initial_capital,
    }
    return PortfolioReport(combined_ec, per, metrics, cfg.initial_capital)

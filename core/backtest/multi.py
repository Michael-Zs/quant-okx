"""多币回测引擎：按资金槽模型把资金分配到各 symbol，各自跑单币引擎，合成组合权益。

与 portfolio.py（多策略单 symbol）同构，区别在分配维度是 symbol。复用 engine.run。
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from core.backtest.engine import run, BacktestConfig
from core.backtest import metrics as M


@dataclass
class MultiReport:
    equity_curve: pd.DataFrame    # 合成组合权益 ts, equity
    per_symbol: list              # [(symbol, weight, BacktestReport), ...]
    metrics: dict
    holdings: pd.DataFrame        # ts + 各 symbol 的 signal(持仓方向)，轮动热力图用
    initial_capital: float
    benchmark_curve: pd.DataFrame = field(default_factory=pd.DataFrame)   # 合成组合基准权益 ts, equity


def run_multi(signals: dict[str, pd.DataFrame], cfg: BacktestConfig,
              allocation: dict[str, float] | None = None,
              invert: bool = False) -> MultiReport:
    symbols = list(signals.keys())
    if not symbols:
        raise ValueError("run_multi 至少需要一个 symbol 的信号")

    if allocation is None:
        allocation = {s: 1.0 / len(symbols) for s in symbols}
    total_w = sum(allocation.values()) or 1.0

    per: list = []
    equity_parts: list = []
    benchmark_parts: list = []
    holdings_cols: dict = {}

    for sym in symbols:
        w = allocation.get(sym, 0.0) / total_w
        sub_cfg = BacktestConfig(
            initial_capital=cfg.initial_capital * w, leverage=cfg.leverage,
            position_ratio=cfg.position_ratio, fee_rate=cfg.fee_rate,
            slippage=cfg.slippage, side_mode=cfg.side_mode,
            bars_per_year=cfg.bars_per_year)
        sig_df = signals[sym]
        rep = run(sig_df, sub_cfg, strategy_name=sym, invert=invert)
        per.append((sym, w, rep))
        equity_parts.append(rep.equity_curve["equity"].values)
        benchmark_parts.append(rep.benchmark_curve["equity"].values
                               if not rep.benchmark_curve.empty else 0.0)
        holdings_cols[sym] = sig_df["signal"].fillna(0).astype(int).values

    combined = np.sum(np.vstack(equity_parts), axis=0)
    benchmark_combined = (np.sum(np.vstack(benchmark_parts), axis=0)
                          if benchmark_parts else np.array([]))
    combined_s = pd.Series(combined)
    benchmark_s = pd.Series(benchmark_combined) if len(benchmark_combined) else None
    ts = signals[symbols[0]]["ts"].values
    combined_ec = pd.DataFrame({"ts": ts, "equity": combined})

    trades_all = pd.concat(
        [r.trades.assign(symbol=sym) for sym, _, r in per if not r.trades.empty],
        ignore_index=True) if any(not r.trades.empty for _, _, r in per) else pd.DataFrame()

    metrics = {
        "total_return": M.total_return(combined_s),
        "annual_return": M.annual_return(combined_s, cfg.bars_per_year),
        "max_drawdown": M.max_drawdown(combined_s),
        "sharpe": M.sharpe(combined_s, cfg.bars_per_year),
        "sortino": M.sortino(combined_s, cfg.bars_per_year),
        "calmar": M.calmar(combined_s, cfg.bars_per_year),
        "volatility": M.volatility(combined_s, cfg.bars_per_year),
        "win_rate": M.win_rate(trades_all),
        "profit_factor": M.profit_factor(trades_all),
        "n_trades": M.n_trades(trades_all),
        "final_capital": float(combined[-1]) if len(combined) else cfg.initial_capital,
    }
    # 多币组合的基准是各币 buy & hold 的资金加权合成（与组合权益同口径、同窗口），
    # 用以判断组合的超额收益来自配置轮动还是单纯跟币圈大盘。
    benchmark_curve = pd.DataFrame()
    if benchmark_s is not None and len(benchmark_s) >= 2:
        metrics["benchmark"] = M.benchmark_metrics(combined_s, benchmark_s, cfg.bars_per_year)
        benchmark_curve = pd.DataFrame({"ts": ts, "equity": benchmark_combined})

    holdings = pd.DataFrame(holdings_cols)
    holdings.insert(0, "ts", ts)
    return MultiReport(combined_ec, per, metrics, holdings, cfg.initial_capital,
                       benchmark_curve=benchmark_curve)

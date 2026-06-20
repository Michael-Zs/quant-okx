"""资金层组合回测：AllocationGroup 的回测消费者。

AllocationGroup（core/strategy/node.py）只 collect 各子信号 + weight/invert，
不碰回测；本模块是它的回测消费者——按 weight 切分资金、各子独立回测、权益相加。
本文件属 backtest 层，import engine / metrics 合法（依赖方向向下）。

与 core/backtest/multi.py 的区别：multi 按 symbol 分配资金（多币资金槽），
本文件按子策略分配资金（多策略资金槽）——两者都是「各跑独立回测再合成权益」。
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

from core.backtest.engine import run, BacktestConfig
from core.backtest import metrics as M
from core.backtest.report import BacktestReport


@dataclass
class PortfolioReport:
    equity_curve: pd.DataFrame            # 合成组合权益 ts, equity
    per_strategy: list                    # [(name, weight, BacktestReport), ...]
    metrics: dict
    initial_capital: float


def _child_name(childref) -> str:
    """子节点显示名：优先 name，回退 template_name。"""
    node = childref.node
    return getattr(node, "name", "") or getattr(node, "template_name", "") or "?"


def _run_child(signals, sub_cfg: BacktestConfig, childref) -> BacktestReport:
    """对一个子（按其 childref.invert）回测其全部 symbol。

    collect 返回的 signals 已含子节点自身的 invert（generate_signals 内应用）；
    此处再应用 childref.invert（该子在组内的额外反向），实现链路级 XOR。
    单 symbol 走 run，多 symbol 走 run_multi（资金槽）。
    """
    syms = list(signals.keys())
    if len(syms) == 1:
        sym = syms[0]
        return run(signals[sym], sub_cfg,
                   strategy_name=_child_name(childref), symbol=sym, invert=childref.invert)
    from core.backtest.multi import run_multi
    return run_multi(signals, sub_cfg, invert=childref.invert)


def run_group(group, ctx, cfg: BacktestConfig) -> PortfolioReport:
    """资金层组合回测：各子按 weight 切分资金、独立回测、权益相加。

    group: AllocationGroup（core/strategy/node.py）
    ctx: NodeContext
    """
    items = group.collect(ctx)            # [(ChildRef, Signals)]
    total_w = sum(c.weight for c, _ in items)
    if total_w <= 0:
        raise ValueError("资金层组合的权重总和必须 > 0")

    per: list = []
    equity_parts: list = []
    all_trades: list = []
    ref_ts = None

    for c, signals in items:
        w = c.weight / total_w
        sub_cfg = cfg.scale_capital(w)
        rep = _run_child(signals, sub_cfg, c)
        if ref_ts is None and not rep.equity_curve.empty:
            ref_ts = rep.equity_curve["ts"].values
        per.append((_child_name(c), w, rep))
        equity_parts.append(rep.equity_curve["equity"].values)
        if not rep.trades.empty:
            all_trades.append(rep.trades)

    combined = np.sum(np.vstack(equity_parts), axis=0) if equity_parts else np.array([])
    combined_s = pd.Series(combined)
    ts = ref_ts if ref_ts is not None else np.array([])
    combined_ec = pd.DataFrame({"ts": ts, "equity": combined})
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

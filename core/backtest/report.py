"""回测结果封装。"""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class BacktestReport:
    equity_curve: pd.DataFrame    # 列: ts, equity
    trades: pd.DataFrame          # 列: ts, side(long/short/close), price, pnl, equity, size, dir
    metrics: dict                 # 绩效指标字典
    config: dict = field(default_factory=dict)   # 回测配置快照
    strategy_name: str = ""
    symbol: str = ""
    bar: str = ""

    @property
    def total_return(self) -> float:
        return self.metrics.get("total_return", 0.0)

    @property
    def max_drawdown(self) -> float:
        return self.metrics.get("max_drawdown", 0.0)

    @property
    def sharpe(self) -> float:
        return self.metrics.get("sharpe", 0.0)

    def short_summary(self) -> str:
        m = self.metrics
        return (f"总收益 {m.get('total_return',0):.2%} | 年化 {m.get('annual_return',0):.2%} | "
                f"最大回撤 {m.get('max_drawdown',0):.2%} | 夏普 {m.get('sharpe',0):.2f} | "
                f"胜率 {m.get('win_rate',0):.2%} | 交易 {m.get('n_trades',0)} 次")

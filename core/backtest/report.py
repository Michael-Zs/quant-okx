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


@dataclass
class BacktestOutcome:
    """统一回测结果（run_node 产出）：对前端 / API 序列化友好的标准结构。

    无论底层是单 symbol、多 symbol 资金槽、还是资金层组合，都归一为这同一结构，
    前端不必关心 report_kind 差异（per_leg 提供各子明细供组合页展开）。
    """
    equity_curve: pd.DataFrame    # ts, equity
    metrics: dict
    trades: pd.DataFrame
    report_kind: str = ""         # single | multi | group
    per_leg: list = field(default_factory=list)   # [(name, weight, BacktestReport), ...]
    config: dict = field(default_factory=dict)
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

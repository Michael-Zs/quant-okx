"""回测引擎：逐 K 线 mark-to-market，支持手续费/滑点/仅多/多空。

仓位模型：每次用 cash * position_ratio * leverage 作为名义价值开仓；
盈亏 = (price - entry) * dir * size，其中 size = notional / entry，
等价于 (price-entry)/entry * dir * capital * leverage * position_ratio。

统一节点抽象后的增强：
- ``BacktestConfig.scale_capital(weight)`` 收口资金切分（消除原 portfolio/multi 逐字段复制）。
- ``run`` 的 invert 改用统一的 ``invert_df``（与 trader/daemon/node 同源）。
- ``run_node(node, ctx, cfg)`` 统一回测入口：按 node_type 分派到 run / run_multi / run_group，
  归一为 ``BacktestOutcome`` 供前端 / API 消费。
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from core.backtest import metrics as M
from core.backtest.report import BacktestReport, BacktestOutcome
from core.strategy.invert import invert_df


@dataclass
class BacktestConfig:
    initial_capital: float = 10000.0
    leverage: float = 5.0
    position_ratio: float = 0.1
    fee_rate: float = 0.0005       # 单边手续费率（OKX taker ~0.05%）
    slippage: float = 0.0005       # 滑点比例
    side_mode: str = "long_short"  # long_only | long_short
    bars_per_year: int = 8760      # 由周期推断，年化用

    def scale_capital(self, weight: float) -> "BacktestConfig":
        """返回 initial_capital 按 weight 缩放的新配置，其余字段不变。

        统一了原 strategy/portfolio.py、backtest/multi.py 各自逐字段复制 BacktestConfig
        的重复，且新增 BacktestConfig 字段时不会因遗漏而静默用默认值。
        """
        return BacktestConfig(
            initial_capital=self.initial_capital * weight,
            leverage=self.leverage, position_ratio=self.position_ratio,
            fee_rate=self.fee_rate, slippage=self.slippage,
            side_mode=self.side_mode, bars_per_year=self.bars_per_year,
        )


def _build_metrics(equity: pd.Series, trades: pd.DataFrame, bpy: int, init: float) -> dict:
    return {
        "total_return": M.total_return(equity),
        "annual_return": M.annual_return(equity, bpy),
        "max_drawdown": M.max_drawdown(equity),
        "sharpe": M.sharpe(equity, bpy),
        "sortino": M.sortino(equity, bpy),
        "calmar": M.calmar(equity, bpy),
        "volatility": M.volatility(equity, bpy),
        "win_rate": M.win_rate(trades),
        "profit_factor": M.profit_factor(trades),
        "n_trades": M.n_trades(trades),
        "final_capital": float(equity.iloc[-1]) if len(equity) else init,
    }


def run(df: pd.DataFrame, cfg: BacktestConfig | None = None,
        strategy_name: str = "", symbol: str = "", bar: str = "",
        invert: bool = False) -> BacktestReport:
    """对含 signal 列的 OHLCV df 跑回测。invert=True 时反转信号方向（1↔-1）。"""
    cfg = cfg or BacktestConfig()
    if "signal" not in df.columns:
        raise ValueError("回测需要 df 含 'signal' 列")
    if invert:
        df = invert_df(df)
    if df.empty:
        empty = pd.DataFrame(columns=["ts", "equity"])
        return BacktestReport(empty, pd.DataFrame(), {}, asdict(cfg), strategy_name, symbol, bar)

    sig = df["signal"].fillna(0).astype(int).to_numpy()
    if cfg.side_mode == "long_only":
        sig = np.where(sig < 0, 0, sig)
    price = df["close"].to_numpy()
    ts = df["ts"].to_numpy()

    cash = cfg.initial_capital
    pos_dir = 0
    size = 0.0
    entry_price = 0.0
    equity_arr = np.empty(len(df))
    trades: list[dict] = []

    for i in range(len(df)):
        p = price[i]

        # 1) mark-to-market：记录当前权益（含未实现盈亏）
        if pos_dir != 0 and size > 0:
            equity_arr[i] = cash + (p - entry_price) * pos_dir * size
        else:
            equity_arr[i] = cash

        # 2) 换仓：目标方向与当前方向不同
        target = int(sig[i])
        if target != pos_dir:
            # 平旧仓
            if pos_dir != 0 and size > 0:
                fill = p * (1 - cfg.slippage * pos_dir)
                realized = (fill - entry_price) * pos_dir * size
                cash += realized
                cash -= abs(size * fill) * cfg.fee_rate
                trades.append({"ts": ts[i], "side": "close", "price": float(fill),
                               "pnl": float(realized), "equity": float(cash),
                               "size": float(size), "dir": int(pos_dir)})
                size = 0.0
                pos_dir = 0
            # 开新仓
            if target != 0:
                notional = cash * cfg.position_ratio * cfg.leverage
                fill = p * (1 + cfg.slippage * target)
                size = notional / fill if fill > 0 else 0.0
                entry_price = fill
                cash -= abs(notional) * cfg.fee_rate
                pos_dir = target
                trades.append({"ts": ts[i],
                               "side": "long" if target == 1 else "short",
                               "price": float(fill), "pnl": 0.0, "equity": float(cash),
                               "size": float(size), "dir": int(target)})

    equity = pd.Series(equity_arr)
    equity_curve = pd.DataFrame({"ts": df["ts"].values, "equity": equity_arr})
    trades_df = pd.DataFrame(trades)
    metrics = _build_metrics(equity, trades_df, cfg.bars_per_year, cfg.initial_capital)
    return BacktestReport(equity_curve, trades_df, metrics, asdict(cfg),
                          strategy_name, symbol, bar)


def run_node(node, ctx, cfg: BacktestConfig | None = None,
             symbol: str = "", bar: str = "") -> BacktestOutcome:
    """统一回测入口：对任意 StrategyNode 回测，返回标准化的 BacktestOutcome。

    按 node_type 分派：
    - allocation_group → run_group（各子按 weight 切分资金，资金层组合）；
    - leaf / signal_combiner → generate_signals 后按 symbol 数走：
      单 symbol → run；多 symbol → run_multi（资金槽模型）。
    run_multi / run_group 延迟 import 以避免 engine ↔ multi/portfolio 循环。
    """
    cfg = cfg or BacktestConfig()
    nt = getattr(node, "node_type", "leaf")
    name = getattr(node, "name", "")

    if nt == "allocation_group":
        from core.backtest.portfolio import run_group
        rep = run_group(node, ctx, cfg)
        return BacktestOutcome(
            equity_curve=rep.equity_curve, metrics=rep.metrics,
            trades=_concat_trades([(n, r) for n, _w, r in rep.per_strategy]),
            report_kind="group", per_leg=list(rep.per_strategy),
            config=asdict(cfg), symbol=symbol, bar=bar,
        )

    signals = node.generate_signals(ctx)
    symbols = list(signals.keys())

    if len(symbols) == 1:
        sym = symbols[0]
        rep = run(signals[sym], cfg, strategy_name=name, symbol=sym, bar=bar)
        return BacktestOutcome(
            equity_curve=rep.equity_curve, metrics=rep.metrics, trades=rep.trades,
            report_kind="single", per_leg=[(name, 1.0, rep)],
            config=asdict(cfg), symbol=sym, bar=bar,
        )

    from core.backtest.multi import run_multi
    rep = run_multi(signals, cfg)
    return BacktestOutcome(
        equity_curve=rep.equity_curve, metrics=rep.metrics,
        trades=_concat_trades([(s, r) for s, _w, r in rep.per_symbol]),
        report_kind="multi", per_leg=list(rep.per_symbol),
        config=asdict(cfg), symbol=symbol, bar=bar,
    )


def _concat_trades(named_reports) -> pd.DataFrame:
    """把多个 BacktestReport 的 trades 合并，附 leg 列标识来源。"""
    parts = [r.trades.assign(leg=n) for n, r in named_reports if not r.trades.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

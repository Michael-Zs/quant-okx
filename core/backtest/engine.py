"""回测引擎：逐 K 线 mark-to-market，支持手续费/滑点/仅多/多空。

相对原项目 /home/zsm/Prj/quant/backtest/engine.py 的改进：
- 每根 K 线都按 close 估算未实现盈亏并记录权益，得到连续权益曲线（原版只在平仓点记）。
- 增加手续费（按名义价值）和滑点；仓位/杠杆/多空逻辑与原版一致（复利）。

仓位模型：每次用 cash * position_ratio * leverage 作为名义价值开仓；
盈亏 = (price - entry) * dir * size，其中 size = notional / entry，
等价于原版 (price-entry)/entry * dir * capital * leverage * position_ratio。
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from core.backtest import metrics as M
from core.backtest.report import BacktestReport


@dataclass
class BacktestConfig:
    initial_capital: float = 10000.0
    leverage: float = 5.0
    position_ratio: float = 0.1
    fee_rate: float = 0.0005       # 单边手续费率（OKX taker ~0.05%）
    slippage: float = 0.0005       # 滑点比例
    side_mode: str = "long_short"  # long_only | long_short
    bars_per_year: int = 8760      # 由周期推断，年化用


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
        df = df.copy()
        df["signal"] = (-df["signal"].fillna(0)).astype(int)
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

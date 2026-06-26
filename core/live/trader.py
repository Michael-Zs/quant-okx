"""单轮回测式实盘执行：拉最新K线 → 取策略信号。

被 daemon 每个周期调用一次。策略来源由调用方注入（单策略或 Ensemble）。
**注意**: 对账下单已移至 executor 统一处理，本函数仅返回信号。
"""
from __future__ import annotations

from core.data.fetcher import fetch_recent
from core.strategy.invert import invert_df


def run_once(strategy, symbol: str, bar: str, invert: bool = False) -> dict:
    """计算策略信号（不涉及交易所余额/下单）。

    Args:
        strategy: 策略实例（单策略或 Ensemble）
        symbol: OKX 格式品种
        bar: K 线周期
        invert: 是否反向信号

    Returns:
        {"signal": int, "price": float}
    """
    df = fetch_recent(symbol, bar, limit=300)
    sig_df = strategy.generate_signals(df)
    if invert:
        sig_df = invert_df(sig_df)
    signal = int(sig_df["signal"].fillna(0).iloc[-1])
    price = float(sig_df["close"].iloc[-1])
    return {"signal": signal, "price": price}

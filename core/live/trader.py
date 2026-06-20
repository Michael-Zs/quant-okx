"""单轮回测式实盘执行：拉最新K线 → 取策略信号 → 对齐当前持仓 → 下单。

被 daemon 每个周期调用一次。策略来源由调用方注入（单策略或 Ensemble）。
"""
from __future__ import annotations

from core.data.fetcher import fetch_recent
from core.data.symbols import okx_to_ccxt
from core.live.exchange import get_position, set_leverage, get_balance, market_order
from core.strategy.invert import invert_df


def run_once(ex, strategy, symbol: str, bar: str, leverage: int, position_ratio: float,
             invert: bool = False) -> dict:
    ccxt_sym = okx_to_ccxt(symbol)
    df = fetch_recent(symbol, bar, limit=300)
    sig_df = strategy.generate_signals(df)
    if invert:
        sig_df = invert_df(sig_df)
    signal = int(sig_df["signal"].fillna(0).iloc[-1])
    price = float(sig_df["close"].iloc[-1])

    pos = get_position(ex, ccxt_sym)
    current = pos["dir"]
    actions: list[str] = []

    if signal == current:
        return {"signal": signal, "price": price, "action": "hold",
                "position_dir": current, "position_contracts": pos["contracts"]}

    # 平旧仓
    if current != 0 and pos["contracts"] > 0:
        side = "sell" if current == 1 else "buy"
        market_order(ex, ccxt_sym, side, pos["contracts"], reduce_only=True)
        actions.append(f"平仓 {side} {pos['contracts']:.4f}")

    # 开新仓
    if signal != 0:
        set_leverage(ex, ccxt_sym, leverage)
        balance = get_balance(ex)
        notional = balance * position_ratio * leverage
        amount = round(notional / price, 3)
        if amount > 0:
            side = "buy" if signal == 1 else "sell"
            market_order(ex, ccxt_sym, side, amount)
            actions.append(f"开仓 {side} {amount} @ {price:.2f}")

    return {"signal": signal, "price": price, "action": "; ".join(actions) or "noop",
            "position_dir": current, "position_contracts": pos["contracts"]}

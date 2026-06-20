"""ccxt 封装：连接 OKX（模拟盘/实盘）、查余额/持仓、下单、设杠杆。

复用原项目 /home/zsm/Prj/quant/live/trader.py 的 get_exchange/okx_to_ccxt 逻辑，
按 per-job 的 is_demo 切换沙箱模式。
"""
from __future__ import annotations
import ccxt

from core.utils.config import settings


def get_exchange(is_demo: bool = True) -> ccxt.Exchange:
    if not (settings.OKX_API_KEY and settings.OKX_API_SECRET and settings.OKX_API_PASSPHRASE):
        raise RuntimeError("未配置 OKX API key，请在「设置」页或 .env 填写")
    ex = ccxt.okx({
        "apiKey": settings.OKX_API_KEY,
        "secret": settings.OKX_API_SECRET,
        "password": settings.OKX_API_PASSPHRASE,
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })
    if is_demo:
        ex.set_sandbox_mode(True)
    return ex


def get_balance(ex, quote: str = "USDT") -> float:
    bal = ex.fetch_balance()
    return float(bal.get(quote, {}).get("free", 0) or 0)


def get_position(ex, ccxt_symbol: str) -> dict:
    """返回当前持仓 {dir(1/-1/0), contracts, entry_price, unrealized_pnl}。"""
    positions = ex.fetch_positions([ccxt_symbol])
    for p in positions:
        contracts = p.get("contracts") or 0
        if contracts and contracts > 0:
            side = p.get("side")
            return {
                "dir": 1 if side == "long" else -1,
                "contracts": float(contracts),
                "entry_price": float(p.get("entryPrice") or 0),
                "unrealized_pnl": float(p.get("unrealizedPnl") or 0),
            }
    return {"dir": 0, "contracts": 0.0, "entry_price": 0.0, "unrealized_pnl": 0.0}


def get_positions(ex, ccxt_symbols: list[str]) -> dict[str, dict]:
    """返回多 symbol 持仓 {ccxt_symbol: {dir, contracts, entry_price, unrealized_pnl}}。

    一次 fetch_positions 批量查询；无持仓的 symbol 返回零仓位占位。
    """
    out = {s: {"dir": 0, "contracts": 0.0, "entry_price": 0.0, "unrealized_pnl": 0.0}
           for s in ccxt_symbols}
    if not ccxt_symbols:
        return out
    for p in ex.fetch_positions(ccxt_symbols):
        sym = p.get("symbol")
        contracts = p.get("contracts") or 0
        if sym in out and contracts and contracts > 0:
            side = p.get("side")
            out[sym] = {"dir": 1 if side == "long" else -1, "contracts": float(contracts),
                        "entry_price": float(p.get("entryPrice") or 0),
                        "unrealized_pnl": float(p.get("unrealizedPnl") or 0)}
    return out


def set_leverage(ex, ccxt_symbol: str, leverage: int):
    try:
        ex.set_leverage(int(leverage), ccxt_symbol)
    except Exception:
        pass  # 某些账户/品种设置失败可忽略


def market_order(ex, ccxt_symbol: str, side: str, amount: float, reduce_only: bool = False):
    params = {"reduceOnly": True} if reduce_only else {}
    return ex.create_order(ccxt_symbol, "market", side, amount, params=params)

"""OKX / ccxt 品种与周期转换、常量。

约定：
- 内部用 OKX 格式 symbol：合约 `BTC-USDT-SWAP`、现货 `BTC-USDT`
- 内部用 OKX 格式 bar（大写 H/D）：`1H` `4H` `1D`（REST API 要求大写）
- ccxt timeframe 用小写：`1h` `4h` `1d`（仅实盘下单/查持仓时需要）
"""
from __future__ import annotations

# OKX bar -> 毫秒（用于年化、缓存增量判断、回测周期换算）
BAR_TO_MS: dict[str, int] = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1H": 3_600_000, "2H": 7_200_000, "4H": 14_400_000, "6H": 21_600_000,
    "12H": 43_200_000, "1D": 86_400_000, "2D": 172_800_000, "3D": 259_200_000,
    "1W": 604_800_000, "1M": 2_592_000_000,
}

# UI 可选周期
COMMON_BARS = ["15m", "1H", "4H", "1D"]


def okx_to_ccxt_tf(bar: str) -> str:
    """OKX bar(1H/1D) -> ccxt timeframe(1h/1d)。"""
    return bar[:-1] + bar[-1].lower()


def ccxt_to_okx_bar(tf: str) -> str:
    """ccxt timeframe(1h/1d) -> OKX bar(1H/1D)。"""
    return tf[:-1] + tf[-1].upper()


def okx_to_ccxt(symbol: str) -> str:
    """OKX symbol -> ccxt symbol。
    合约 BTC-USDT-SWAP -> BTC/USDT:USDT
    现货 BTC-USDT     -> BTC/USDT
    """
    parts = symbol.split("-")
    if len(parts) == 3:  # 合约
        base, quote, _ = parts
        return f"{base}/{quote}:{quote}"
    if len(parts) == 2:  # 现货
        return f"{parts[0]}/{parts[1]}"
    return symbol


def is_swap(symbol: str) -> bool:
    return symbol.endswith("-SWAP")


def bars_per_year(bar: str) -> int:
    """该周期一年（按 365 天）的 K 线数，用于年化收益/夏普。"""
    ms = BAR_TO_MS.get(bar, 3_600_000)
    return max(1, int(round(365 * 24 * 3_600_000 / ms)))


# UI 默认品种（合约为主；可由 API 动态拉取完整列表）
COMMON_SYMBOLS = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
    "BNB-USDT-SWAP", "XRP-USDT-SWAP", "DOGE-USDT-SWAP",
]

"""多币种数据加载与时间对齐。

取各 symbol 的 OHLCV，对齐到所有 symbol 都有数据的公共时间轴（交集），
保证每个 symbol 的 df 长度与 ts 完全一致，便于跨币种截面计算。
新增币种零改动：传入任意 symbol 列表即可。
"""
from __future__ import annotations
import pandas as pd

from core.data.cache import get_data


def get_multi(symbols: list[str], bar: str = "1H", days: int = 180,
              use_cache: bool = True, refresh: bool = False) -> dict[str, pd.DataFrame]:
    """加载多个 symbol，对齐到公共时间轴，返回 {symbol: df(ts,open,high,low,close,vol)}。"""
    raw: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = get_data(sym, bar, days, use_cache=use_cache, refresh=refresh)
        if df is not None and not df.empty:
            raw[sym] = df

    if not raw:
        return {}

    # 公共时间轴：所有 symbol 都有的 ts（交集）
    index_sets = [set(d["ts"]) for d in raw.values()]
    common_ts = sorted(set.intersection(*index_sets))
    if not common_ts:
        return {}

    aligned: dict[str, pd.DataFrame] = {}
    cols = ["ts", "open", "high", "low", "close", "vol"]
    for sym, df in raw.items():
        a = df[df["ts"].isin(common_ts)].copy()
        a = a.sort_values("ts").reset_index(drop=True)
        aligned[sym] = a[cols]
    return aligned

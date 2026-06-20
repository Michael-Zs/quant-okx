"""本地 parquet 缓存 + 增量更新。

缓存键：`{symbol}_{bar}.parquet`，存「截至某 ts 的全量」。
访问时若距上次更新超过一个 bar 周期，只补拉增量并合并去重，再按 days 截取。
"""
from __future__ import annotations
import time
import pandas as pd

from core.utils.config import settings
from core.data.symbols import BAR_TO_MS
from core.data.fetcher import fetch_history, fetch_candles, _to_df


def _path(symbol: str, bar: str) -> "Path":
    return settings.CACHE_DIR / f"{symbol.replace('-', '_')}_{bar}.parquet"


def load_cached(symbol: str, bar: str) -> pd.DataFrame | None:
    p = _path(symbol, bar)
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            return None
    return None


def save_cache(symbol: str, bar: str, df: pd.DataFrame) -> None:
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_path(symbol, bar), index=False)


def _fetch_increment(symbol: str, bar: str, since_ms: int) -> pd.DataFrame:
    """拉取 since_ms 之后的增量 K 线（公开 API）。"""
    new_rows: list = []
    after = None
    # 最多翻 20 页，足够补几天的增量
    for _ in range(20):
        rows = fetch_candles(symbol, bar, limit=300, after=after)
        if not rows:
            break
        new_rows.extend(rows)
        oldest = int(rows[-1][0])
        if oldest <= since_ms:
            break
        after = str(oldest)
        time.sleep(0.2)
    return _to_df(new_rows) if new_rows else pd.DataFrame(
        columns=["ts", "open", "high", "low", "close", "vol"])


def get_data(symbol: str, bar: str = "1H", days: int = 365,
             use_cache: bool = True, refresh: bool = False) -> pd.DataFrame:
    """获取数据：优先缓存 + 增量，否则全量拉取。返回最近 days 天。"""
    cached = load_cached(symbol, bar) if (use_cache and not refresh) else None

    # 缓存覆盖的天数是否满足请求？不足则全量重拉（避免返回不足的历史）
    span_ok = (cached is not None and not cached.empty and len(cached) >= 2
               and (cached["ts"].iloc[-1] - cached["ts"].iloc[0]).total_seconds() / 86400 >= days * 0.98)

    if span_ok:
        bar_ms = BAR_TO_MS.get(bar, 3_600_000)
        last_ts_ms = int(cached["ts"].iloc[-1].timestamp() * 1000)
        now_ms = int(time.time() * 1000)
        if now_ms - last_ts_ms >= bar_ms:
            try:
                inc = _fetch_increment(symbol, bar, last_ts_ms)
                if not inc.empty:
                    cached = (pd.concat([cached, inc])
                              .drop_duplicates("ts")
                              .sort_values("ts")
                              .reset_index(drop=True))
                    save_cache(symbol, bar, cached)
            except Exception:
                pass  # 增量失败时退回旧缓存
    else:
        cached = fetch_history(symbol, bar, days)
        if not cached.empty:
            save_cache(symbol, bar, cached)

    if cached is None or cached.empty:
        return cached if cached is not None else pd.DataFrame(
            columns=["ts", "open", "high", "low", "close", "vol"])

    cutoff = cached["ts"].iloc[-1] - pd.Timedelta(days=days)
    return cached[cached["ts"] >= cutoff].reset_index(drop=True)


def clear_cache(symbol: str | None = None, bar: str | None = None) -> int:
    """清缓存。不传参则清全部。返回删除文件数。"""
    n = 0
    if symbol:
        for p in settings.CACHE_DIR.glob(f"{symbol.replace('-', '_')}_*.parquet"):
            p.unlink()
            n += 1
    else:
        for p in settings.CACHE_DIR.glob("*.parquet"):
            p.unlink()
            n += 1
    return n

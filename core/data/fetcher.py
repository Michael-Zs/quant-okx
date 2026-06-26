"""OKX 历史 K 线拉取（公开 REST API，无需鉴权）。

复用原项目 /home/zsm/Prj/quant/data/fetcher.py 的分页逻辑，统一返回
带 UTC 时区的 OHLCV DataFrame: ["ts","open","high","low","close","vol"]。
"""
from __future__ import annotations
import json
import time
import requests
import pandas as pd

import core.utils.okx_dns  # noqa: F401  国内 DNS 污染绕行（www.okx.com → 真实 IP），必须在任何 OKX 请求前

BASE_URL = "https://www.okx.com"


def _to_df(rows: list) -> pd.DataFrame:
    """把 OKX 返回的原始行列表转成标准 OHLCV DataFrame。"""
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "vol"])
    df = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"
    ])
    df = df[df["confirm"] == "1"].copy()  # 只保留已收盘 K 线
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    for c in ["open", "high", "low", "close", "vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open"]).sort_values("ts").reset_index(drop=True)
    return df[["ts", "open", "high", "low", "close", "vol"]]


def fetch_candles(symbol: str, bar: str = "1H", limit: int = 300, after: str | None = None) -> list:
    """单次拉取（最多 300 根）。after 为更早的分页游标（毫秒时间戳字符串）。"""
    params = {"instId": symbol, "bar": bar, "limit": limit}
    if after:
        params["after"] = after
    r = requests.get(f"{BASE_URL}/api/v5/market/history-candles", params=params, timeout=10)
    r.raise_for_status()
    return r.json()["data"]


def fetch_history(symbol: str, bar: str = "1H", days: int = 365) -> pd.DataFrame:
    """分页拉取最近 `days` 天历史 K 线。"""
    all_rows: list = []
    after = None
    target = int(time.time() * 1000) - days * 86_400_000
    while True:
        rows = fetch_candles(symbol, bar, limit=300, after=after)
        if not rows:
            break
        all_rows.extend(rows)
        oldest = int(rows[-1][0])
        if oldest <= target:
            break
        after = str(oldest)
        time.sleep(0.2)  # 避免触发频率限制
    return _to_df(all_rows)


def fetch_recent(symbol: str, bar: str = "1H", limit: int = 300) -> pd.DataFrame:
    """拉取最近 `limit` 根 K 线（实盘信号用）。"""
    rows = fetch_candles(symbol, bar, limit=limit)
    return _to_df(rows)


def list_swap_instruments(quote: str = "USDT", refresh: bool = False) -> list[str]:
    """拉取所有 USDT 本位永续合约品种（公开 API，带 1 天文件缓存）。

    新增币种零改动：UI 直接用这个列表让用户选任意品种。
    """
    from core.utils.config import settings
    cache_path = settings.CACHE_DIR / f"swap_instruments_{quote}.json"
    if not refresh and cache_path.exists():
        try:
            if time.time() - cache_path.stat().st_mtime < 86400:
                return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    r = requests.get(f"{BASE_URL}/api/v5/public/instruments",
                     params={"instType": "SWAP"}, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    syms = sorted(d["instId"] for d in data
                  if d.get("settleCcy") == quote and d.get("state") == "live")
    try:
        settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(syms), encoding="utf-8")
    except Exception:
        pass
    return syms

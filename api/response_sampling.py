"""回测响应采样工具。

只对返回体做展示级压缩，不影响 metrics 的计算基础数据。
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def normalize_max_points(max_points: int | None) -> int | None:
    if max_points is None:
        return None
    if max_points <= 0:
        return None
    return max(2, int(max_points))


def sampled_index(length: int, max_points: int | None) -> list[int]:
    if length <= 0:
        return []
    cap = normalize_max_points(max_points)
    if cap is None or length <= cap:
        return list(range(length))
    if cap == 1:
        return [length - 1]
    last = length - 1
    idx = sorted({round(i * last / (cap - 1)) for i in range(cap)})
    if idx[0] != 0:
        idx[0] = 0
    if idx[-1] != last:
        idx[-1] = last
    return idx


def sample_curve(df: pd.DataFrame, value_col: str, max_points: int | None) -> dict[str, Any] | None:
    if df is None or df.empty:
        return None
    idx = sampled_index(len(df), max_points)
    sampled = df.iloc[idx]
    return {
        "ts": [str(t) for t in sampled["ts"].tolist()],
        value_col: [float(x) for x in sampled[value_col].tolist()],
        "sampled": len(sampled) != len(df),
        "total_points": int(len(df)),
        "returned_points": int(len(sampled)),
    }


def sample_holdings(df: pd.DataFrame, max_points: int | None) -> dict[str, Any]:
    idx = sampled_index(len(df), max_points)
    sampled = df.iloc[idx] if len(idx) else df.iloc[0:0]
    symbols = [c for c in df.columns if c != "ts"]
    return {
        "ts": [str(t) for t in sampled["ts"].tolist()],
        "symbols": symbols,
        "matrix": [[int(v) for v in sampled[s].tolist()] for s in symbols],
        "sampled": len(sampled) != len(df),
        "total_points": int(len(df)),
        "returned_points": int(len(sampled)),
    }


"""回测响应采样工具。

只对返回体做展示级压缩，不影响 metrics 的计算基础数据。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from core.backtest import metrics as M


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


def summarize_equity(df: pd.DataFrame) -> dict[str, Any] | None:
    if df is None or df.empty:
        return None
    equity = pd.Series(df["equity"].to_numpy())
    peak_idx = int(equity.idxmax())
    trough_idx = int(equity.idxmin())
    dd = M.drawdown_series(equity)
    dd_end = int(dd.idxmax()) if len(dd) else 0
    dd_start = int(equity.iloc[: dd_end + 1].idxmax()) if len(equity) else 0
    return {
        "start_ts": str(df["ts"].iloc[0]),
        "start_equity": float(equity.iloc[0]),
        "end_ts": str(df["ts"].iloc[-1]),
        "end_equity": float(equity.iloc[-1]),
        "peak_ts": str(df["ts"].iloc[peak_idx]),
        "peak_equity": float(equity.iloc[peak_idx]),
        "trough_ts": str(df["ts"].iloc[trough_idx]),
        "trough_equity": float(equity.iloc[trough_idx]),
        "max_drawdown": float(dd.iloc[dd_end]) if len(dd) else 0.0,
        "max_drawdown_start_ts": str(df["ts"].iloc[dd_start]),
        "max_drawdown_start_equity": float(equity.iloc[dd_start]),
        "max_drawdown_end_ts": str(df["ts"].iloc[dd_end]),
        "max_drawdown_end_equity": float(equity.iloc[dd_end]),
    }


def summarize_trades(trades: pd.DataFrame, bars_per_year: int | None = None,
                     initial_capital: float | None = None) -> dict[str, Any]:
    if trades is None or trades.empty:
        return {
            "n_entries": 0,
            "n_long_entries": 0,
            "n_short_entries": 0,
            "n_closes": 0,
            "switch_count": 0,
            "avg_hold_bars": 0.0,
            "turnover": 0.0,
        }

    entries = trades[trades["side"].isin(["long", "short"])].copy() if "side" in trades.columns else trades.iloc[0:0]
    closes = trades[trades["side"] == "close"].copy() if "side" in trades.columns else trades.iloc[0:0]
    hold_bars: list[int] = []
    last_entry_idx: int | None = None
    last_entry_dir: int | None = None
    switch_count = 0

    for i, row in trades.reset_index(drop=True).iterrows():
        side = row.get("side")
        if side in {"long", "short"}:
            cur_dir = int(row.get("dir", 0))
            if last_entry_dir is not None and cur_dir != last_entry_dir:
                switch_count += 1
            last_entry_idx = i
            last_entry_dir = cur_dir
        elif side == "close" and last_entry_idx is not None:
            hold_bars.append(i - last_entry_idx)
            last_entry_idx = None

    turnover_notional = 0.0
    if {"size", "price"}.issubset(trades.columns):
        turnover_notional = float((trades["size"].abs() * trades["price"].abs()).sum())
    turnover = turnover_notional / initial_capital if initial_capital and initial_capital > 0 else turnover_notional

    return {
        "n_entries": int(len(entries)),
        "n_long_entries": int((entries["side"] == "long").sum()) if "side" in entries else 0,
        "n_short_entries": int((entries["side"] == "short").sum()) if "side" in entries else 0,
        "n_closes": int(len(closes)),
        "switch_count": int(switch_count),
        "avg_hold_bars": float(sum(hold_bars) / len(hold_bars)) if hold_bars else 0.0,
        "turnover": float(turnover),
        "bars_per_year": int(bars_per_year) if bars_per_year else None,
    }

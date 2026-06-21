"""参数网格搜索：穷举参数组合，返回按目标指标排序的结果列表。"""
from __future__ import annotations
from copy import deepcopy
from itertools import product
import numpy as np

from core.backtest.engine import run, BacktestConfig
from core.backtest.multi import run_multi
from core.data.cache import get_data
from core.strategy.node import NodeContext, node_from_spec


def arange_values(lo: float, hi: float, step: float, limit: int = 200) -> list:
    """生成 [lo, hi] 步长 step 的去重值列表（含 hi），带数量上限保护。"""
    if step == 0 or hi < lo:
        return [float(lo)]
    arr = np.arange(lo, hi + step * 0.5, step)
    vals = sorted(set(round(float(x), 6) for x in arr))
    return vals[:limit]


def grid_search(strategy_cls, df, cfg: BacktestConfig, param_grid: dict,
                metric: str = "total_return", top_n: int | None = None,
                n_jobs: int = 1) -> list[dict]:
    """穷举 param_grid（{参数名: [取值]}）的所有组合，回测并按 metric 降序排序。

    返回全部结果（list[dict]，每个含参数 + 各指标）；top_n 不为空则截断。
    """
    keys = list(param_grid.keys())
    if not keys:
        return []
    combos = list(product(*[param_grid[k] for k in keys]))

    def run_one(combo):
        params = dict(zip(keys, combo))
        try:
            sig = strategy_cls(**params).generate_signals(df)
            rep = run(sig, cfg, strategy_name=strategy_cls.name)
            m = rep.metrics
            row = dict(params)
            row.update({
                "total_return": m["total_return"], "sharpe": m["sharpe"],
                "max_drawdown": m["max_drawdown"], "sortino": m["sortino"],
                "calmar": m["calmar"], "win_rate": m["win_rate"],
                "n_trades": m["n_trades"],
            })
            return row
        except Exception:
            return None

    if n_jobs and n_jobs > 1 and len(combos) > 1:
        from joblib import Parallel, delayed
        raw = Parallel(n_jobs=n_jobs)(delayed(run_one)(c) for c in combos)
    else:
        raw = [run_one(c) for c in combos]

    results = [r for r in raw if r]
    results.sort(key=lambda x: x.get(metric, -1e18), reverse=True)
    return results if top_n is None else results[:top_n]


def grid_search_multi(*, node_spec: dict, symbols: list[str], bar: str, days_list: list[int],
                      cfg: BacktestConfig, param_grid: dict, metric: str = "total_return",
                      allocation: dict[str, float] | None = None, invert: bool = False,
                      top_n: int | None = None, n_jobs: int = 1) -> list[dict]:
    """多币参数搜索：对 node_spec.params 穷举参数组合，并在多个 days 窗口聚合评分。"""
    keys = list(param_grid.keys())
    if not keys:
        return []
    combos = list(product(*[param_grid[k] for k in keys]))
    day_values = days_list or [180]

    def run_one(combo):
        params = dict(zip(keys, combo))
        metrics_by_days: dict[int, dict] = {}
        try:
            for days in day_values:
                spec = deepcopy(node_spec)
                spec.setdefault("params", {})
                spec["params"].update(params)
                data = {sym: get_data(sym, bar, days) for sym in symbols}
                ctx = NodeContext(data=data, primary_symbol=symbols[0], bar=bar)
                node = node_from_spec(spec)
                signals = node.generate_signals(ctx)
                rep = run_multi(signals, cfg, allocation=allocation, invert=invert)
                metrics_by_days[int(days)] = rep.metrics
            row = dict(params)
            primary = metrics_by_days[int(day_values[0])]
            row.update({
                "total_return": primary["total_return"],
                "sharpe": primary["sharpe"],
                "max_drawdown": primary["max_drawdown"],
                "sortino": primary["sortino"],
                "calmar": primary["calmar"],
                "win_rate": primary["win_rate"],
                "n_trades": primary["n_trades"],
                "windows": metrics_by_days,
                "window_count": len(metrics_by_days),
                "min_total_return": min(m["total_return"] for m in metrics_by_days.values()),
                "max_drawdown_worst": max(m["max_drawdown"] for m in metrics_by_days.values()),
                "avg_sharpe": float(np.mean([m["sharpe"] for m in metrics_by_days.values()])),
            })
            if metric == "robust_score":
                row["robust_score"] = row["avg_sharpe"] + row["min_total_return"] - row["max_drawdown_worst"]
            return row
        except Exception:
            return None

    if n_jobs and n_jobs > 1 and len(combos) > 1:
        from joblib import Parallel, delayed
        raw = Parallel(n_jobs=n_jobs)(delayed(run_one)(c) for c in combos)
    else:
        raw = [run_one(c) for c in combos]

    results = [r for r in raw if r]
    key = metric if metric != "robust_score" else "robust_score"
    results.sort(key=lambda x: x.get(key, -1e18), reverse=True)
    return results if top_n is None else results[:top_n]

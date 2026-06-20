"""参数网格搜索：穷举参数组合，返回按目标指标排序的结果列表。"""
from __future__ import annotations
from itertools import product
import numpy as np

from core.backtest.engine import run, BacktestConfig


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

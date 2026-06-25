"""控制类路由（POST/PUT/DELETE）：回测、部署管理。全部需 token。

- POST /api/backtest：统一吃 node_spec 或 ref_id，经 run_node 回测，结果落 backtests 表。
- 部署 CRUD + 启停（start_deployment 起 daemon --deployment）。
"""
from __future__ import annotations
import re
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.strategy.registry import StrategyRegistry
from core.strategy.node import node_from_spec, LeafNode, NodeContext
from core.data.cache import get_data, clear_cache
from core.data.symbols import bars_per_year
from core.backtest.engine import run_node, BacktestConfig
from core.backtest.multi import run_multi
from core.backtest.gridsearch import grid_search, grid_search_multi, arange_values
from core.persist import repositories as R
from core.persist.db import init_db
from core.live import runtime as Rt
from core.utils.config import settings
from api import verify_token
from api.schemas import BacktestRequest, DeploymentCreate, DeploymentUpdate
from api.routes_monitor import _clean
from api.response_sampling import sample_curve, sample_holdings, summarize_equity, summarize_trades

router = APIRouter(prefix="/api", dependencies=[Depends(verify_token)])


@router.post("/backtest")
def backtest(req: BacktestRequest):
    """统一回测：node_spec 或 (ref_kind, ref_id) → run_node → 落 backtests 表。"""
    init_db()
    StrategyRegistry.discover_all()
    if req.response_mode not in {"full", "compact"}:
        raise HTTPException(400, "response_mode 仅支持 full 或 compact")
    try:
        node = _build_node(req)
        symbols = req.symbols or [req.symbol]
        data = {sym: get_data(sym, req.bar, req.days) for sym in symbols}
        ctx = NodeContext(data=data, primary_symbol=symbols[0], bar=req.bar)
        cfg = BacktestConfig(initial_capital=req.initial_capital, leverage=req.leverage,
                             position_ratio=req.position_ratio, fee_rate=req.fee_rate,
                             slippage=req.slippage, bars_per_year=bars_per_year(req.bar))
        outcome = run_node(node, ctx, cfg,
                           symbol=symbols[0] if len(symbols) == 1 else "", bar=req.bar)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

    eq = outcome.equity_curve
    bid = R.save_backtest(node_kind=req.ref_kind or "adhoc", ref_id=req.ref_id,
                          spec=node.to_spec(), metrics=_clean(outcome.metrics),
                          cfg=asdict(cfg), symbol=",".join(symbols), bar=req.bar,
                          days=req.days, equity_df=eq,
                          benchmark_df=outcome.benchmark_curve)
    resp = {"backtest_id": bid, "report_kind": outcome.report_kind,
            "metrics": _clean(outcome.metrics), "n_trades": len(outcome.trades),
            "equity_start": float(eq["equity"].iloc[0]),
            "equity_end": float(eq["equity"].iloc[-1]),
            "key_points": summarize_equity(eq),
            "trade_summary": summarize_trades(
                outcome.trades, bars_per_year=cfg.bars_per_year,
                initial_capital=cfg.initial_capital,
            ),
            "response_mode": req.response_mode}
    if req.response_mode == "full":
        resp["equity"] = sample_curve(eq, "equity", req.max_points)
        # 基准（同 symbol buy & hold）权益曲线：供前端绘制叠加图区分 alpha / beta。
        # 仅当后端计算出基准时返回（单 symbol / 多币 / 资金层组合都会产出）。
        if not outcome.benchmark_curve.empty:
            resp["benchmark"] = sample_curve(outcome.benchmark_curve, "equity", req.max_points)
    return resp


def _build_node(req: BacktestRequest):
    if req.ref_id and req.ref_kind:
        if req.ref_kind == "strategy":
            s = R.get_strategy(req.ref_id)
            if not s:
                raise KeyError(f"未知策略实例: {req.ref_id}")
            return LeafNode(name=s["name"], template_name=s["template_name"],
                            strategy_kind=s["strategy_kind"], params=s["params"])
        if req.ref_kind == "group":
            g = R.get_group(req.ref_id)
            if not g:
                raise KeyError(f"未知策略组: {req.ref_id}")
            return node_from_spec(g["spec"])
        raise ValueError(f"未知 ref_kind: {req.ref_kind}")
    if req.node_spec:
        return node_from_spec(req.node_spec)
    raise HTTPException(400, "需提供 node_spec 或 (ref_kind, ref_id)")


# ---------- 部署 ----------

_BAR_INTERVAL = {"1H": 3600, "4H": 14400, "1D": 86400}

@router.post("/deployments")
def create_deployment(req: DeploymentCreate):
    init_db()
    if R.find_deployment_by_name(req.name):
        raise HTTPException(409, f"部署名已存在: {req.name}")
    groups = [g.model_dump() for g in req.groups]
    did = R.create_deployment(name=req.name, is_demo=req.is_demo, bar=req.bar,
                              symbols=req.symbols, groups=groups,
                              check_interval_sec=_BAR_INTERVAL.get(req.bar, 3600),
                              leverage=req.leverage,
                              position_ratio=req.position_ratio, initial_capital=req.initial_capital)
    return R.get_deployment(did)


@router.put("/deployments/{did}")
def update_deployment(did: str, req: DeploymentUpdate):
    init_db()
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if "groups" in fields:
        fields["groups"] = [g.model_dump() for g in fields["groups"]]
    if "bar" in fields:
        fields["check_interval_sec"] = _BAR_INTERVAL.get(fields["bar"], 3600)
    if not R.update_deployment(did, **fields):
        raise HTTPException(404, f"未知部署: {did}")
    return R.get_deployment(did)


@router.post("/deployments/{did}/start")
def start_deployment_route(did: str):
    init_db()
    if not R.get_deployment(did):
        raise HTTPException(404, f"未知部署: {did}")
    jid = Rt.start_deployment(did)
    return {"deployment_id": did, "job_id": jid, "status": "running"}


@router.post("/deployments/{did}/stop")
def stop_deployment_route(did: str):
    return {"deployment_id": did, "stopped": Rt.stop_deployment(did)}


@router.delete("/deployments/{did}")
def delete_deployment_route(did: str):
    Rt.stop_deployment(did)
    Rt.delete_job(did)   # 清理 runtime/jobs state logs 文件，避免僵尸残留
    return {"deployment_id": did, "deleted": R.delete_deployment(did)}


# ---------- 策略实验室：用户 .py 文件 CRUD ----------

class UserStrategySave(BaseModel):
    name: str
    code: str


@router.post("/user_strategies")
def save_user_strategy(req: UserStrategySave):
    """保存用户策略 .py 到 strategies/ 并重载注册表。

    name 必须是合法 Python 标识符；返回保存后该策略是否成功注册。
    """
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", req.name):
        raise HTTPException(400, "策略名必须是合法 Python 标识符")
    path = settings.STRATEGIES_DIR / f"{req.name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(req.code, encoding="utf-8")
    StrategyRegistry.discover_dir(settings.STRATEGIES_DIR, force_reload=True)
    registered = req.name in StrategyRegistry.names()
    return {"ok": True, "name": req.name, "registered": registered,
            "names": StrategyRegistry.names()}


@router.delete("/user_strategies/{name}")
def delete_user_strategy(name: str):
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise HTTPException(400, "策略名必须是合法 Python 标识符")
    path = settings.STRATEGIES_DIR / f"{name}.py"
    if not path.exists():
        raise HTTPException(404, f"文件不存在: {name}.py")
    path.unlink()
    StrategyRegistry.discover_dir(settings.STRATEGIES_DIR, force_reload=True)
    return {"ok": True, "deleted": name, "names": StrategyRegistry.names()}


# ---------- 参数网格搜索 ----------

class GridSearchRequest(BaseModel):
    template_name: str
    param_ranges: dict            # {参数名: [lo, hi, step]}
    symbol: str = "BTC-USDT-SWAP"
    symbols: Optional[list[str]] = None
    bar: str = "1H"
    days: int = 180
    days_list: Optional[list[int]] = None
    metric: str = "total_return"  # total_return | sharpe | calmar | sortino
    n_jobs: int = 1
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1
    fee_rate: float = 0.0005
    slippage: float = 0.0005
    strategy_kind: Optional[str] = None
    node_spec: Optional[dict] = None
    allocation: Optional[dict[str, float]] = None
    invert: bool = False


@router.post("/grid_search")
def grid_search_route(req: GridSearchRequest):
    """穷举参数组合回测，返回按 metric 降序的结果列表。"""
    StrategyRegistry.discover_all()
    try:
        cls = StrategyRegistry.get(req.template_name)
    except KeyError as e:
        raise HTTPException(404, str(e))
    # 把 {参数名: [lo,hi,step]} 展成取值列表
    param_grid = {}
    for pname, rng in req.param_ranges.items():
        if not isinstance(rng, list) or len(rng) != 3:
            raise HTTPException(400, f"参数 {pname} 的取值需为 [lo, hi, step]")
        param_grid[pname] = arange_values(float(rng[0]), float(rng[1]), float(rng[2]))
    if not param_grid:
        raise HTTPException(400, "未提供任何参数范围")
    cfg = BacktestConfig(
        initial_capital=req.initial_capital, leverage=req.leverage,
        position_ratio=req.position_ratio, fee_rate=req.fee_rate,
        slippage=req.slippage, bars_per_year=bars_per_year(req.bar),
    )
    is_multi = (
        (req.strategy_kind or "").lower() == "multi"
        or bool(req.symbols)
        or (req.node_spec is not None)
    )
    if is_multi:
        symbols = req.symbols or ([req.symbol] if req.symbol else [])
        if not symbols:
            raise HTTPException(400, "multi grid_search 需提供 symbols")
        node_spec = req.node_spec or {
            "node_type": "leaf",
            "name": req.template_name,
            "template_name": req.template_name,
            "strategy_kind": "multi",
            "params": {},
        }
        days_list = req.days_list or [req.days]
        try:
            results = grid_search_multi(
                node_spec=node_spec,
                symbols=symbols,
                bar=req.bar,
                days_list=days_list,
                cfg=cfg,
                param_grid=param_grid,
                metric=req.metric,
                allocation=req.allocation,
                invert=req.invert,
                n_jobs=req.n_jobs,
            )
        except KeyError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(400, str(e))
    else:
        try:
            df = get_data(req.symbol, req.bar, req.days)
        except Exception as e:
            raise HTTPException(400, f"数据加载失败: {e}")
        results = grid_search(cls, df, cfg, param_grid, metric=req.metric, n_jobs=req.n_jobs)
    return {"results": _clean_rows(results), "keys": list(param_grid.keys()),
            "metric": req.metric, "count": len(results)}


def _clean_rows(rows: list[dict]) -> list[dict]:
    """保证 JSON 可序列化：inf/NaN → null。"""
    import math
    out = []
    for r in rows:
        out.append({k: (None if isinstance(v, float) and (math.isinf(v) or math.isnan(v)) else v)
                    for k, v in r.items()})
    return out


# ---------- 多币回测（含 per_symbol 明细 + holdings 热力图） ----------

class MultiBacktestRequest(BaseModel):
    node_spec: dict               # leaf 节点（单币批量或跨币）
    symbols: list[str]
    bar: str = "1H"
    days: int = 180
    days_list: Optional[list[int]] = None
    allocation: Optional[dict[str, float]] = None   # {symbol: weight}，默认等权
    invert: bool = False
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1
    fee_rate: float = 0.0005
    slippage: float = 0.0005
    max_points: Optional[int] = 300
    response_mode: str = "full"


@router.post("/multi_backtest")
def multi_backtest(req: MultiBacktestRequest):
    """多币回测：返回组合 metrics + 各 symbol 明细 + holdings 信号矩阵（热力图用）。"""
    StrategyRegistry.discover_all()
    if not req.symbols:
        raise HTTPException(400, "symbols 不能为空")
    if req.response_mode not in {"full", "compact"}:
        raise HTTPException(400, "response_mode 仅支持 full 或 compact")
    days_list = req.days_list or [req.days]
    try:
        windows = [
            _serialize_multi_report(
                _run_multi_for_days(req, days),
                max_points=req.max_points,
                response_mode=req.response_mode,
                days=days,
                bar=req.bar,
                symbols=req.symbols,
            )
            for days in days_list
        ]
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

    if req.days_list:
        return {
            "windows": windows,
            "response_mode": req.response_mode,
            "bar": req.bar,
            "symbols": req.symbols,
            "days_list": days_list,
        }
    return windows[0]


def _run_multi_for_days(req: MultiBacktestRequest, days: int):
    data = {sym: get_data(sym, req.bar, days) for sym in req.symbols}
    ctx = NodeContext(data=data, primary_symbol=req.symbols[0], bar=req.bar)
    node = node_from_spec(req.node_spec)
    signals = node.generate_signals(ctx)
    cfg = BacktestConfig(initial_capital=req.initial_capital, leverage=req.leverage,
                         position_ratio=req.position_ratio, fee_rate=req.fee_rate,
                         slippage=req.slippage, bars_per_year=bars_per_year(req.bar))
    return run_multi(signals, cfg, allocation=req.allocation, invert=req.invert)


def _serialize_multi_report(rep, *, max_points: int | None, response_mode: str,
                            days: int, bar: str, symbols: list[str]) -> dict:
    compact = response_mode == "compact"
    per_symbol = []
    for sym, w, r in rep.per_symbol:
        item = {"symbol": sym, "weight": w, "metrics": _clean(r.metrics)}
        if not compact:
            item["equity"] = (
                sample_curve(r.equity_curve, "equity", max_points) or {"equity": []}
            )["equity"]
        per_symbol.append(item)
    return {
        "days": days,
        "bar": bar,
        "symbols": symbols,
        "metrics": _clean(rep.metrics),
        "equity": sample_curve(rep.equity_curve, "equity", max_points),
        "per_symbol": per_symbol,
        "holdings": sample_holdings(rep.holdings, max_points),
        "key_points": summarize_equity(rep.equity_curve),
        "trade_summary": summarize_trades(
            _concat_multi_trades(rep.per_symbol),
            bars_per_year=bars_per_year(bar),
            initial_capital=rep.initial_capital,
        ),
        "initial_capital": rep.initial_capital,
        "response_mode": response_mode,
        # 组合层基准（各币 buy & hold 资金加权合成）权益曲线，供前端叠加对比。
        "benchmark": (sample_curve(rep.benchmark_curve, "equity", max_points)
                       if not rep.benchmark_curve.empty else None),
    }


def _concat_multi_trades(per_symbol: list) -> object:
    import pandas as pd
    parts = [r.trades.assign(symbol=sym) for sym, _w, r in per_symbol if not r.trades.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ---------- 设置：.env 编辑 / 缓存清理 ----------

class EnvUpdate(BaseModel):
    OKX_API_KEY: Optional[str] = None
    OKX_API_SECRET: Optional[str] = None
    OKX_API_PASSPHRASE: Optional[str] = None


@router.post("/config/env")
def update_env(req: EnvUpdate):
    """更新 .env 中的 OKX 凭证（不存在则追加）。修改后需重启生效。"""
    path = settings.ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = []
    for key, val in {"OKX_API_KEY": req.OKX_API_KEY,
                     "OKX_API_SECRET": req.OKX_API_SECRET,
                     "OKX_API_PASSPHRASE": req.OKX_API_PASSPHRASE}.items():
        if val is None:
            continue
        found = False
        for i, ln in enumerate(lines):
            if ln.startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                found = True
                break
        if not found:
            lines.append(f"{key}={val}")
        updated.append(key)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "updated": updated, "note": "需重启控制台/API 生效"}


@router.post("/cache/clear")
def clear_cache_route(symbol: Optional[str] = None, bar: Optional[str] = None,
                      include_instruments: bool = True):
    return {"cleared": clear_cache(symbol=symbol, bar=bar,
                                   include_instruments=include_instruments)}

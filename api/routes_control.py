"""控制类路由（POST/PUT/DELETE）：回测、部署管理。全部需 token。

- POST /api/backtest：统一吃 node_spec 或 ref_id，经 run_node 回测，结果落 backtests 表。
- 部署 CRUD + 启停（start_deployment 起 daemon --deployment）。
"""
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException

from core.strategy.registry import StrategyRegistry
from core.strategy.node import node_from_spec, LeafNode, NodeContext
from core.data.cache import get_data
from core.data.symbols import bars_per_year
from core.backtest.engine import run_node, BacktestConfig
from core.persist import repositories as R
from core.persist.db import init_db
from core.live import runtime as Rt
from api import verify_token
from api.schemas import BacktestRequest, DeploymentCreate, DeploymentUpdate
from api.routes_monitor import _clean

router = APIRouter(prefix="/api", dependencies=[Depends(verify_token)])


@router.post("/backtest")
def backtest(req: BacktestRequest):
    """统一回测：node_spec 或 (ref_kind, ref_id) → run_node → 落 backtests 表。"""
    init_db()
    StrategyRegistry.discover_all()
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
                          days=req.days, equity_df=eq)
    return {"backtest_id": bid, "report_kind": outcome.report_kind,
            "metrics": _clean(outcome.metrics), "n_trades": len(outcome.trades),
            "equity_start": float(eq["equity"].iloc[0]),
            "equity_end": float(eq["equity"].iloc[-1])}


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

@router.post("/deployments")
def create_deployment(req: DeploymentCreate):
    init_db()
    if R.find_deployment_by_name(req.name):
        raise HTTPException(409, f"部署名已存在: {req.name}")
    groups = [g.model_dump() for g in req.groups]
    did = R.create_deployment(name=req.name, is_demo=req.is_demo, bar=req.bar,
                              symbols=req.symbols, groups=groups,
                              check_interval_sec=req.check_interval_sec, leverage=req.leverage,
                              position_ratio=req.position_ratio, initial_capital=req.initial_capital)
    return R.get_deployment(did)


@router.put("/deployments/{did}")
def update_deployment(did: str, req: DeploymentUpdate):
    init_db()
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if "groups" in fields:
        fields["groups"] = [g.model_dump() for g in fields["groups"]]
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
    return {"deployment_id": did, "deleted": R.delete_deployment(did)}

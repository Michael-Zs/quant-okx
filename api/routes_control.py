"""控制类路由（POST/PUT/DELETE）：回测、部署管理。全部需 token。

- POST /api/backtest：统一吃 node_spec 或 ref_id，经 run_node 回测，结果落 backtests 表。
- 部署 CRUD + 启停（start_deployment 起 daemon --deployment）。
"""
from __future__ import annotations
import re
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.strategy.registry import StrategyRegistry
from core.strategy.node import node_from_spec, LeafNode, NodeContext
from core.data.cache import get_data, clear_cache
from core.data.symbols import bars_per_year
from core.backtest.engine import run_node, BacktestConfig
from core.backtest.multi import run_multi
from core.backtest.gridsearch import grid_search, arange_values
from core.persist import repositories as R
from core.persist.db import init_db
from core.live import runtime as Rt
from core.utils.config import settings
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
    bar: str = "1H"
    days: int = 180
    metric: str = "total_return"  # total_return | sharpe | calmar | sortino
    n_jobs: int = 1
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1


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
    try:
        df = get_data(req.symbol, req.bar, req.days)
    except Exception as e:
        raise HTTPException(400, f"数据加载失败: {e}")
    cfg = BacktestConfig(initial_capital=req.initial_capital, leverage=req.leverage,
                         position_ratio=req.position_ratio, bars_per_year=bars_per_year(req.bar))
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
    allocation: dict[str, float] | None = None   # {symbol: weight}，默认等权
    invert: bool = False
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1
    fee_rate: float = 0.0005
    slippage: float = 0.0005


@router.post("/multi_backtest")
def multi_backtest(req: MultiBacktestRequest):
    """多币回测：返回组合 metrics + 各 symbol 明细 + holdings 信号矩阵（热力图用）。"""
    StrategyRegistry.discover_all()
    if not req.symbols:
        raise HTTPException(400, "symbols 不能为空")
    try:
        data = {sym: get_data(sym, req.bar, req.days) for sym in req.symbols}
        ctx = NodeContext(data=data, primary_symbol=req.symbols[0], bar=req.bar)
        node = node_from_spec(req.node_spec)
        signals = node.generate_signals(ctx)
        cfg = BacktestConfig(initial_capital=req.initial_capital, leverage=req.leverage,
                             position_ratio=req.position_ratio, fee_rate=req.fee_rate,
                             slippage=req.slippage, bars_per_year=bars_per_year(req.bar))
        rep = run_multi(signals, cfg, allocation=req.allocation, invert=req.invert)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

    ts = [str(t) for t in rep.equity_curve["ts"].tolist()]
    per_symbol = []
    for sym, w, r in rep.per_symbol:
        per_symbol.append({
            "symbol": sym, "weight": w, "metrics": _clean(r.metrics),
            "equity": [float(x) for x in r.equity_curve["equity"].tolist()],
        })
    hold = rep.holdings
    holding_symbols = [c for c in hold.columns if c != "ts"]
    return {
        "metrics": _clean(rep.metrics),
        "equity": ts and {"ts": ts, "equity": [float(x) for x in rep.equity_curve["equity"].tolist()]},
        "per_symbol": per_symbol,
        "holdings": {
            "ts": [str(t) for t in hold["ts"].tolist()],
            "symbols": holding_symbols,
            "matrix": [[int(v) for v in hold[s].tolist()] for s in holding_symbols],
        },
        "initial_capital": rep.initial_capital,
    }


# ---------- 设置：.env 编辑 / 缓存清理 ----------

class EnvUpdate(BaseModel):
    OKX_API_KEY: str | None = None
    OKX_API_SECRET: str | None = None
    OKX_API_PASSPHRASE: str | None = None


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
def clear_cache_route():
    return {"cleared": clear_cache()}

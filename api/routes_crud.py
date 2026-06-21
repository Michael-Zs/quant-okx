"""CRUD 路由：策略实例（单策略）/ 策略组。

GET 公开（只读），POST/PUT/DELETE 需 token。
- /api/strategies：用户保存的参数化单策略实例（模板 + 参数）。
- /api/groups：用户保存的策略组（整棵 node 树）。
模板列表见 /api/templates。
"""
from fastapi import APIRouter, Depends, HTTPException

from core.persist import repositories as R
from core.persist.db import init_db
from core.strategy.node import node_from_spec
from api import verify_token
from api.schemas import StrategyCreate, StrategyUpdate, GroupCreate, GroupUpdate

router = APIRouter(prefix="/api")


# ---------- 策略实例 ----------

@router.get("/strategies")
def list_strategies():
    init_db()
    return {"strategies": R.list_strategies()}


@router.post("/strategies", dependencies=[Depends(verify_token)])
def create_strategy(req: StrategyCreate):
    init_db()
    if R.find_strategy_by_name(req.name):
        raise HTTPException(409, f"策略名已存在: {req.name}")
    sid = R.create_strategy(name=req.name, template_name=req.template_name,
                            strategy_kind=req.strategy_kind, params=req.params,
                            side_mode=req.side_mode, description=req.description,
                            bar=req.bar, days=req.days, symbols=req.symbols, invert=req.invert)
    return R.get_strategy(sid)


@router.get("/strategies/{sid}")
def get_strategy(sid: str):
    init_db()
    s = R.get_strategy(sid)
    if not s:
        raise HTTPException(404, f"未知策略: {sid}")
    return s


@router.put("/strategies/{sid}", dependencies=[Depends(verify_token)])
def update_strategy(sid: str, req: StrategyUpdate):
    init_db()
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if not R.update_strategy(sid, **fields):
        raise HTTPException(404, f"未知策略: {sid}")
    return R.get_strategy(sid)


@router.delete("/strategies/{sid}", dependencies=[Depends(verify_token)])
def delete_strategy(sid: str):
    if not R.delete_strategy(sid):
        raise HTTPException(404, f"未知策略: {sid}")
    return {"id": sid, "deleted": True}


# ---------- 策略组 ----------

@router.post("/groups/validate", dependencies=[Depends(verify_token)])
def validate_group(spec: dict):
    """校验 node 树 spec 能否被 node_from_spec 解析重建（前端组合预检用）。"""
    init_db()
    try:
        node = node_from_spec(spec)
        return {"valid": True, "node_type": node.node_type, "universe": node.universe()}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.get("/groups")
def list_groups():
    init_db()
    return {"groups": R.list_groups()}


@router.post("/groups", dependencies=[Depends(verify_token)])
def create_group(req: GroupCreate):
    init_db()
    if R.find_group_by_name(req.name):
        raise HTTPException(409, f"组名已存在: {req.name}")
    gid = R.create_group(name=req.name, spec=req.spec, description=req.description)
    return R.get_group(gid)


@router.get("/groups/{gid}")
def get_group(gid: str):
    init_db()
    g = R.get_group(gid)
    if not g:
        raise HTTPException(404, f"未知组: {gid}")
    return g


@router.put("/groups/{gid}", dependencies=[Depends(verify_token)])
def update_group(gid: str, req: GroupUpdate):
    init_db()
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if not R.update_group(gid, **fields):
        raise HTTPException(404, f"未知组: {gid}")
    return R.get_group(gid)


@router.delete("/groups/{gid}", dependencies=[Depends(verify_token)])
def delete_group(gid: str):
    if not R.delete_group(gid):
        raise HTTPException(404, f"未知组: {gid}")
    return {"id": gid, "deleted": True}

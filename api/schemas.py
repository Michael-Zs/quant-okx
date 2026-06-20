"""API 请求/响应模型（pydantic）。

node_spec / spec 用 dict 接收（前端发 JSON node 树），由 core.strategy.node.node_from_spec
解析校验——避免 pydantic 递归模型的复杂度，结构正确性由节点工厂保证。
这是前后端 TS 类型的契约源。
"""
from __future__ import annotations
from pydantic import BaseModel


class StrategyCreate(BaseModel):
    name: str
    template_name: str
    strategy_kind: str = "single"
    params: dict = {}
    side_mode: str = "long_short"
    description: str = ""


class StrategyUpdate(BaseModel):
    name: str | None = None
    params: dict | None = None
    side_mode: str | None = None
    description: str | None = None


class GroupCreate(BaseModel):
    name: str
    spec: dict                  # node 树（to_spec 结果）
    description: str = ""


class GroupUpdate(BaseModel):
    name: str | None = None
    spec: dict | None = None
    description: str | None = None


class GroupRefSpec(BaseModel):
    """部署中的策略组引用：占比 weight + 部署层反向 invert。"""
    group_id: str
    weight: float = 1.0
    invert: bool = False


class DeploymentCreate(BaseModel):
    name: str
    is_demo: bool = True
    bar: str = "1H"
    symbols: list[str] = ["BTC-USDT-SWAP"]   # 单币策略批量运行的 symbol 列表
    groups: list[GroupRefSpec]
    check_interval_sec: int = 3600
    leverage: int = 5
    position_ratio: float = 0.1
    initial_capital: float = 10000.0


class DeploymentUpdate(BaseModel):
    name: str | None = None
    is_demo: bool | None = None
    bar: str | None = None
    symbols: list[str] | None = None
    groups: list[GroupRefSpec] | None = None
    check_interval_sec: int | None = None
    leverage: int | None = None
    position_ratio: float | None = None
    initial_capital: float | None = None


class BacktestRequest(BaseModel):
    """统一回测请求：node_spec（内联节点树）或 ref_id（引用已保存策略/组）。"""
    node_spec: dict | None = None
    ref_kind: str | None = None    # "strategy" | "group"
    ref_id: str | None = None
    symbol: str = "BTC-USDT-SWAP"
    symbols: list[str] | None = None
    bar: str = "1H"
    days: int = 180
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1
    fee_rate: float = 0.0005
    slippage: float = 0.0005

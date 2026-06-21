"""API 请求/响应模型（pydantic）。

node_spec / spec 用 dict 接收（前端发 JSON node 树），由 core.strategy.node.node_from_spec
解析校验——避免 pydantic 递归模型的复杂度，结构正确性由节点工厂保证。
这是前后端 TS 类型的契约源。
"""
from typing import Optional
from pydantic import BaseModel


class StrategyCreate(BaseModel):
    name: str
    template_name: str
    strategy_kind: str = "single"
    params: dict = {}
    side_mode: str = "long_short"
    description: str = ""
    bar: Optional[str] = None              # 绑定的周期（保存时记录，Compose/部署复用）
    days: Optional[int] = None            # 回测天数
    symbols: list[str] = []            # 品种（单币 1 个 / 多币 universe）
    invert: bool = False               # 信号反向


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    params: Optional[dict] = None
    side_mode: Optional[str] = None
    description: Optional[str] = None
    bar: Optional[str] = None
    days: Optional[int] = None
    symbols: Optional[list[str]] = None
    invert: Optional[bool] = None


class GroupCreate(BaseModel):
    name: str
    spec: dict                  # node 树（to_spec 结果）
    description: str = ""


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    spec: Optional[dict] = None
    description: Optional[str] = None


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
    leverage: int = 5
    position_ratio: float = 0.1
    initial_capital: float = 10000.0


class DeploymentUpdate(BaseModel):
    name: Optional[str] = None
    is_demo: Optional[bool] = None
    bar: Optional[str] = None
    symbols: Optional[list[str]] = None
    groups: Optional[list[GroupRefSpec]] = None
    leverage: Optional[int] = None
    position_ratio: Optional[float] = None
    initial_capital: Optional[float] = None


class BacktestRequest(BaseModel):
    """统一回测请求：node_spec（内联节点树）或 ref_id（引用已保存策略/组）。"""
    node_spec: Optional[dict] = None
    ref_kind: Optional[str] = None    # "strategy" | "group"
    ref_id: Optional[str] = None
    symbol: str = "BTC-USDT-SWAP"
    symbols: Optional[list[str]] = None
    bar: str = "1H"
    days: int = 180
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1
    fee_rate: float = 0.0005
    slippage: float = 0.0005
    max_points: Optional[int] = None
    response_mode: str = "full"

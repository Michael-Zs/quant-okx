"""统一的策略节点抽象：把单币 / 多币 / 信号组合 / 资金组合统一为
可序列化、可嵌套的 ``StrategyNode``。

依赖方向铁律：本模块属于 strategy 层，只 import base / context / invert，
**绝不 import core.backtest / core.live**（回测与实盘是节点树的两个消费者，
不是组合器的内部依赖）。对注册表的依赖用「函数内延迟 import」打破循环
（registry 发现模板类、node 构建叶子时反向取模板）。

核心概念：
- ``Signals = dict[str, pd.DataFrame]``  统一输出。单币策略也输出单元素 dict，
  从而单/多币在组合器、回测、实盘路径上形态一致，下游永远遍历 Signals.items()，
  「单币还是多币」的 if 分流被「看 symbols 个数」取代。
- ``StrategyNode``  Protocol：``node_type`` / ``invert``（链路级反向）/
  ``generate_signals(ctx)->Signals`` / ``universe()`` / ``to_spec()``。
- ``ChildRef``：``{node, weight, invert}``——占比与反向是组合器中「子引用」的属性，
  可表达「同一子策略在 A 组正向、被嵌套进 B 组时反向」。
- 两类组合器：``SignalCombiner``（信号层合成，源自 Ensemble）/
  ``AllocationGroup``（资金层独立持仓，源自 Portfolio）。两者只产信号/目标，
  回测与实盘是它们的消费者。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Any
import pandas as pd

from core.strategy.invert import Signals, invert_signals


# ---------------------------------------------------------------------------
# 执行上下文
# ---------------------------------------------------------------------------

@dataclass
class NodeContext:
    """节点执行上下文。

    data: {symbol: OHLCV df}（回测侧已对齐；实盘侧由 daemon 预取）。
    primary_symbol: 单币叶节点的默认 symbol（部署配置指定）。
    """
    data: dict[str, pd.DataFrame]
    bar: str = "1H"
    primary_symbol: str | None = None
    _cache: dict = field(default_factory=dict)

    @property
    def symbols(self) -> list[str]:
        return list(self.data.keys())

    def as_multi_context(self):
        """转为多币 Context（复用 context.py 的 @feature 特征注册表与缓存）。"""
        from core.strategy.context import Context
        return Context(data=self.data, bar=self.bar, _cache=self._cache)


# ---------------------------------------------------------------------------
# Protocol 与子引用
# ---------------------------------------------------------------------------

@runtime_checkable
class StrategyNode(Protocol):
    """统一节点契约：可被回测/实盘消费、可序列化、可嵌套组合。"""
    node_type: str          # "leaf" | "signal_combiner" | "allocation_group"
    name: str
    invert: bool            # 本节点输出是否反向（链路级）

    def generate_signals(self, ctx: NodeContext) -> Signals: ...
    def universe(self) -> list[str]: ...
    def to_spec(self) -> dict: ...


@dataclass
class ChildRef:
    """子节点引用：承载该子在父中的占比 weight 与反向 invert。

    invert 是链路级：同一子策略可在 A 组内正向、被嵌套进 B 组时反向。
    组合器在聚合子信号时先应用子的 invert、再应用自身的 invert，等价逐层 XOR。
    """
    node: StrategyNode
    weight: float = 1.0
    invert: bool = False

    def to_spec(self) -> dict:
        return {"node": self.node.to_spec(), "weight": self.weight, "invert": self.invert}


# ---------------------------------------------------------------------------
# 叶节点：包装单个策略实例（单币或多币）
# ---------------------------------------------------------------------------

@dataclass
class LeafNode:
    node_type: str = "leaf"
    name: str = ""
    template_name: str = ""           # registry 中的模板类名
    strategy_kind: str = "single"     # "single" | "multi"
    params: dict = field(default_factory=dict)
    invert: bool = False

    def universe(self) -> list[str]:
        """多币叶节点声明其涉及的 symbol；单币叶节点返回 []（symbol 由部署上下文决定）。"""
        if self.strategy_kind == "multi":
            from core.strategy.registry import StrategyRegistry
            cls = StrategyRegistry.get(self.template_name)
            return list(getattr(cls, "universe", []) or [])
        return []

    def generate_signals(self, ctx: NodeContext) -> Signals:
        from core.strategy.registry import StrategyRegistry
        strat = StrategyRegistry.get(self.template_name)(**self.params)
        if self.strategy_kind == "multi":
            raw: Signals = strat.generate_signals(ctx.as_multi_context())
        else:
            # 单币策略对 ctx 内所有 symbol 批量独立运行（支持部署多 symbol）
            raw = {sym: strat.generate_signals(ctx.data[sym]) for sym in ctx.symbols}
        return invert_signals(raw, self.invert)

    def to_spec(self) -> dict:
        return {
            "node_type": "leaf", "name": self.name, "template_name": self.template_name,
            "strategy_kind": self.strategy_kind, "params": self.params, "invert": self.invert,
        }


# ---------------------------------------------------------------------------
# 信号层组合器：多子节点 signal 按模式合成（源自 Ensemble）
# ---------------------------------------------------------------------------

def _combine(sig: pd.DataFrame, mode: str, weights: dict[str, float]) -> pd.Series:
    """对 time×sub 的 signal 矩阵按 mode 合成单列最终 signal。算法搬自 ensemble.py。"""
    n = sig.shape[1]
    if mode == "and":
        return sig.eq(1).all(axis=1).astype(int) - sig.eq(-1).all(axis=1).astype(int)
    if mode == "or":
        return sig.eq(1).any(axis=1).astype(int) - sig.eq(-1).any(axis=1).astype(int)
    if mode == "majority":
        pos = (sig == 1).sum(axis=1)
        neg = (sig == -1).sum(axis=1)
        out = pd.Series(0, index=sig.index)
        out[pos > n / 2] = 1
        out[neg > n / 2] = -1
        return out
    if mode == "weighted":
        ws = pd.Series(weights)
        ws = ws / (ws.sum() or 1.0)
        net = sig.mul(ws.values, axis=1).sum(axis=1)
        out = pd.Series(0, index=sig.index)
        out[net > 0] = 1
        out[net < 0] = -1
        return out
    # vote：净票数符号
    net = sig.sum(axis=1)
    out = pd.Series(0, index=sig.index)
    out[net > 0] = 1
    out[net < 0] = -1
    return out


@dataclass
class SignalCombiner:
    node_type: str = "signal_combiner"
    name: str = ""
    mode: str = "vote"                       # vote|majority|and|or|weighted
    children: list[ChildRef] = field(default_factory=list)
    invert: bool = False
    MODES = ("vote", "majority", "and", "or", "weighted")

    def universe(self) -> list[str]:
        return _union_universe(self.children)

    def generate_signals(self, ctx: NodeContext) -> Signals:
        subs = [(c, c.node.generate_signals(ctx)) for c in self.children]
        out: Signals = {}
        for sym in _collect_symbols(subs):
            ref = _first_df(subs, sym)
            sig_mat = pd.DataFrame(index=ref.index)
            weights: dict[str, float] = {}
            for i, (c, sig) in enumerate(subs):
                col = f"sub{i}"
                s = sig.get(sym)
                col_vals = s["signal"].fillna(0).astype(int) if s is not None else 0
                if c.invert:
                    col_vals = -col_vals
                sig_mat[col] = col_vals
                weights[col] = c.weight
            final = _combine(sig_mat, self.mode, weights)
            d = ref.copy()
            d["signal"] = final.astype(int).values
            d["trade"] = d["signal"].diff().fillna(0).astype(int)
            out[sym] = d
        return invert_signals(out, self.invert)

    def to_spec(self) -> dict:
        return {
            "node_type": "signal_combiner", "name": self.name, "mode": self.mode,
            "children": [c.to_spec() for c in self.children], "invert": self.invert,
        }


# ---------------------------------------------------------------------------
# 资金层组合器：各子独立持仓、按 weight 切分资金（源自 Portfolio）
# ---------------------------------------------------------------------------

@dataclass
class AllocationGroup:
    """资金层组合器。

    资金层组合本质上「没有单一合成信号」：每个子独立持仓、按 weight 切分资金，
    各自盈亏相加。因此本类把「收集各子信号 + weight/invert」暴露给消费者
    （回测器 / 实盘执行器），由消费者分别处理。

    ``generate_signals`` 仅提供一个「加权净方向投影」用于轻量预览；
    **正式的资金层回测/实盘必须走 ``collect()`` 分支**，否则会按单一合成信号
    跑全仓而失真。run_group / run_deployment_round 走的就是 collect。
    """
    node_type: str = "allocation_group"
    name: str = ""
    children: list[ChildRef] = field(default_factory=list)
    invert: bool = False

    def universe(self) -> list[str]:
        return _union_universe(self.children)

    def collect(self, ctx: NodeContext) -> list[tuple[ChildRef, Signals]]:
        """各子独立产出信号，附带其在组内的 weight/invert。

        回测器据此对每个子按 weight 切分资金、独立回测后权益相加；
        实盘执行器据此对各子按 weight 缩放目标 notional、分别对齐持仓。
        """
        return [(c, c.node.generate_signals(ctx)) for c in self.children]

    def generate_signals(self, ctx: NodeContext) -> Signals:
        """加权净方向投影——仅供轻量预览，勿用于正式资金层回测（会失真）。"""
        items = self.collect(ctx)
        total_w = sum(c.weight for c, _ in items) or 1.0
        out: Signals = {}
        for sym in _collect_symbols(items):
            ref = _first_df(items, sym)
            net = pd.Series(0.0, index=ref.index)
            for c, sig in items:
                s = sig.get(sym)
                if s is None:
                    continue
                contribution = s["signal"].fillna(0).astype(float) * (c.weight / total_w)
                if c.invert:
                    contribution = -contribution
                net += contribution.values
            final = pd.Series(0, index=ref.index)
            final[net > 0] = 1
            final[net < 0] = -1
            if self.invert:
                final = -final
            d = ref.copy()
            d["signal"] = final.astype(int).values
            d["trade"] = d["signal"].diff().fillna(0).astype(int)
            out[sym] = d
        return out

    def to_spec(self) -> dict:
        return {
            "node_type": "allocation_group", "name": self.name,
            "children": [c.to_spec() for c in self.children], "invert": self.invert,
        }


# ---------------------------------------------------------------------------
# 序列化工厂：spec dict <-> 节点树（纯 JSON，存 SQLite / 前后端传输）
# ---------------------------------------------------------------------------

def node_from_spec(spec: dict) -> StrategyNode:
    """从 JSON-serializable spec 递归重建节点树。与各节点的 to_spec 互逆。"""
    t = spec.get("node_type")
    if t == "leaf":
        return LeafNode(
            name=spec.get("name", ""), template_name=spec["template_name"],
            strategy_kind=spec.get("strategy_kind", "single"),
            params=spec.get("params", {}), invert=spec.get("invert", False),
        )
    if t == "signal_combiner":
        return SignalCombiner(
            name=spec.get("name", ""), mode=spec.get("mode", "vote"),
            children=_children_from_spec(spec), invert=spec.get("invert", False),
        )
    if t == "allocation_group":
        return AllocationGroup(
            name=spec.get("name", ""), children=_children_from_spec(spec),
            invert=spec.get("invert", False),
        )
    raise ValueError(f"未知节点类型: {t!r}")


def _children_from_spec(spec: dict) -> list[ChildRef]:
    return [
        ChildRef(node=node_from_spec(c["node"]),
                 weight=c.get("weight", 1.0), invert=c.get("invert", False))
        for c in spec.get("children", [])
    ]


# ---------------------------------------------------------------------------
# 小工具：跨子节点聚合 symbol / 取参考 df
# ---------------------------------------------------------------------------

def _union_universe(children: list[ChildRef]) -> list[str]:
    seen: list[str] = []
    for c in children:
        for s in c.node.universe():
            if s not in seen:
                seen.append(s)
    return seen


def _collect_symbols(subs: list[tuple[ChildRef, Signals]]) -> list[str]:
    """从「(子引用, 该子 Signals)」列表收集 symbol 并集，保持首次出现顺序。"""
    seen: list[str] = []
    for _, sig in subs:
        for s in sig:
            if s not in seen:
                seen.append(s)
    return seen


def _first_df(subs: list[tuple[Any, Signals]], symbol: str) -> pd.DataFrame:
    """从子信号列表中取首个含该 symbol 的 df 作为 OHLCV 参考列。"""
    for _, sig in subs:
        if symbol in sig:
            return sig[symbol]
    raise KeyError(f"无子节点产出 symbol {symbol!r}")

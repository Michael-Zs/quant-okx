"""策略组部署执行：多组占比聚合 → 目标持仓 → 写 intent。

daemon 每轮调 ``run_deployment_round``。聚合逻辑：
- 部署 = 资金层组合（多组按 group_weight 切资金，各组独立持仓）。
- 每个 symbol 的目标无量纲净信号 =
      Σ(group_weight × child_weight × 有效信号方向)。
- 有效信号方向经链路级 invert XOR：
      子节点自身 invert（已在 signals 内）× 组内 child invert × 组 invert × 部署 group invert。
- 返回 intent dict（含 signals/capital_weight/position_ratio/leverage/is_demo/bar/ts），
  由 executor 聚合后对账下单。
"""
from __future__ import annotations
import time

from core.data.fetcher import fetch_recent
from core.persist import repositories as R
from core.strategy.node import node_from_spec, NodeContext, AllocationGroup
from core.strategy.registry import StrategyRegistry


def _effective_signal(sig: float, *invert_flags: bool) -> float:
    """链路级 invert XOR：奇数个 True 则反向。"""
    return -sig if sum(1 for f in invert_flags if f) % 2 == 1 else sig


def collect_universe(deployment: dict) -> list[str]:
    """部署涉及的所有 symbol：单币用 deployment.symbols，多币用各 group node.universe()。"""
    symbols = list(deployment.get("symbols", []))
    for gref in deployment.get("groups", []):
        grp = R.get_group(gref.get("group_id"))
        if not grp:
            continue
        node = node_from_spec(grp["spec"])
        for s in node.universe():
            if s not in symbols:
                symbols.append(s)
    return symbols


def compute_net_signals(deployment: dict, ctx: NodeContext) -> dict[str, float]:
    """计算每个 symbol 的无量纲净信号（值域 [-1,1]）。返回 {okx_symbol: net_signal}。

    部署 = 资金层组合。AllocationGroup 的各子按 child_weight 切组资金；leaf/signal_combiner
    整组按 group_weight 切部署资金。invert 按链路 XOR 累乘。

    **注意**: 本函数不再计算 per_unit_notional，由 executor 按 equity×cw×pr×lev 统一计算。
    """
    groups = deployment.get("groups", [])
    total_gw = sum(g.get("weight", 1.0) for g in groups) or 1.0
    signals: dict[str, float] = {}

    for gref in groups:
        gw = gref.get("weight", 1.0) / total_gw
        g_invert = bool(gref.get("invert", False))
        grp = R.get_group(gref.get("group_id"))
        if not grp:
            continue
        node = node_from_spec(grp["spec"])
        if isinstance(node, AllocationGroup):
            total_cw = sum(c.weight for c in node.children) or 1.0
            for cref, sigs in node.collect(ctx):
                cw = cref.weight / total_cw
                for sym, df in sigs.items():
                    sig = float(df["signal"].fillna(0).iloc[-1])
                    eff = _effective_signal(sig, cref.invert, node.invert, g_invert)
                    # 累加贡献（无量纲，值域 [-1,1]）
                    signals[sym] = signals.get(sym, 0.0) + gw * cw * eff
        else:
            for sym, df in node.generate_signals(ctx).items():
                sig = float(df["signal"].fillna(0).iloc[-1])
                eff = _effective_signal(sig, g_invert)
                signals[sym] = signals.get(sym, 0.0) + gw * eff
    return signals


def run_deployment_round(deployment_id: str) -> dict:
    """单轮部署执行：聚合净信号 → 构造 intent dict。

    不再进行对账下单（由 executor 统一处理）。
    返回 intent dict（含 signals/capital_weight/position_ratio/leverage/is_demo/bar/ts），
    供 daemon 写入 intent 文件。

    Args:
        deployment_id: 部署 ID

    Returns:
        intent dict: {deployment_id, signals, capital_weight, position_ratio, leverage,
                     is_demo, bar, ts, prices}
    """
    deployment = R.get_deployment(deployment_id)
    if not deployment:
        raise ValueError(f"未知 deployment: {deployment_id}")

    # 确保 daemon 进程的策略注册表已加载
    StrategyRegistry.discover_all()

    symbols = collect_universe(deployment)
    if not symbols:
        return {"deployment_id": deployment_id, "error": "部署未涉及任何 symbol"}

    data = {sym: fetch_recent(sym, deployment["bar"], limit=300) for sym in symbols}
    ctx = NodeContext(data=data, bar=deployment["bar"])

    net_signals = compute_net_signals(deployment, ctx)   # {okx_symbol: net_signal}

    # 取最新价格（可选，供 executor 参考但不依赖）
    prices = {sym: float(data[sym]["close"].iloc[-1]) for sym in net_signals}

    return {
        "deployment_id": deployment_id,
        "signals": net_signals,
        "capital_weight": deployment.get("capital_weight", 1.0),
        "position_ratio": deployment["position_ratio"],
        "leverage": deployment["leverage"],
        "is_demo": deployment["is_demo"],
        "bar": deployment["bar"],
        "ts": time.time(),
        "prices": prices,  # 可选，供 executor 参考
    }



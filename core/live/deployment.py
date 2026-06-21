"""策略组部署执行：多组占比聚合 → 目标持仓 → 增量对齐下单。

daemon 每轮调 ``run_deployment_round``。聚合逻辑：
- 部署 = 资金层组合（多组按 group_weight 切资金，各组独立持仓）。
- 每个 symbol 的目标名义价值 =
      Σ(group_weight × child_weight × 有效信号方向) × per_unit_notional。
- 有效信号方向经链路级 invert XOR：
      子节点自身 invert（已在 signals 内）× 组内 child invert × 组 invert × 部署 group invert。
- 增量下单：目标 notional 与当前持仓 notional 的差额（避免每轮全平全开，省手续费），
  单 symbol 下单失败不中断其他 symbol。
"""
from __future__ import annotations

from core.data.fetcher import fetch_recent
from core.data.symbols import okx_to_ccxt
from core.live.exchange import get_positions, get_balance, get_equity, set_leverage, market_order
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


def compute_targets(deployment: dict, ctx: NodeContext, per_unit_notional: float) -> dict[str, float]:
    """计算每个 symbol 的目标名义价值（带符号）。返回 {okx_symbol: target_notional}。

    部署 = 资金层组合。AllocationGroup 的各子按 child_weight 切组资金；leaf/signal_combiner
    整组按 group_weight 切部署资金。invert 按链路 XOR 累乘。
    """
    groups = deployment.get("groups", [])
    total_gw = sum(g.get("weight", 1.0) for g in groups) or 1.0
    target: dict[str, float] = {}

    for gref in groups:
        gw = gref.get("weight", 1.0) / total_gw
        g_invert = bool(gref.get("invert", False))
        grp = R.get_group(gref.get("group_id"))
        if not grp:
            continue
        node = node_from_spec(grp["spec"])
        if isinstance(node, AllocationGroup):
            total_cw = sum(c.weight for c in node.children) or 1.0
            for cref, signals in node.collect(ctx):
                cw = cref.weight / total_cw
                for sym, df in signals.items():
                    sig = float(df["signal"].fillna(0).iloc[-1])
                    eff = _effective_signal(sig, cref.invert, node.invert, g_invert)
                    target[sym] = target.get(sym, 0.0) + gw * cw * eff * per_unit_notional
        else:
            for sym, df in node.generate_signals(ctx).items():
                sig = float(df["signal"].fillna(0).iloc[-1])
                eff = _effective_signal(sig, g_invert)
                target[sym] = target.get(sym, 0.0) + gw * eff * per_unit_notional
    return target


def run_deployment_round(ex, deployment_id: str) -> dict:
    """单轮部署执行：聚合目标持仓 → 对齐实际持仓 → 增量下单。

    返回 state dict（含每个 symbol 的目标/当前 notional、持仓、动作）。
    """
    deployment = R.get_deployment(deployment_id)
    if not deployment:
        raise ValueError(f"未知 deployment: {deployment_id}")

    # 确保 daemon 进程的策略注册表已加载（LeafNode 据此实例化模板；
    # daemon 是独立进程，不会继承 api_server 进程的注册表状态）
    StrategyRegistry.discover_all()

    symbols = collect_universe(deployment)
    if not symbols:
        return {"deployment_id": deployment_id, "error": "部署未涉及任何 symbol", "actions": []}

    data = {sym: fetch_recent(sym, deployment["bar"], limit=300) for sym in symbols}
    ctx = NodeContext(data=data, bar=deployment["bar"])

    balance = get_balance(ex)
    equity = get_equity(ex)
    per_unit = balance * float(deployment["position_ratio"]) * float(deployment["leverage"])
    targets = compute_targets(deployment, ctx, per_unit)   # {okx_symbol: target_notional}

    ccxt_map = {sym: okx_to_ccxt(sym) for sym in targets}
    current = get_positions(ex, list(ccxt_map.values()))
    actions: list[str] = []
    positions_state: dict = {}

    for sym, target_n in targets.items():
        ccxt_sym = ccxt_map[sym]
        price = float(data[sym]["close"].iloc[-1])
        cur = current.get(ccxt_sym, {})
        cur_contracts = float(cur.get("contracts", 0.0))
        cur_dir = int(cur.get("dir", 0))
        current_n = cur_dir * cur_contracts * price
        delta_n = target_n - current_n
        positions_state[sym] = {
            "target_notional": round(target_n, 2),
            "current_notional": round(current_n, 2),
            "price": price,
            "position_dir": cur_dir, "position_contracts": cur_contracts,
            "entry_price": cur.get("entry_price", 0.0),
            "unrealized_pnl": cur.get("unrealized_pnl", 0.0),
        }
        # 阈值：名义差额 < 0.5% per_unit 视为无需调整（噪声过滤）
        if abs(delta_n) < per_unit * 0.005:
            actions.append(f"{sym} hold")
            continue
        set_leverage(ex, ccxt_sym, int(deployment["leverage"]))
        amount = round(abs(delta_n) / price, 3)
        if amount <= 0:
            continue
        side = "buy" if delta_n > 0 else "sell"
        try:
            market_order(ex, ccxt_sym, side, amount)
            actions.append(f"{sym} {side} {amount} (Δ{delta_n:+.0f})")
        except Exception as e:
            actions.append(f"{sym} 下单失败: {e}")   # 单 symbol 失败不中断

    return {"deployment_id": deployment_id,
            "balance": balance, "equity": equity,
            "targets": {s: round(v, 2) for s, v in targets.items()},
            "actions": actions, "positions": positions_state}

"""Executor 对账下单循环。

从 intents 聚合目标持仓，与账户实际持仓对账，增量下单。
关键修正：对账集合 = intents 声明的 symbol ∪ 账户实际持仓，
确保停止/删除部署时能平掉残留仓位。
"""
from __future__ import annotations
from typing import Optional

from core.data.symbols import okx_to_ccxt
from core.executor.intent import load_fresh_intents, aggregate
from core.live.exchange import (
    get_equity, get_all_positions, set_leverage, market_order
)


def reconcile_and_trade(ex, intents: list[dict]) -> dict:
    """单轮对账下单。

    步骤：
    1. 获取账户 equity
    2. 聚合 intents → target持仓
    3. 获取账户全部持仓
    4. 对账集合 = target.keys() ∪ 持仓.keys()
    5. 批量取价格
    6. 逐 symbol 计算差额、噪声过滤、设杠杆、市价下单
    7. 单 symbol 失败不中断

    Args:
        ex: ccxt.Exchange 实例
        intents: 该 is_demo 组的 intent 列表

    Returns:
        state dict: equity/target/positions/actions/errors/warn
    """
    if ex is None:
        return {"error": "Exchange 构造失败（API key 不匹配或网络错误）"}

    equity = get_equity(ex)
    target, meta = aggregate(intents, equity)

    # 关键修正：对账集合 = intents 声明 ∪ 账户实际持仓
    pos_all = get_all_positions(ex)  # {okx_sym: {dir, contracts, ...}}
    syms = set(target) | set(pos_all)

    if not syms:
        return {
            "equity": round(equity, 2),
            "target": {},
            "positions": {},
            "actions": ["无交易对，跳过"],
            "errors": [],
            "warn": meta.get("warn"),
        }

    # 批量取价格
    ccxt_syms = [okx_to_ccxt(s) for s in syms]
    try:
        tickers = ex.fetch_tickers(ccxt_syms)
    except Exception as e:
        return {
            "equity": round(equity, 2),
            "target": {s: round(v, 2) for s, v in target.items()},
            "error": f"取价失败: {e}",
            "actions": [],
            "errors": [{"msg": f"批量取价失败: {e}"}],
            "warn": meta.get("warn"),
        }

    actions: list[str] = []
    errors: list[dict] = []
    positions_state: dict = {}

    for sym in syms:
        ccxt_sym = okx_to_ccxt(sym)
        ticker = tickers.get(ccxt_sym, {})
        price = float(ticker.get("last", 0) or 0)
        if price <= 0:
            errors.append({"sym": sym, "err": f"无效价格 {price}"})
            continue

        cur = pos_all.get(sym, {})
        cur_dir = int(cur.get("dir", 0))
        cur_contracts = float(cur.get("contracts", 0.0))
        current_n = cur_dir * cur_contracts * price
        target_n = target.get(sym, 0.0)

        delta = target_n - current_n

        positions_state[sym] = {
            "target": round(target_n, 2),
            "current": round(current_n, 2),
            "price": price,
            "position_dir": cur_dir,
            "position_contracts": cur_contracts,
            "entry_price": cur.get("entry_price", 0.0),
            "unrealized_pnl": cur.get("unrealized_pnl", 0.0),
        }

        # 噪声阈值：名义差额 < 0.5% max(|target|,|current|,1) 视为无需调整
        threshold = max(abs(target_n), abs(current_n), 1.0) * 0.005
        if abs(delta) < threshold:
            actions.append(f"{sym} hold (Δ{delta:+.0f})")
            continue

        # 设杠杆：取所有涉及该 symbol 的 intent 的最大杠杆
        lev = 1
        if intents:
            lev = max((int(it.get("leverage", 1)) for it in intents if sym in it.get("signals", {})), default=1)
        try:
            set_leverage(ex, ccxt_sym, lev)
        except Exception as e:
            errors.append({"sym": sym, "err": f"设杠杆失败: {e}"})

        amount = round(abs(delta) / price, 3)
        if amount <= 0:
            continue
        side = "buy" if delta > 0 else "sell"
        try:
            market_order(ex, ccxt_sym, side, amount)
            actions.append(f"{sym} {side} {amount} (Δ{delta:+.0f})")
        except Exception as e:
            errors.append({"sym": sym, "err": str(e)})
            actions.append(f"{sym} 下单失败: {e}")

    return {
        "equity": round(equity, 2),
        "target": {s: round(v, 2) for s, v in target.items()},
        "positions": positions_state,
        "actions": actions,
        "errors": errors,
        "warn": meta.get("warn"),
    }


def run_once_cycle(demo_ex, live_ex) -> dict:
    """执行一轮完整的 executor 循环。

    1. 加载所有 intents
    2. 按 is_demo 分组
    3. 各组调用 reconcile_and_trade
    4. 汇总返回结果

    Args:
        demo_ex: 模拟盘 exchange（可能为 None）
        live_ex: 实盘 exchange（可能为 None）

    Returns:
        {demo: {...}, live: {...}, ts: "..."}
    """
    intents = load_fresh_intents()
    demo_intents = [it for it in intents if it.get("is_demo") is not False]
    live_intents = [it for it in intents if it.get("is_demo") is False]

    import time
    result = {
        "demo": reconcile_and_trade(demo_ex, demo_intents) if demo_ex else {"error": "模拟盘 exchange 未配置"},
        "live": reconcile_and_trade(live_ex, live_intents) if live_ex else {"error": "实盘 exchange 未配置"},
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 补充统计
    result["deployment_count"] = {
        "demo": len(demo_intents),
        "live": len(live_intents),
    }
    return result

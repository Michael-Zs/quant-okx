"""Intent 文件读写与聚合。

Intent 是部署 daemon 写入的目标仓位意图，包含：
- signals: {symbol: net_signal}（无量纲，[-1,1]）
- capital_weight: 部署间资金份额（Σ≤1 软约束）
- position_ratio: 单部署激进度（0~1）
- leverage: 杠杆倍数
- is_demo: 是否模拟盘
- bar: K 线周期
- ts: 写入时间戳

Executor 聚合所有 intent → 按 equity×cw×pr×lev 计算每部署贡献 → 求和得目标持仓。
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional

from core.utils.config import settings


def intent_path(deployment_id: str) -> Path:
    """返回 deployment 的 intent 文件路径。"""
    return settings.INTENTS_DIR / f"{deployment_id}.json"


def write_intent(intent: dict) -> None:
    """原子写入 intent 文件。"""
    path = intent_path(intent["deployment_id"])
    from core.live.runtime import write_json_atomic
    write_json_atomic(path, intent)


def read_intent(path: Path) -> Optional[dict]:
    """读取 intent 文件，损坏返回 None。"""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_fresh_intents(max_age_sec: Optional[int] = None) -> list[dict]:
    """加载所有有效的 intent 文件。

    Args:
        max_age_sec: 最大有效期（秒），默认用 settings.INTENT_MAX_AGE_SEC（7200）
                    超过 2 个 1H 周期视为僵尸残留，跳过聚合但不删文件。

    Returns:
        有效的 intent 列表（按部署 ID 排序）。
    """
    if max_age_sec is None:
        max_age_sec = settings.INTENT_MAX_AGE_SEC
    now = time.time()
    intents = []
    for p in sorted(settings.INTENTS_DIR.glob("*.json")):
        data = read_intent(p)
        if data is None:
            continue  # 损坏文件跳过
        ts = data.get("ts", 0)
        if now - ts > max_age_sec:
            continue  # 过期跳过
        intents.append(data)
    return intents


def aggregate(intents: list[dict], equity: float) -> tuple[dict, dict]:
    """聚合所有 intent → 目标持仓与元数据。

    计算逻辑：
    - per_unit_deploy[d] = equity × capital_weight × position_ratio × leverage
    - contribution[d, sym] = signals[sym] × per_unit_deploy[d]
    - target[sym] = Σ contribution[d, sym]

    软截断：若 Σ(cw × pr) > 1，按比例缩放所有 target，并在 meta.warn 标记。

    Args:
        intents: intent 列表（每个含 signals/capital_weight/position_ratio/leverage）
        equity: 当前账户权益

    Returns:
        (target, meta) 元组
        - target: {okx_symbol: target_notional}（带符号）
        - meta: {"warn": str|None, "sum_cw_pr": float, "scale": float}
    """
    target: dict[str, float] = {}
    total_cw_pr = 0.0
    per_unit_deploy: dict[str, float] = {}

    for it in intents:
        did = it["deployment_id"]
        cw = float(it.get("capital_weight", 1.0))
        pr = float(it.get("position_ratio", 0.1))
        lev = float(it.get("leverage", 1))
        per_unit = equity * cw * pr * lev
        per_unit_deploy[did] = per_unit
        total_cw_pr += cw * pr

        signals: dict = it.get("signals", {})
        for sym, net_sig in signals.items():
            target[sym] = target.get(sym, 0.0) + net_sig * per_unit

    # 软截断
    scale = 1.0
    warn = None
    if total_cw_pr > 1.0:
        scale = 1.0 / total_cw_pr
        warn = f"Σ(capital_weight × position_ratio) = {total_cw_pr:.2f} > 1，已按 {scale:.2%} 缩放"
        for sym in list(target.keys()):
            target[sym] *= scale

    meta = {
        "sum_cw_pr": total_cw_pr,
        "scale": scale,
        "warn": warn,
        "deployment_count": len(intents),
    }
    return target, meta

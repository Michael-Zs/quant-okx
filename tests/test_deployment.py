"""部署聚合引擎测试：compute_targets 的权重缩放与链路级 invert XOR。

不触达真实交易所（compute_targets 是纯聚合），用 tmp_db 造组 + 假行情 ctx。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    from core.utils.config import settings
    from core.persist import db
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(settings, "BACKTESTS_DIR", tmp_path / "bt")
    db.init_db()
    yield


def _ctx():
    np.random.seed(7)
    n = 200
    ts = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = 100 + np.random.randn(n).cumsum()
    df = pd.DataFrame({"ts": ts, "open": close, "high": close + 1,
                       "low": close - 1, "close": close, "vol": 1000.0})
    from core.strategy import node as N
    return N.NodeContext(data={"BTC-USDT-SWAP": df}, bar="1H")


def _leaf(template, params):
    return {"node_type": "leaf", "name": template, "template_name": template,
            "strategy_kind": "single", "params": params, "invert": False}


def _alloc(children):
    return {"node_type": "allocation_group", "name": "g", "invert": False,
            "children": [{"node": c["node"], "weight": c["weight"], "invert": c["invert"]}
                         for c in children]}


def _discover():
    from core.strategy.registry import StrategyRegistry
    StrategyRegistry.discover_all()


def test_compute_targets_within_budget():
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    gid = R.create_group(name="g1", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 0.6, "invert": False},
        {"node": _leaf("rsi", {"period": 14}), "weight": 0.4, "invert": False},
    ]))
    dep = {"symbols": ["BTC-USDT-SWAP"],
           "groups": [{"group_id": gid, "weight": 1.0, "invert": False}]}
    targets = D.compute_targets(dep, _ctx(), per_unit_notional=1000.0)
    assert "BTC-USDT-SWAP" in targets
    # 单组 weight=1、子权重和=1、信号∈[-1,1] → 目标应在 [-1000, 1000]
    assert -1000.001 <= targets["BTC-USDT-SWAP"] <= 1000.001


def test_group_invert_flips_target():
    """部署层 g_invert=True 使目标取反（链路 XOR）。"""
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    gid = R.create_group(name="g2", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": False}]))
    ctx = _ctx()
    pos = D.compute_targets({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid, "weight": 1.0, "invert": False}]},
                            ctx, 1000.0)
    neg = D.compute_targets({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid, "weight": 1.0, "invert": True}]},
                            ctx, 1000.0)
    assert pos["BTC-USDT-SWAP"] == pytest.approx(-neg["BTC-USDT-SWAP"], abs=1e-6)


def test_child_invert_flips_target():
    """组内 cref.invert=True 使该子贡献取反。"""
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    gid_pos = R.create_group(name="gp", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": False}]))
    gid_neg = R.create_group(name="gn", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": True}]))
    ctx = _ctx()
    pos = D.compute_targets({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid_pos, "weight": 1.0, "invert": False}]},
                            ctx, 1000.0)
    neg = D.compute_targets({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid_neg, "weight": 1.0, "invert": False}]},
                            ctx, 1000.0)
    assert pos["BTC-USDT-SWAP"] == pytest.approx(-neg["BTC-USDT-SWAP"], abs=1e-6)


def test_group_weight_splits_capital():
    """两组同策略各 weight=0.5，聚合 = 单组 weight=1（资金等价切分）。"""
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    spec = _alloc([{"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": False}])
    g1 = R.create_group(name="gw1", spec=spec)
    g2 = R.create_group(name="gw2", spec=spec)
    ctx = _ctx()
    single = D.compute_targets({"symbols": ["BTC-USDT-SWAP"],
                                "groups": [{"group_id": g1, "weight": 1.0, "invert": False}]},
                               ctx, 1000.0)
    double = D.compute_targets({"symbols": ["BTC-USDT-SWAP"],
                                "groups": [{"group_id": g1, "weight": 0.5, "invert": False},
                                           {"group_id": g2, "weight": 0.5, "invert": False}]},
                               ctx, 1000.0)
    assert single["BTC-USDT-SWAP"] == pytest.approx(double["BTC-USDT-SWAP"], abs=1e-6)

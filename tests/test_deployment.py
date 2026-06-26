"""部署聚合引擎测试：compute_net_signals 的权重缩放与链路级 invert XOR。

不触达真实交易所（compute_net_signals 是纯聚合），用 tmp_db 造组 + 假行情 ctx。
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


def test_compute_net_signals_within_range():
    """compute_net_signals 返回无量纲净信号，值域 [-1,1]。"""
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    gid = R.create_group(name="g1", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 0.6, "invert": False},
        {"node": _leaf("rsi", {"period": 14}), "weight": 0.4, "invert": False},
    ]))
    dep = {"symbols": ["BTC-USDT-SWAP"],
           "groups": [{"group_id": gid, "weight": 1.0, "invert": False}]}
    signals = D.compute_net_signals(dep, _ctx())
    assert "BTC-USDT-SWAP" in signals
    # 单组 weight=1、子权重和=1、信号∈[-1,1] → 净信号应在 [-1, 1]
    assert -1.001 <= signals["BTC-USDT-SWAP"] <= 1.001


def test_group_invert_flips_signal():
    """部署层 g_invert=True 使净信号取反（链路 XOR）。"""
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    gid = R.create_group(name="g2", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": False}]))
    ctx = _ctx()
    pos = D.compute_net_signals({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid, "weight": 1.0, "invert": False}]},
                             ctx)
    neg = D.compute_net_signals({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid, "weight": 1.0, "invert": True}]},
                             ctx)
    assert pos["BTC-USDT-SWAP"] == pytest.approx(-neg["BTC-USDT-SWAP"], abs=1e-6)


def test_child_invert_flips_signal():
    """组内 cref.invert=True 使该子贡献取反。"""
    from core.live import deployment as D
    from core.persist import repositories as R
    _discover()
    gid_pos = R.create_group(name="gp", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": False}]))
    gid_neg = R.create_group(name="gn", spec=_alloc([
        {"node": _leaf("ma_cross", {"fast": 5, "slow": 20}), "weight": 1.0, "invert": True}]))
    ctx = _ctx()
    pos = D.compute_net_signals({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid_pos, "weight": 1.0, "invert": False}]},
                             ctx)
    neg = D.compute_net_signals({"symbols": ["BTC-USDT-SWAP"],
                             "groups": [{"group_id": gid_neg, "weight": 1.0, "invert": False}]},
                             ctx)
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
    single = D.compute_net_signals({"symbols": ["BTC-USDT-SWAP"],
                                "groups": [{"group_id": g1, "weight": 1.0, "invert": False}]},
                                ctx)
    double = D.compute_net_signals({"symbols": ["BTC-USDT-SWAP"],
                                "groups": [{"group_id": g1, "weight": 0.5, "invert": False},
                                           {"group_id": g2, "weight": 0.5, "invert": False}]},
                                ctx)
    assert single["BTC-USDT-SWAP"] == pytest.approx(double["BTC-USDT-SWAP"], abs=1e-6)

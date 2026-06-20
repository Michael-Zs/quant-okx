"""SQLite 持久化层测试：init_db + 四表 CRUD 往返 + node 树存取 + equity 外存。

用临时 DB（tmp_path）避免污染真实 runtime/console.db。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    from core.utils.config import settings
    from core.persist import db
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(settings, "BACKTESTS_DIR", tmp_path / "bt")
    db.init_db()
    yield


def test_init_creates_tables():
    from core.persist.db import get_conn
    with get_conn() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategies", "strategy_groups", "deployments", "backtests"}.issubset(names)


def test_strategy_crud():
    from core.persist import repositories as R
    sid = R.create_strategy(name="我的MA", template_name="ma_cross",
                            strategy_kind="single", params={"fast": 5, "slow": 20})
    s = R.get_strategy(sid)
    assert s["name"] == "我的MA"
    assert s["params"] == {"fast": 5, "slow": 20}
    assert s["strategy_kind"] == "single"
    assert R.update_strategy(sid, params={"fast": 10, "slow": 30})
    assert R.get_strategy(sid)["params"] == {"fast": 10, "slow": 30}
    assert R.find_strategy_by_name("我的MA")["id"] == sid
    assert R.delete_strategy(sid)
    assert R.get_strategy(sid) is None


def test_group_crud_with_node_tree():
    """策略组存整棵 node 树 spec，往返保持结构（含嵌套子节点的 weight/invert）。"""
    from core.persist import repositories as R
    spec = {
        "node_type": "allocation_group", "name": "my_group", "invert": False,
        "children": [
            {"node": {"node_type": "leaf", "name": "ma", "template_name": "ma_cross",
                      "strategy_kind": "single", "params": {"fast": 5, "slow": 20},
                      "invert": False},
             "weight": 0.6, "invert": False},
            {"node": {"node_type": "leaf", "name": "rsi", "template_name": "rsi",
                      "strategy_kind": "single", "params": {"period": 14}, "invert": True},
             "weight": 0.4, "invert": True},
        ],
    }
    gid = R.create_group(name="aggressive", spec=spec, description="激进组")
    g = R.get_group(gid)
    assert g["spec"] == spec
    assert g["spec"]["children"][1]["invert"] is True
    assert R.delete_group(gid)


def test_deployment_crud():
    from core.persist import repositories as R
    groups = [{"group_id": "grp_1", "weight": 0.7, "invert": False},
              {"group_id": "grp_2", "weight": 0.3, "invert": True}]
    did = R.create_deployment(name="live_1", is_demo=True, bar="1H", groups=groups,
                              leverage=10, initial_capital=50000)
    d = R.get_deployment(did)
    assert d["is_demo"] is True
    assert d["groups"] == groups
    assert d["leverage"] == 10
    assert R.list_deployments()[0]["id"] == did


def test_backtest_save_and_equity_external():
    """回测结果落表，equity 曲线外存 parquet，可按需读回。"""
    import pandas as pd
    from core.persist import repositories as R
    eq = pd.DataFrame({"ts": pd.date_range("2024-01-01", periods=5, freq="1h"),
                       "equity": [10000, 10100, 9900, 10500, 10800]})
    metrics = {"total_return": 0.08, "sharpe": 1.5, "n_trades": 3}
    bid = R.save_backtest(node_kind="strategy", spec={"node_type": "leaf"},
                          metrics=metrics, cfg={"initial_capital": 10000},
                          symbol="BTC-USDT-SWAP", bar="1H", days=180, equity_df=eq)
    bt = R.get_backtest(bid, with_equity=True)
    assert bt["metrics"] == metrics
    assert bt["equity"]["equity"] == [10000, 10100, 9900, 10500, 10800]
    assert len(R.list_backtests()) == 1

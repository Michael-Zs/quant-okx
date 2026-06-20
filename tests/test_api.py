"""API 层测试：CRUD 往返 + token 鉴权 + 路由注册（TestClient，不触网络）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    from core.utils.config import settings
    from core.persist import db
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(settings, "BACKTESTS_DIR", tmp_path / "bt")
    monkeypatch.setattr(settings, "API_TOKEN", "testtoken")
    db.init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api_server import app
    return TestClient(app)


H = {"X-API-Token": "testtoken"}


def test_templates_listed(client):
    r = client.get("/api/templates")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 4
    assert any(t["strategy_kind"] == "multi" for t in data["templates"])


def test_strategy_crud_requires_token(client):
    r = client.post("/api/strategies", json={"name": "s1", "template_name": "ma_cross",
                    "strategy_kind": "single", "params": {"fast": 5, "slow": 20}})
    assert r.status_code == 401


def test_strategy_crud(client):
    r = client.post("/api/strategies", json={"name": "s1", "template_name": "ma_cross",
                    "strategy_kind": "single", "params": {"fast": 5, "slow": 20}}, headers=H)
    assert r.status_code == 200
    sid = r.json()["id"]
    assert client.get("/api/strategies").json()["strategies"][0]["id"] == sid
    assert client.get(f"/api/strategies/{sid}").json()["params"] == {"fast": 5, "slow": 20}
    assert client.delete(f"/api/strategies/{sid}", headers=H).status_code == 200


def test_group_crud_and_validate(client):
    spec = {"node_type": "allocation_group", "name": "g", "invert": False,
            "children": [{"node": {"node_type": "leaf", "name": "ma", "template_name": "ma_cross",
                                   "strategy_kind": "single", "params": {"fast": 5, "slow": 20},
                                   "invert": False}, "weight": 1.0, "invert": False}]}
    r = client.post("/api/groups", json={"name": "g1", "spec": spec}, headers=H)
    assert r.status_code == 200
    gid = r.json()["id"]
    assert client.post("/api/groups/validate", json=spec, headers=H).json()["valid"] is True
    assert client.get(f"/api/groups/{gid}").json()["spec"] == spec


def test_deployment_crud(client):
    spec = {"node_type": "leaf", "name": "ma", "template_name": "ma_cross",
            "strategy_kind": "single", "params": {"fast": 5, "slow": 20}, "invert": False}
    gid = client.post("/api/groups", json={"name": "dg", "spec": spec}, headers=H).json()["id"]
    r = client.post("/api/deployments", json={"name": "dep1", "is_demo": True, "bar": "1H",
                    "symbols": ["BTC-USDT-SWAP"],
                    "groups": [{"group_id": gid, "weight": 1.0, "invert": False}]}, headers=H)
    assert r.status_code == 200
    did = r.json()["id"]
    deps = client.get("/api/deployments").json()["deployments"]
    assert deps[0]["id"] == did
    assert deps[0]["symbols"] == ["BTC-USDT-SWAP"]


def test_routes_registered(client):
    paths = {r.path for r in client.app.routes}
    for p in ["/api/templates", "/api/strategies", "/api/groups", "/api/deployments",
              "/api/backtest", "/api/backtests/{bid}", "/ws/backtest",
              "/api/deployments/{did}/start"]:
        assert p in paths, f"路由未注册: {p}"

"""API 层测试：CRUD 往返 + token 鉴权 + 路由注册（TestClient，不触网络）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pandas as pd


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    from core.utils.config import settings
    from core.persist import db
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(settings, "BACKTESTS_DIR", tmp_path / "bt")
    monkeypatch.setattr(settings, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(settings, "API_TOKEN", "testtoken")
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api_server import app
    return TestClient(app)


H = {"X-API-Token": "testtoken"}


def _dummy_ohlcv(periods: int = 48) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=periods, freq="h")
    close = [100 + i for i in range(periods)]
    return pd.DataFrame({
        "ts": ts,
        "open": close,
        "high": [v + 1 for v in close],
        "low": [v - 1 for v in close],
        "close": close,
        "volume": [1.0] * periods,
    })


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


def test_config_cache_counts_all_cache_files(client):
    from core.utils.config import settings
    (settings.CACHE_DIR / "BTC_USDT_SWAP_1H.parquet").write_bytes(b"parquet-a")
    (settings.CACHE_DIR / "ETH_USDT_SWAP_4H.parquet").write_bytes(b"parquet-b")
    (settings.CACHE_DIR / "swap_instruments_USDT.json").write_text('["BTC-USDT-SWAP"]', encoding="utf-8")

    r = client.get("/api/config")
    assert r.status_code == 200
    cache = r.json()["cache"]
    assert cache["count"] == 3
    assert cache["parquet_count"] == 2
    assert cache["json_count"] == 1
    assert cache["size_bytes"] == (
        cache["parquet_size_bytes"] + cache["json_size_bytes"]
    )


def test_clear_cache_route_clears_all_cache_types(client):
    from core.utils.config import settings
    (settings.CACHE_DIR / "BTC_USDT_SWAP_1H.parquet").write_bytes(b"parquet-a")
    (settings.CACHE_DIR / "swap_instruments_USDT.json").write_text('["BTC-USDT-SWAP"]', encoding="utf-8")

    r = client.post("/api/cache/clear", headers=H)
    assert r.status_code == 200
    assert r.json()["cleared"] == 2
    assert list(settings.CACHE_DIR.iterdir()) == []


def test_clear_cache_route_supports_symbol_bar_scoping(client):
    from core.utils.config import settings
    (settings.CACHE_DIR / "BTC_USDT_SWAP_1H.parquet").write_bytes(b"btc-1h")
    (settings.CACHE_DIR / "BTC_USDT_SWAP_4H.parquet").write_bytes(b"btc-4h")
    (settings.CACHE_DIR / "ETH_USDT_SWAP_1H.parquet").write_bytes(b"eth-1h")
    (settings.CACHE_DIR / "swap_instruments_USDT.json").write_text('["BTC-USDT-SWAP"]', encoding="utf-8")

    r = client.post("/api/cache/clear?symbol=BTC-USDT-SWAP&bar=1H&include_instruments=false", headers=H)
    assert r.status_code == 200
    assert r.json()["cleared"] == 1
    remaining = sorted(p.name for p in settings.CACHE_DIR.iterdir())
    assert remaining == [
        "BTC_USDT_SWAP_4H.parquet",
        "ETH_USDT_SWAP_1H.parquet",
        "swap_instruments_USDT.json",
    ]


def test_backtest_detail_supports_max_points_sampling(client):
    from core.persist import repositories as R

    eq = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=10, freq="h"),
        "equity": [10000 + i * 10 for i in range(10)],
    })
    bid = R.save_backtest(
        node_kind="adhoc",
        ref_id=None,
        spec={"node_type": "leaf"},
        metrics={"total_return": 0.1},
        cfg={"bar": "1H"},
        symbol="BTC-USDT-SWAP",
        bar="1H",
        days=10,
        equity_df=eq,
    )

    r = client.get(f"/api/backtests/{bid}?with_equity=true&max_points=4")
    assert r.status_code == 200
    data = r.json()
    assert data["equity"]["sampled"] is True
    assert data["equity"]["total_points"] == 10
    assert data["equity"]["returned_points"] == 4
    assert data["equity"]["ts"][0].startswith("2026-01-01")
    assert data["equity"]["equity"][0] == 10000.0
    assert data["equity"]["equity"][-1] == 10090.0


def test_sampling_helper_keeps_first_and_last_points():
    from api.response_sampling import sample_curve

    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=9, freq="h"),
        "equity": [float(i) for i in range(9)],
    })
    sampled = sample_curve(df, "equity", 4)
    assert sampled is not None
    assert sampled["returned_points"] == 4
    assert sampled["equity"][0] == 0.0
    assert sampled["equity"][-1] == 8.0


def test_multi_backtest_supports_days_list_and_summaries(client, monkeypatch):
    import api.routes_control as rc
    monkeypatch.setattr(rc, "get_data", lambda symbol, bar, days: _dummy_ohlcv(64))

    req = {
        "node_spec": {
            "node_type": "leaf",
            "name": "eq",
            "template_name": "equal_weight",
            "strategy_kind": "multi",
            "params": {},
        },
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "bar": "1H",
        "days_list": [10, 20],
        "max_points": 5,
        "response_mode": "compact",
    }
    r = client.post("/api/multi_backtest", json=req, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["days_list"] == [10, 20]
    assert len(data["windows"]) == 2
    first = data["windows"][0]
    assert first["equity"]["returned_points"] == 5
    assert first["holdings"]["returned_points"] == 5
    assert first["key_points"]["start_equity"] == 10000.0
    assert "trade_summary" in first


def test_grid_search_supports_multi_strategy_symbols(client, monkeypatch):
    import api.routes_control as rc
    monkeypatch.setattr(rc, "get_data", lambda symbol, bar, days: _dummy_ohlcv(48))

    req = {
        "template_name": "equal_weight",
        "strategy_kind": "multi",
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "bar": "1H",
        "days_list": [10, 20],
        "metric": "robust_score",
        "param_ranges": {"dummy": [1, 2, 1]},
        "n_jobs": 1,
    }
    r = client.post("/api/grid_search", json=req, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert "windows" in data["results"][0]
    assert "robust_score" in data["results"][0]


def test_backtest_exposes_benchmark_metrics_and_curve(client, monkeypatch):
    """单币回测必须返回基准对比指标 + 基准权益曲线，且可持久化后读回。"""
    import api.routes_control as rc
    monkeypatch.setattr(rc, "get_data", lambda symbol, bar, days: _dummy_ohlcv(64))

    req = {
        "node_spec": {"node_type": "leaf", "name": "ma", "template_name": "ma_cross",
                      "strategy_kind": "single", "params": {"fast": 5, "slow": 20}},
        "symbol": "BTC-USDT-SWAP", "bar": "1H", "days": 10,
        "response_mode": "full", "max_points": 8,
    }
    r = client.post("/api/backtest", json=req, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    # metrics.benchmark 子字典存在且含全部六个指标
    bench = body["metrics"].get("benchmark")
    assert bench is not None
    for key in ("beta", "alpha", "correlation", "tracking_error",
                "information_ratio", "excess_return"):
        assert key in bench
    # 基准权益曲线返回（与权益曲线同采样长度）
    assert body["benchmark"]["returned_points"] == 8
    assert body["benchmark"]["total_points"] == 64
    # 持久化后 GET 能读回 benchmark 指标 + benchmark 采样曲线
    bid = body["backtest_id"]
    g = client.get(f"/api/backtests/{bid}?with_equity=true").json()
    assert "benchmark" in g["metrics"]
    assert "benchmark" in g                # 并入同一 parquet 的额外列，读取时单独采样
    assert g["benchmark"]["returned_points"] == 64   # max_points=None → 不采样


def test_multi_backtest_exposes_benchmark_curve(client, monkeypatch):
    """多币回测返回组合层基准权益曲线。"""
    import api.routes_control as rc
    monkeypatch.setattr(rc, "get_data", lambda symbol, bar, days: _dummy_ohlcv(48))
    req = {
        "node_spec": {"node_type": "leaf", "name": "eq", "template_name": "equal_weight",
                      "strategy_kind": "multi", "params": {}},
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "bar": "1H", "days": 10, "max_points": 5, "response_mode": "compact",
    }
    r = client.post("/api/multi_backtest", json=req, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert "benchmark" in body["metrics"]
    assert body["benchmark"] is not None
    assert body["benchmark"]["returned_points"] == 5

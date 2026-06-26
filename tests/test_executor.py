"""Executor 单元测试。

测 aggregate（软截断/多部署求和）与 reconcile_and_trade（fake exchange）。
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from core.executor.intent import (
    intent_path, write_intent, read_intent, load_fresh_intents, aggregate
)
from core.executor.engine import reconcile_and_trade, run_once_cycle
from core.utils.config import settings


@pytest.fixture(autouse=True)
def ensure_intents_dir():
    """确保 INTENTS_DIR 存在。"""
    settings.INTENTS_DIR.mkdir(parents=True, exist_ok=True)
    # 清理所有旧文件（包括之前测试残留的）
    for p in settings.INTENTS_DIR.glob("*.json"):
        p.unlink()
    yield
    # 清理测试文件
    for p in settings.INTENTS_DIR.glob("*.json"):
        p.unlink()


class FakeExchange:
    """Fake exchange for testing reconcile_and_trade."""

    def __init__(self, equity: float = 10000.0, positions: dict = None):
        self.equity = equity
        self.positions = positions or {}
        self.orders = []
        self.leverages = {}

    def fetch_balance(self):
        # 返回 get_equity 期望的结构
        return {
            "USDT": {
                "free": self.equity,
                "used": 0.0,
                "total": self.equity,
            },
            "total": {
                "USDT": self.equity,
            },
            "info": {},
        }

    def fetch_ticker(self, symbol):
        # 简单 mock，BTC/USDT:USDT -> 50000, ETH/USDT:USDT -> 3000
        if "BTC" in symbol:
            return {"last": 50000.0}
        if "ETH" in symbol:
            return {"last": 3000.0}
        return {"last": 100.0}

    def fetch_tickers(self, symbols):
        return {s: self.fetch_ticker(s) for s in symbols}

    def fetch_positions(self, symbols=None):
        # 返回 OKX 格式持仓
        out = []
        for okx_sym, pos in self.positions.items():
            if pos["contracts"] > 0:
                ccxt_sym = okx_to_ccxt(okx_sym)
                out.append({
                    "symbol": ccxt_sym,
                    "contracts": pos["contracts"],
                    "side": "long" if pos["dir"] > 0 else "short",
                    "entryPrice": pos.get("entry_price", 0),
                    "unrealizedPnl": pos.get("unrealized_pnl", 0),
                })
        return out

    def set_leverage(self, leverage, symbol):
        self.leverages[symbol] = leverage

    def create_order(self, symbol, _type, side, amount, params=None):
        self.orders.append({
            "symbol": symbol,
            "side": side,
            "amount": amount,
        })
        return {"id": f"order_{len(self.orders)}"}


def okx_to_ccxt(symbol: str) -> str:
    """简化版转换（复用 core/data/symbols.py）"""
    parts = symbol.split("-")
    if len(parts) == 3:
        return f"{parts[0]}/{parts[1]}:{parts[1]}"
    if len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    return symbol


class TestIntent:
    """测试 intent 读写与加载。"""

    def test_intent_path(self):
        assert intent_path("test_123") == settings.INTENTS_DIR / "test_123.json"

    def test_write_read_roundtrip(self):
        intent = {
            "deployment_id": "test_001",
            "signals": {"BTC-USDT-SWAP": 1.0, "ETH-USDT-SWAP": -0.5},
            "capital_weight": 0.5,
            "position_ratio": 0.8,
            "leverage": 5,
            "is_demo": True,
            "bar": "1H",
            "ts": time.time(),
        }
        write_intent(intent)
        loaded = read_intent(intent_path("test_001"))
        assert loaded is not None
        assert loaded["deployment_id"] == "test_001"
        assert loaded["signals"]["BTC-USDT-SWAP"] == 1.0
        assert loaded["capital_weight"] == 0.5

    def test_read_corrupt_returns_none(self):
        path = intent_path("test_corrupt")
        path.write_text("invalid json", encoding="utf-8")
        assert read_intent(path) is None

    def test_read_missing_returns_none(self):
        assert read_intent(intent_path("nonexistent")) is None

    def test_load_fresh_intents_filters_stale(self):
        # 写入一个过期 intent
        stale = {
            "deployment_id": "test_stale",
            "signals": {},
            "ts": time.time() - 7300,  # 超过 7200s
        }
        write_intent(stale)

        # 写入一个新鲜 intent
        fresh = {
            "deployment_id": "test_fresh",
            "signals": {"BTC-USDT-SWAP": 0.5},
            "ts": time.time(),
        }
        write_intent(fresh)

        intents = load_fresh_intents()
        ids = [it["deployment_id"] for it in intents]
        assert "test_fresh" in ids
        assert "test_stale" not in ids


class TestAggregate:
    """测试聚合逻辑。"""

    def test_single_deployment(self):
        intents = [{
            "deployment_id": "d1",
            "signals": {"BTC-USDT-SWAP": 1.0},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
        }]
        target, meta = aggregate(intents, equity=10000)
        assert target["BTC-USDT-SWAP"] == 10000 * 1.0 * 0.5 * 2  # 10000
        assert meta["sum_cw_pr"] == 0.5
        assert meta["scale"] == 1.0
        assert meta["warn"] is None

    def test_multiple_deployments_sum(self):
        intents = [
            {
                "deployment_id": "d1",
                "signals": {"BTC-USDT-SWAP": 1.0},
                "capital_weight": 0.5,
                "position_ratio": 0.8,
                "leverage": 2,
            },
            {
                "deployment_id": "d2",
                "signals": {"BTC-USDT-SWAP": 0.5},
                "capital_weight": 0.5,
                "position_ratio": 0.6,
                "leverage": 2,
            },
        ]
        target, meta = aggregate(intents, equity=10000)
        # d1: 10000 * 0.5 * 0.8 * 2 * 1.0 = 8000
        # d2: 10000 * 0.5 * 0.6 * 2 * 0.5 = 3000
        # total: 11000
        assert target["BTC-USDT-SWAP"] == 11000
        assert meta["sum_cw_pr"] == 0.5 * 0.8 + 0.5 * 0.6  # 0.7
        assert meta["warn"] is None

    def test_soft_truncate_when_over_1(self):
        intents = [
            {
                "deployment_id": "d1",
                "signals": {"BTC-USDT-SWAP": 1.0},
                "capital_weight": 0.8,
                "position_ratio": 0.8,
                "leverage": 2,
            },
            {
                "deployment_id": "d2",
                "signals": {"ETH-USDT-SWAP": 1.0},
                "capital_weight": 0.6,
                "position_ratio": 0.7,
                "leverage": 2,
            },
        ]
        target, meta = aggregate(intents, equity=10000)
        # sum_cw_pr = 0.8*0.8 + 0.6*0.7 = 0.64 + 0.42 = 1.06 > 1
        assert meta["sum_cw_pr"] == 1.06
        assert meta["scale"] == pytest.approx(1.0 / 1.06, rel=0.01)
        assert meta["warn"] is not None
        # 目标被缩放
        d1_unscaled = 10000 * 0.8 * 0.8 * 2 * 1.0  # 12800
        assert target["BTC-USDT-SWAP"] == pytest.approx(d1_unscaled * meta["scale"], rel=0.01)

    def test_multi_symbol_aggregation(self):
        intents = [{
            "deployment_id": "d1",
            "signals": {
                "BTC-USDT-SWAP": 0.8,
                "ETH-USDT-SWAP": -0.4,
            },
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 3,
        }]
        target, meta = aggregate(intents, equity=10000)
        assert target["BTC-USDT-SWAP"] == 10000 * 1.0 * 0.5 * 3 * 0.8  # 12000
        assert target["ETH-USDT-SWAP"] == 10000 * 1.0 * 0.5 * 3 * (-0.4)  # -6000


class TestReconcile:
    """测试对账下单循环。"""

    def test_hold_when_delta_small(self):
        ex = FakeExchange(equity=10000)
        intents = [{
            "deployment_id": "d1",
            "signals": {"BTC-USDT-SWAP": 0.5},
            "capital_weight": 1.0,
            "position_ratio": 0.2,
            "leverage": 2,
        }]
        # 当前持仓 2000，目标也是 2000，应 hold
        ex.positions = {
            "BTC-USDT-SWAP": {"dir": 1, "contracts": 0.04, "entry_price": 50000, "unrealized_pnl": 0},
        }
        result = reconcile_and_trade(ex, intents)
        assert result["equity"] == 10000
        assert "hold" in result["actions"][0]
        assert len(ex.orders) == 0

    def test_buy_when_target_higher(self):
        ex = FakeExchange(equity=10000)
        intents = [{
            "deployment_id": "d1",
            "signals": {"BTC-USDT-SWAP": 1.0},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
        }]
        # 当前无持仓，目标 10000
        result = reconcile_and_trade(ex, intents)
        assert result["equity"] == 10000
        assert result["target"]["BTC-USDT-SWAP"] == 10000
        assert len(ex.orders) == 1
        assert ex.orders[0]["side"] == "buy"
        # amount = 10000 / 50000 = 0.2
        assert ex.orders[0]["amount"] == 0.2

    def test_close_position_when_target_zero(self):
        ex = FakeExchange(equity=10000)
        intents = [{
            "deployment_id": "d1",
            "signals": {"BTC-USDT-SWAP": 0.0},  # 目标 0
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
        }]
        # 当前有 0.2 BTC 多头
        ex.positions = {
            "BTC-USDT-SWAP": {"dir": 1, "contracts": 0.2, "entry_price": 50000, "unrealized_pnl": 0},
        }
        result = reconcile_and_trade(ex, intents)
        assert result["target"]["BTC-USDT-SWAP"] == 0
        assert len(ex.orders) == 1
        assert ex.orders[0]["side"] == "sell"
        assert ex.orders[0]["amount"] == 0.2

    def test_reconcile_includes_all_positions(self):
        """关键修正：对账集合 = intents ∌ 账户持仓。"""
        ex = FakeExchange(equity=10000)
        intents = [{
            "deployment_id": "d1",
            "signals": {"BTC-USDT-SWAP": 1.0},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
        }]
        # 账户有 ETH 持仓，但 intents 不含 ETH → 应平掉
        ex.positions = {
            "BTC-USDT-SWAP": {"dir": 1, "contracts": 0.1, "entry_price": 50000, "unrealized_pnl": 0},
            "ETH-USDT-SWAP": {"dir": 1, "contracts": 1.0, "entry_price": 3000, "unrealized_pnl": 0},
        }
        result = reconcile_and_trade(ex, intents)
        # ETH 应平掉（target 默认 0）
        eth_actions = [a for a in result["actions"] if "ETH" in a]
        assert len(eth_actions) > 0
        # 至少有一个 sell ETH 动作
        assert any("sell" in a for a in eth_actions)

    def test_single_symbol_error_doesnt_interrupt(self):
        """单个 symbol 下单失败不中断其他 symbol。"""
        class FailingExchange(FakeExchange):
            def create_order(self, symbol, _type, side, amount, params=None):
                if "BTC" in symbol:
                    raise Exception("BTC 下单失败")
                return super().create_order(symbol, _type, side, amount, params)

        ex = FailingExchange(equity=10000)
        intents = [{
            "deployment_id": "d1",
            "signals": {"BTC-USDT-SWAP": 1.0, "ETH-USDT-SWAP": 1.0},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
        }]
        result = reconcile_and_trade(ex, intents)
        # ETH 应下单成功
        assert len(ex.orders) == 1
        assert "ETH" in ex.orders[0]["symbol"]
        # BTC 有错误记录
        btc_errors = [e for e in result["errors"] if "BTC" in str(e.get("sym", ""))]
        assert len(btc_errors) > 0

    def test_empty_intents_closes_all(self):
        """空 intents 时应平掉所有持仓。"""
        ex = FakeExchange(equity=10000)
        ex.positions = {
            "BTC-USDT-SWAP": {"dir": 1, "contracts": 0.2, "entry_price": 50000, "unrealized_pnl": 0},
            "ETH-USDT-SWAP": {"dir": -1, "contracts": 2.0, "entry_price": 3000, "unrealized_pnl": 0},
        }
        result = reconcile_and_trade(ex, intents=[])
        # 应平掉所有持仓
        assert len(ex.orders) == 2
        # 一个 sell BTC，一个 buy ETH（平空）
        sides = {o["side"] for o in ex.orders}
        assert sides == {"sell", "buy"}

    def test_exchange_none_returns_error(self):
        result = reconcile_and_trade(None, intents=[])
        assert "error" in result


class TestRunOnceCycle:
    """测试完整循环。"""

    def test_splits_demo_live(self):
        demo_ex = FakeExchange(equity=10000)
        live_ex = FakeExchange(equity=20000)

        # 写入 intents
        write_intent({
            "deployment_id": "demo_d1",
            "signals": {"BTC-USDT-SWAP": 0.5},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
            "is_demo": True,
            "ts": time.time(),
        })
        write_intent({
            "deployment_id": "live_d1",
            "signals": {"ETH-USDT-SWAP": 0.5},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
            "is_demo": False,
            "ts": time.time(),
        })

        result = run_once_cycle(demo_ex, live_ex)
        assert "demo" in result
        assert "live" in result
        assert result["deployment_count"]["demo"] == 1
        assert result["deployment_count"]["live"] == 1
        assert result["demo"]["equity"] == 10000
        assert result["live"]["equity"] == 20000

    def test_handles_none_exchange(self):
        result = run_once_cycle(demo_ex=None, live_ex=None)
        assert "error" in result["demo"]
        assert "error" in result["live"]

    def test_loads_intents_from_file(self):
        demo_ex = FakeExchange(equity=10000)
        live_ex = FakeExchange(equity=20000)

        # 清理
        for p in settings.INTENTS_DIR.glob("*.json"):
            p.unlink()

        write_intent({
            "deployment_id": "demo_test",
            "signals": {},
            "capital_weight": 1.0,
            "position_ratio": 0.5,
            "leverage": 2,
            "is_demo": True,
            "ts": time.time(),
        })

        result = run_once_cycle(demo_ex, live_ex)
        assert "demo" in result
        # 应该加载到刚写的 intent
        assert result["deployment_count"]["demo"] >= 1

    def test_empty_intents_waits_doesnt_flatten(self):
        """fail-safe：整组无 intent 时跳过对账，不平掉账户现有仓位。

        部署/重启时序中 executor 可能早于 daemon 第一个 intent 启动，
        此时绝不能把账户现有仓位误判为"目标 0"全平。
        """
        ex = FakeExchange(equity=10000)
        ex.positions = {
            "BTC-USDT-SWAP": {"dir": 1, "contracts": 0.2, "entry_price": 50000, "unrealized_pnl": 0},
        }
        for p in settings.INTENTS_DIR.glob("*.json"):  # 清空 intents
            p.unlink()
        result = run_once_cycle(demo_ex=ex, live_ex=None)
        assert result["demo"]["status"] == "waiting_for_intents"
        assert len(ex.orders) == 0  # 没有平仓单

"""阶段①统一节点抽象（core/strategy/node.py + invert.py）测试。

覆盖：invert 原语、LeafNode 信号生成与 spec 往返、SignalCombiner 合成、
AllocationGroup.collect 与投影、链路级 invert（XOR）语义。
单币链路用内置 ma_cross / rsi 模板驱动。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from core.strategy import node
from core.strategy.invert import invert_df, invert_signals
from core.strategy.registry import StrategyRegistry

StrategyRegistry.discover_all()


def _ctx():
    np.random.seed(42)
    n = 200
    ts = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = 100 + np.random.randn(n).cumsum()
    df = pd.DataFrame({"ts": ts, "open": close, "high": close + 1,
                       "low": close - 1, "close": close, "vol": 1000.0})
    return node.NodeContext(data={"BTC-USDT-SWAP": df}, primary_symbol="BTC-USDT-SWAP")


def _leaf(template, params=None, **kw):
    return node.LeafNode(name=template, template_name=template,
                         strategy_kind="single", params=params or {}, **kw)


def test_invert_df():
    df = pd.DataFrame({"signal": [1, -1, 0, 1]})
    out = invert_df(df)
    assert out["signal"].tolist() == [-1, 1, 0, -1]
    assert df["signal"].tolist() == [1, -1, 0, 1]      # 不改入参


def test_invert_signals_passthrough_when_false():
    sigs = {"BTC": pd.DataFrame({"signal": [1, -1]})}
    assert invert_signals(sigs, False) is sigs          # invert=False 原样返回
    out = invert_signals(sigs, True)
    assert out["BTC"]["signal"].tolist() == [-1, 1]


def test_leaf_generate_signals():
    leaf = _leaf("ma_cross", {"fast": 5, "slow": 20})
    sig = leaf.generate_signals(_ctx())
    assert list(sig.keys()) == ["BTC-USDT-SWAP"]
    s = sig["BTC-USDT-SWAP"]["signal"]
    assert len(s) == 200
    assert set(s.unique()).issubset({-1, 0, 1})


def test_leaf_spec_roundtrip():
    leaf = _leaf("ma_cross", {"fast": 7, "slow": 21}, invert=True)
    leaf2 = node.node_from_spec(leaf.to_spec())
    assert leaf2.template_name == "ma_cross"
    assert leaf2.params == {"fast": 7, "slow": 21}
    assert leaf2.invert is True
    ctx = _ctx()
    s1 = leaf.generate_signals(ctx)["BTC-USDT-SWAP"]["signal"]
    s2 = leaf2.generate_signals(ctx)["BTC-USDT-SWAP"]["signal"]
    assert (s1 == s2).all()


def test_signal_combiner_vote_and_roundtrip():
    children = [node.ChildRef(_leaf("ma_cross", {"fast": 5, "slow": 20})),
                node.ChildRef(_leaf("rsi", {"period": 14}))]
    combo = node.SignalCombiner(name="c", mode="vote", children=children)
    sig = combo.generate_signals(_ctx())
    assert len(sig["BTC-USDT-SWAP"]["signal"]) == 200
    combo2 = node.node_from_spec(combo.to_spec())
    assert combo2.mode == "vote"
    assert len(combo2.children) == 2


def test_allocation_group_collect_and_projection():
    children = [node.ChildRef(_leaf("ma_cross", {"fast": 5, "slow": 20}), weight=0.6),
                node.ChildRef(_leaf("rsi", {"period": 14}), weight=0.4, invert=True)]
    grp = node.AllocationGroup(name="g", children=children)
    items = grp.collect(_ctx())
    assert len(items) == 2
    assert items[0][0].weight == 0.6
    assert items[1][0].invert is True
    sig = grp.generate_signals(_ctx())          # 投影
    assert len(sig["BTC-USDT-SWAP"]["signal"]) == 200


def test_leaf_invert_flips_signal():
    """LeafNode.invert=True 应把信号取反（XOR 单层）。"""
    ctx = _ctx()
    s_pos = _leaf("ma_cross", {"fast": 5, "slow": 20}).generate_signals(ctx)["BTC-USDT-SWAP"]["signal"]
    leaf_inv = _leaf("ma_cross", {"fast": 5, "slow": 20})
    leaf_inv.invert = True
    s_neg = leaf_inv.generate_signals(ctx)["BTC-USDT-SWAP"]["signal"]
    assert (s_pos == -s_neg).all()


# ---------- run_node / run_group / scale_capital ----------

def test_scale_capital():
    from core.backtest.engine import BacktestConfig
    cfg = BacktestConfig(initial_capital=10000, leverage=5, fee_rate=0.001)
    sub = cfg.scale_capital(0.3)
    assert sub.initial_capital == 3000
    assert sub.leverage == 5 and sub.fee_rate == 0.001   # 其余字段不变
    assert cfg.initial_capital == 10000                    # 不改原配置


def test_run_node_single_leaf():
    from core.backtest.engine import run_node, BacktestConfig
    leaf = _leaf("ma_cross", {"fast": 5, "slow": 20})
    out = run_node(leaf, _ctx(), BacktestConfig(initial_capital=10000))
    assert out.report_kind == "single"
    assert "total_return" in out.metrics and "sharpe" in out.metrics
    assert len(out.equity_curve) == 200


def test_run_node_signal_combiner():
    from core.backtest.engine import run_node, BacktestConfig
    children = [node.ChildRef(_leaf("ma_cross", {"fast": 5, "slow": 20})),
                node.ChildRef(_leaf("rsi", {"period": 14}))]
    out = run_node(node.SignalCombiner(name="c", mode="vote", children=children),
                   _ctx(), BacktestConfig(initial_capital=10000))
    assert out.report_kind == "single"
    assert "sharpe" in out.metrics


def test_run_node_allocation_group():
    from core.backtest.engine import run_node, BacktestConfig
    children = [node.ChildRef(_leaf("ma_cross", {"fast": 5, "slow": 20}), weight=0.6),
                node.ChildRef(_leaf("rsi", {"period": 14}), weight=0.4)]
    out = run_node(node.AllocationGroup(name="g", children=children),
                   _ctx(), BacktestConfig(initial_capital=10000))
    assert out.report_kind == "group"
    assert len(out.per_leg) == 2
    assert "total_return" in out.metrics
    assert len(out.equity_curve) == 200


def test_regression_combiner_matches_old_ensemble():
    """回归：新 SignalCombiner 与旧 Ensemble 在相同子策略/模式下，合成 signal 应逐点一致。

    这是「回测可信度可从旧实现迁移到新抽象」的关键保证——_combine 算法从
    ensemble.py 搬运到 node.py 后不得改变数值结果。
    """
    from core.strategy.ensemble import Ensemble
    from core.strategy.registry import StrategyRegistry
    ctx = _ctx()
    df = ctx.data["BTC-USDT-SWAP"]
    ma_cls, rsi_cls = StrategyRegistry.get("ma_cross"), StrategyRegistry.get("rsi")
    for mode in ("vote", "majority"):
        old = Ensemble([ma_cls(fast=5, slow=20), rsi_cls(period=14)], mode=mode)
        old_sig = old.generate_signals(df)["signal"].fillna(0).astype(int).values
        children = [node.ChildRef(_leaf("ma_cross", {"fast": 5, "slow": 20})),
                    node.ChildRef(_leaf("rsi", {"period": 14}))]
        new_sig = (node.SignalCombiner(name="c", mode=mode, children=children)
                   .generate_signals(ctx)["BTC-USDT-SWAP"]["signal"]
                   .fillna(0).astype(int).values)
        assert (old_sig == new_sig).all(), f"模式 {mode} 下新旧合成 signal 不一致"

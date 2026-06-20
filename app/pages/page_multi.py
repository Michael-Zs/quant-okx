"""多币策略页：跨币种择优（动量轮动等）+ 单币策略多币批量运行。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.state import ensure_registry, get, set, coin_options
from app.components.param_controls import render_params
from app.components.metrics_card import show_metrics
from core.strategy.registry import StrategyRegistry
from core.strategy.context import Context
from core.data.multi import get_multi
from core.data.cache import get_data
from core.data.symbols import COMMON_SYMBOLS, COMMON_BARS, bars_per_year
from core.backtest.engine import BacktestConfig
from core.backtest.multi import run_multi

st.title("🌐 多币策略")
st.caption("跨币种择优（动量轮动 / 相对强弱）+ 单币策略多币批量运行。")
ensure_registry()

all_strats = StrategyRegistry.all()
info_map = {s["name"]: s for s in StrategyRegistry.info()}

# ---------- 币种 + 数据 ----------
c1, c2, c3 = st.columns([3, 1, 1])
symbols = c1.multiselect("选择币种（≥2，可搜索全部品种）", coin_options(),
                         default=["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"], key="mu_symbols")
bar = c2.selectbox("周期", COMMON_BARS, index=1, key="mu_bar")
days = c3.slider("天数", 60, 730, 180, 10, key="mu_days")

if len(symbols) < 2:
    st.info("请至少选择 2 个币种")
    st.stop()

dkey = f"{'|'.join(symbols)}_{bar}_{days}"
if get("mu_data_key") != dkey or get("mu_dfs") is None:
    try:
        with st.spinner("加载并对齐多币数据…"):
            dfs = get_multi(symbols, bar, days)
            set("mu_dfs", dfs)
            set("mu_data_key", dkey)
    except Exception as e:
        st.error(f"数据加载失败：{e}")
        st.stop()
dfs: dict = get("mu_dfs")
if not dfs or len(dfs) < 2:
    st.warning("有效数据不足（部分币种可能无公共历史）")
    st.stop()
_common = len(next(iter(dfs.values())))
st.caption(f"{len(dfs)} 币种 × {_common} 根K线（已对齐公共时间轴）")

# 各币种历史长度诊断：揪出上市晚、拖累公共历史的币
_len_info = []
for _s in symbols:
    try:
        _len_info.append((_s, len(get_data(_s, bar, days))))
    except Exception:
        _len_info.append((_s, 0))
with st.expander(f"📋 各币种可用历史（公共 {_common} 根）", expanded=False):
    st.dataframe(pd.DataFrame([
        {"币种": s, "可用K线": ln,
         "状态": "⚠️ 拖累公共历史" if ln < _common * 2 and ln < days else "OK"}
        for s, ln in _len_info
    ]), hide_index=True)
    if _common < min(days, 60):
        _short = [s for s, ln in _len_info if ln <= _common + 5]
        st.warning(
            f"⚠️ 公共历史只有 {_common} 根，被这些上市较晚的币限制：{', '.join(_short)}。"
            "跨币策略需要足够长的公共历史，否则信号不足、结果可能全为 0。"
            "建议在上方取消选中这些新币，或缩短回测天数。")

# ---------- 策略 ----------
names = list(all_strats.keys())
sname = st.selectbox(
    "策略", names,
    format_func=lambda n: f"{all_strats[n].display_name} · {info_map[n]['kind']}({'跨币' if info_map[n]['kind']=='multi' else '批量'})",
    key="mu_strat")
cls = all_strats[sname]
is_multi = info_map[sname]["kind"] == "multi"
st.caption(cls.description + (" ｜ 【跨币策略】同时看多币种择优" if is_multi else " ｜ 【批量】该单币策略在各币种独立运行"))
with st.expander("策略参数", expanded=True):
    params = render_params(cls, key_prefix="mu_")

with st.expander("⚙️ 引擎参数", expanded=False):
    e1, e2, e3 = st.columns(3)
    init = e1.number_input("初始资金", 1000, 1_000_000, 10000, 1000, key="mu_init")
    lev = e2.number_input("杠杆", 1, 125, 5, 1, key="mu_lev")
    ratio = e3.slider("仓位比例", 0.01, 1.0, 0.1, 0.01, key="mu_ratio")

with st.expander("💰 资金分配（各币种资金槽占比，默认等权）", expanded=False):
    alloc_cols = st.columns(min(len(dfs), 4))
    for i, s in enumerate(dfs):
        alloc_cols[i % len(alloc_cols)].slider(s.split("-")[0], 0.0, 2.0, 1.0, 0.1, key=f"mu_alloc_{s}")

# ---------- 回测 ----------
invert = st.toggle("🔄 反转信号（1↔-1）", value=False, key="mu_invert",
                   help="反转所有币种信号方向，方向反了的亏损策略通常转盈。")
if st.button("🚀 组合回测", type="primary", key="mu_run"):
    with st.spinner("回测中…"):
        ctx = Context(dfs, bar)
        if is_multi:
            signals = cls(**params).generate_signals(ctx)
        else:
            strat = cls(**params)
            signals = {s: strat.generate_signals(dfs[s]) for s in dfs}
        alloc = {s: st.session_state[f"mu_alloc_{s}"] for s in dfs}
        cfg = BacktestConfig(initial_capital=float(init), leverage=int(lev),
                             position_ratio=float(ratio), bars_per_year=bars_per_year(bar))
        rep = run_multi(signals, cfg, allocation=alloc, invert=invert)
        set("mu_report", rep)
    st.success("组合回测完成 ✔")

rep = get("mu_report")
if rep is None:
    st.info("选好币种与策略，点「组合回测」查看结果")
    st.stop()

show_metrics(rep.metrics)

# 合成权益 + 各币种权益叠加
fig = go.Figure()
fig.add_trace(go.Scatter(x=rep.equity_curve["ts"], y=rep.equity_curve["equity"],
                         name="组合(合成)", line=dict(width=2.5, color="#4dd0e1")))
for name, w, r in rep.per_symbol:
    fig.add_trace(go.Scatter(x=r.equity_curve["ts"], y=r.equity_curve["equity"],
                             name=f"{name.split('-')[0]} ({w:.0%})", line=dict(width=1, dash="dot")))
fig.add_hline(y=rep.initial_capital, line_dash="dash", line_color="gray")
fig.update_layout(template="plotly_dark", height=430,
                  title="组合权益 vs 各币种权益", margin=dict(l=40, r=20, t=40, b=20))
st.plotly_chart(fig, width="stretch")

# 持仓时间线热力图
hold = rep.holdings.set_index("ts")
z = hold.values
fig2 = go.Figure(go.Heatmap(
    z=z.T, x=hold.index, y=[s.split("-")[0] for s in hold.columns],
    colorscale=[[0, "#1a1a1a"], [0.5, "#2a2a2a"], [0.51, "#00e676"], [1, "#00e676"]],
    colorbar=dict(title="持仓", tickvals=[0, 1], ticktext=["空仓", "持仓"])))
fig2.update_layout(template="plotly_dark", height=260, title="持仓时间线（绿=持仓）",
                   yaxis=dict(autorange="reversed"), margin=dict(l=40, r=20, t=40, b=20))
st.plotly_chart(fig2, width="stretch")

# 各币种贡献表
rows = []
for name, w, r in rep.per_symbol:
    rows.append({
        "币种": name, "资金占比": f"{w:.0%}",
        "总收益": f"{r.metrics['total_return']:.2%}",
        "最大回撤": f"{r.metrics['max_drawdown']:.2%}",
        "夏普": f"{r.metrics['sharpe']:.2f}", "交易次数": r.metrics["n_trades"]})
st.dataframe(pd.DataFrame(rows), hide_index=True)

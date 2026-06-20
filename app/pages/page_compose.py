"""策略组合页：Ensemble（信号投票组合）+ Portfolio（资金分配组合）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.state import ensure_registry, get, set
from app.components.param_controls import render_params
from app.components.metrics_card import show_metrics
from app.components.chart_equity import plot_equity, plot_drawdown
from core.strategy.registry import StrategyRegistry
from core.strategy.ensemble import Ensemble
from core.strategy.portfolio import Allocation, run_portfolio
from core.data.cache import get_data
from core.data.symbols import COMMON_SYMBOLS, COMMON_BARS, bars_per_year
from core.backtest.engine import run, BacktestConfig

st.title("🧩 策略组合")
st.caption("Ensemble 信号投票组合 · Portfolio 资金分配组合")
ensure_registry()
strategies = StrategyRegistry.all()
names_all = list(strategies.keys())
_disp = {n: strategies[n].display_name for n in names_all}

# ---------- 数据 ----------
c1, c2, c3 = st.columns([2, 1, 1])
symbol = c1.selectbox("品种", COMMON_SYMBOLS, key="cp_symbol")
bar = c2.selectbox("周期", COMMON_BARS, index=1, key="cp_bar")
days = c3.slider("天数", 60, 730, 365, 10, key="cp_days")
dkey = f"{symbol}_{bar}_{days}"
if get("cp_data_key") != dkey:
    try:
        set("cp_df", get_data(symbol, bar, days))
        set("cp_data_key", dkey)
    except Exception as e:
        st.error(f"拉取数据失败：{e}")
        st.stop()
df: pd.DataFrame = get("cp_df")
st.caption(f"{symbol} · {bar} · {len(df)} 根K线")

tabA, tabB = st.tabs(["🔗 Ensemble 信号组合", "💼 Portfolio 资金分配"])

# ---------- Ensemble ----------
with tabA:
    st.markdown("多个策略同时给信号，按规则合成**一个最终信号**，作为一个组合策略回测。")
    sel = st.multiselect("选择子策略（≥2）", names_all,
                         default=names_all[:2],
                         format_func=lambda n: _disp[n], key="cp_ens_sel")
    if len(sel) < 2:
        st.info("请至少选择 2 个策略")
    else:
        subs = []
        for n in sel:
            cls = strategies[n]
            with st.expander(f"{cls.display_name} 参数", expanded=False):
                p = render_params(cls, key_prefix="ens_")
            subs.append(cls(**p))

        mode_label = {"vote": "投票(净票数)", "majority": "多数过半",
                      "and": "全一致(AND)", "or": "任一(OR)", "weighted": "加权"}
        mode = st.selectbox("组合模式", Ensemble.MODES,
                            format_func=lambda m: mode_label[m], key="cp_ens_mode")
        weights = None
        if mode == "weighted":
            weights = {}
            wcols = st.columns(len(subs))
            for i, s in enumerate(subs):
                weights[s.name] = wcols[i].slider(_disp.get(s.name, s.name), 0.0, 5.0, 1.0, 0.1,
                                                  key=f"cp_ens_w_{s.name}")
        invert = st.toggle("🔄 反转信号（1↔-1）", value=False, key="cp_ens_invert",
                           help="反转组合信号方向，方向反了的亏损组合通常转盈。")
        if st.button("🚀 组合回测", key="cp_ens_run", type="primary"):
            ens = Ensemble(subs, mode, weights)
            sig = ens.generate_signals(df)
            cfg = BacktestConfig(bars_per_year=bars_per_year(bar))
            rep = run(sig, cfg,
                      strategy_name=ens.name + ("（反转）" if invert else ""),
                      invert=invert)
            set("cp_ens_report", rep)
            set("cp_ens_sig", sig)
            set("cp_ens_subs", [getattr(s, "name") for s in subs])
        rep = get("cp_ens_report")
        if rep:
            show_metrics(rep.metrics)
            st.plotly_chart(plot_equity(rep), width="stretch")
            st.plotly_chart(plot_drawdown(rep), width="stretch")
            st.caption("组合信号 vs 各子策略信号（末 20 根）：")
            sig = get("cp_ens_sig")
            comp = pd.DataFrame({"ts": sig["ts"], "组合": sig["signal"]})
            for n in get("cp_ens_subs", []):
                comp[_disp.get(n, n)] = strategies[n]().generate_signals(df)["signal"].values
            st.dataframe(comp.tail(20), hide_index=True)

# ---------- Portfolio ----------
with tabB:
    st.markdown("每个策略**独立运行、独立持仓**，按资金比例切分，合成组合权益曲线。")
    sel2 = st.multiselect("选择策略（≥2）", names_all,
                          default=names_all[:2],
                          format_func=lambda n: _disp[n], key="cp_pf_sel")
    if len(sel2) < 2:
        st.info("请至少选择 2 个策略")
    else:
        allocs = []
        for n in sel2:
            cls = strategies[n]
            cc = st.columns([1, 3])
            w = cc[0].slider("权重", 0.0, 5.0, 1.0, 0.1, key=f"cp_pf_w_{n}")
            with cc[1].expander(f"{cls.display_name} 参数", expanded=False):
                p = render_params(cls, key_prefix="pf_")
            allocs.append(Allocation(cls(**p), w))
        invert = st.toggle("🔄 反转信号（1↔-1）", value=False, key="cp_pf_invert",
                           help="反转各子策略信号方向。")
        if st.button("🚀 组合回测", key="cp_pf_run", type="primary"):
            cfg = BacktestConfig(bars_per_year=bars_per_year(bar))
            prep = run_portfolio(allocs, df, cfg, invert=invert)
            set("cp_pf_report", prep)
        prep = get("cp_pf_report")
        if prep:
            show_metrics(prep.metrics)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=prep.equity_curve["ts"], y=prep.equity_curve["equity"],
                name="组合(合成)", line=dict(width=2.5, color="#4dd0e1")))
            for name, w, r in prep.per_strategy:
                fig.add_trace(go.Scatter(
                    x=r.equity_curve["ts"], y=r.equity_curve["equity"],
                    name=f"{_disp.get(name, name)} ({w:.0%})", line=dict(width=1, dash="dot")))
            fig.add_hline(y=prep.initial_capital, line_dash="dash", line_color="gray")
            fig.update_layout(template="plotly_dark", height=450,
                              title="组合权益 vs 各子策略权益", margin=dict(l=40, r=20, t=40, b=20))
            st.plotly_chart(fig, width="stretch")
            rows = []
            for name, w, r in prep.per_strategy:
                rows.append({
                    "策略": _disp.get(name, name), "资金占比": f"{w:.0%}",
                    "总收益": f"{r.metrics['total_return']:.2%}",
                    "最大回撤": f"{r.metrics['max_drawdown']:.2%}",
                    "夏普": f"{r.metrics['sharpe']:.2f}"})
            st.dataframe(pd.DataFrame(rows), hide_index=True)

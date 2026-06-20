"""数据与回测页（核心）：选数据 → 选策略调参 → 一键回测 → 全套可视化。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.state import ensure_registry, get, set, coin_options
from app.components.param_controls import render_params
from app.components.metrics_card import show_metrics
from app.components.chart_kline import plot_kline
from app.components.chart_equity import (
    plot_equity, plot_drawdown, plot_monthly_heatmap, plot_returns_dist)
from core.strategy.registry import StrategyRegistry
from core.data.cache import get_data, clear_cache
from core.data.symbols import COMMON_SYMBOLS, COMMON_BARS, bars_per_year
from core.backtest.engine import run, BacktestConfig

st.title("📊 数据与回测")
st.caption("选品种 → 选策略调参 → 一键回测 → 全套可视化")
ensure_registry()
strategies = StrategyRegistry.all()

# ---------- 1. 数据 ----------
st.subheader("1️⃣ 数据")
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
symbol = c1.selectbox("品种（可搜索）", coin_options(), key="bt_symbol")
bar = c2.selectbox("周期", COMMON_BARS, index=1, key="bt_bar")
days = c3.slider("天数", 30, 730, 365, 10, key="bt_days")
refresh = c4.button("🔄 刷新")

data_key = f"{symbol}_{bar}_{days}"
if get("data_key") != data_key or refresh:
    try:
        if refresh:
            clear_cache(symbol, bar)
        df = get_data(symbol, bar, days)
        set("df", df)
        set("data_key", data_key)
    except Exception as e:
        st.error(f"拉取数据失败：{e}")
        st.stop()

df: pd.DataFrame = get("df")
if df is None or df.empty:
    st.warning("无数据，请检查品种/网络。")
    st.stop()
st.caption(f"{symbol} · {bar} · {len(df)} 根K线 · "
           f"{df['ts'].iloc[0].date()} → {df['ts'].iloc[-1].date()}")

# ---------- 2. 策略 ----------
st.subheader("2️⃣ 策略")
names = list(strategies.keys())
sname = st.selectbox(
    "选择策略", names,
    format_func=lambda n: f"{strategies[n].display_name}（{n}）",
    key="bt_strat")
strat_cls = strategies[sname]
st.caption(strat_cls.description)
with st.expander("策略参数", expanded=True):
    params = render_params(strat_cls)

# ---------- 3. 引擎参数 ----------
with st.expander("⚙️ 引擎参数（手续费 / 滑点 / 杠杆）", expanded=False):
    e1, e2, e3, e4 = st.columns(4)
    init = e1.number_input("初始资金", 1000, 1_000_000, 10000, 1000, key="bt_init")
    lev = e2.number_input("杠杆", 1, 125, 5, 1, key="bt_lev")
    ratio = e3.slider("仓位比例", 0.01, 1.0, 0.1, 0.01, key="bt_ratio")
    fee = e4.number_input("手续费率", 0.0, 0.01, 0.0005, 0.0001, format="%.4f", key="bt_fee")
    s1, s2 = st.columns(2)
    slip = s1.slider("滑点", 0.0, 0.01, 0.0005, 0.0001, key="bt_slip")
    side_mode = s2.radio("方向", ["long_short", "long_only"],
                         format_func=lambda x: "多空" if x == "long_short" else "仅做多",
                         horizontal=True, key="bt_side")

# ---------- 4. 回测 ----------
invert = st.toggle("🔄 反转信号（做多 ↔ 做空）", value=False, key="bt_invert",
                   help="开启后所有信号方向反转。方向判断反了的亏损策略通常会转为盈利"
                        "（手续费仍照付，对多空策略效果最佳）。")
if st.button("🚀 一键回测", type="primary"):
    with st.spinner("回测中…"):
        strat = strat_cls(**params)
        sig_df = strat.generate_signals(df)
        cfg = BacktestConfig(
            initial_capital=float(init), leverage=int(lev),
            position_ratio=float(ratio), fee_rate=float(fee),
            slippage=float(slip), side_mode=side_mode,
            bars_per_year=bars_per_year(bar))
        report = run(sig_df, cfg,
                     strategy_name=sname + ("（反转）" if invert else ""),
                     symbol=symbol, bar=bar, invert=invert)
        set("last_report", report)
        set("last_sig_df", sig_df)
    st.success("回测完成 ✔")

# ---------- 5. 结果 ----------
report = get("last_report")
if report is None:
    st.info("👈 选好参数后点「一键回测」查看结果")
    st.stop()

with st.container(border=True):
    st.markdown("### 📊 回测结果")
    show_metrics(report.metrics)

    sig_df: pd.DataFrame = get("last_sig_df")
    ohlcv = {"ts", "open", "high", "low", "close", "vol", "signal", "trade"}
    indicators = [c for c in sig_df.columns
                  if c not in ohlcv and pd.api.types.is_numeric_dtype(sig_df[c])]

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["🕯️ K线图", "📈 权益曲线", "📉 回撤", "🔥 月度热力图", "📊 收益分布", "📋 交易明细"])
    with tab1:
        st.plotly_chart(plot_kline(sig_df, report.trades, indicators), width="stretch")
    with tab2:
        st.plotly_chart(plot_equity(report), width="stretch")
    with tab3:
        st.plotly_chart(plot_drawdown(report), width="stretch")
    with tab4:
        st.plotly_chart(plot_monthly_heatmap(report), width="stretch")
    with tab5:
        st.plotly_chart(plot_returns_dist(report), width="stretch")
    with tab6:
        if report.trades.empty:
            st.write("无交易记录")
        else:
            st.dataframe(report.trades, use_container_width=True, hide_index=True)

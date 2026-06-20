"""指标卡片展示。"""
import streamlit as st


def _pf_str(pf: float) -> str:
    if pf == float("inf"):
        return "∞"
    return f"{pf:.2f}"


def show_metrics(metrics: dict):
    """分组展示核心指标：收益 / 风险 / 交易，收益带涨跌色。"""
    m = metrics
    pf_str = _pf_str(m.get("profit_factor", 0))

    st.markdown("#### 💰 收益表现")
    c1, c2, c3 = st.columns(3)
    c1.metric("总收益率", f"{m.get('total_return', 0):.2%}",
              delta=f"{m.get('total_return', 0):+.2%}")
    c2.metric("年化收益", f"{m.get('annual_return', 0):.2%}",
              delta=f"{m.get('annual_return', 0):+.2%}")
    c3.metric("最终资金", f"{m.get('final_capital', 0):,.0f}",
              delta=f"{m.get('total_return', 0):+.2%}")

    st.markdown("#### ⚖️ 风险调整")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最大回撤", f"{m.get('max_drawdown', 0):.2%}",
              delta=f"{m.get('max_drawdown', 0):+.2%}", delta_color="inverse")
    c2.metric("夏普比率", f"{m.get('sharpe', 0):.2f}")
    c3.metric("Sortino", f"{m.get('sortino', 0):.2f}")
    c4.metric("Calmar", f"{m.get('calmar', 0):.2f}")

    st.markdown("#### 📋 交易统计")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("胜率", f"{m.get('win_rate', 0):.2%}")
    c2.metric("盈亏比", pf_str)
    c3.metric("交易次数", f"{m.get('n_trades', 0)}")
    c4.metric("年化波动", f"{m.get('volatility', 0):.2%}")

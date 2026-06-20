"""实盘部署页：选账户/策略/品种/杠杆 → 一键启动后台 daemon；列出任务并启停。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.state import ensure_registry
from app.components.param_controls import render_params
from core.strategy.registry import StrategyRegistry
from core.live import runtime as R
from core.data.symbols import COMMON_SYMBOLS, COMMON_BARS

st.title("🚀 实盘部署")
st.caption("选择账户与策略，一键启动后台 trader（独立进程，关闭浏览器仍运行）。")
ensure_registry()
strategies = StrategyRegistry.all()
names_all = list(strategies.keys())

# ---------- 部署配置 ----------
st.subheader("部署配置")
c1, c2 = st.columns(2)
is_demo = c1.radio("账户类型", [True, False],
                   format_func=lambda x: "🟢 模拟盘" if x else "🔴 真实盘",
                   horizontal=True, key="dep_demo")
if not is_demo:
    c2.error("⚠️ 真实盘将使用真实资金交易！")

cc1, cc2, cc3 = st.columns(3)
symbol = cc1.selectbox("品种", COMMON_SYMBOLS, key="dep_symbol")
bar = cc2.selectbox("周期", COMMON_BARS, index=1, key="dep_bar")
interval = cc3.number_input("检查间隔(秒)", 60, 86400, 3600, 60, key="dep_interval")

dd1, dd2 = st.columns(2)
leverage = dd1.number_input("杠杆", 1, 125, 5, 1, key="dep_lev")
position_ratio = dd2.slider("仓位比例", 0.01, 1.0, 0.1, 0.01, key="dep_ratio")

sname = st.selectbox("策略", names_all,
                     format_func=lambda n: strategies[n].display_name, key="dep_strat")
cls = strategies[sname]
with st.expander("策略参数", expanded=False):
    params = render_params(cls, key_prefix="dep_")

if st.checkbox("预览最新信号（只读，不下单）", key="dep_preview"):
    try:
        from core.data.fetcher import fetch_recent
        sig_df = cls(**params).generate_signals(fetch_recent(symbol, bar, 200))
        last = sig_df.iloc[-1]
        txt = {1: "做多 🟢", -1: "做空 🔴", 0: "空仓 ⚪"}.get(int(last["signal"]), "?")
        st.info(f"最新收盘信号：{txt} ｜ 价格 {last['close']:.2f}")
    except Exception as e:
        st.error(f"预览失败：{e}")

invert = st.toggle("🔄 反转信号（实盘反开：做多 ↔ 做空）", value=False, key="dep_invert",
                   help="开启后实盘按反转信号下单（反手开仓）。方向反了的亏损策略可用此反开。")

confirm = True
if not is_demo:
    confirm = st.checkbox("我已知晓真实盘将使用真实资金，确认启动", key="dep_confirm")

if st.button("🚀 启动实盘", type="primary", disabled=not confirm):
    config = {
        "is_demo": is_demo, "symbol": symbol, "bar": bar,
        "strategy": {"type": "single", "name": sname, "params": params},
        "leverage": int(leverage), "position_ratio": float(position_ratio),
        "check_interval_sec": int(interval),
        "invert": invert,
    }
    try:
        jid = R.start_job(config)
        st.success(f"✔ 已启动实盘任务：{jid}（到「实盘监控」页查看）")
    except Exception as e:
        st.error(f"启动失败：{e}")

# ---------- 任务列表 ----------
st.divider()
st.subheader("实盘任务")
jobs = R.list_jobs()
if not jobs:
    st.info("暂无实盘任务")
else:
    for j in jobs:
        with st.container(border=True):
            m1, m2, m3, m4, m5 = st.columns([3, 1, 1, 1, 1])
            strat = j.get("strategy", {}).get("name", "-")
            m1.write(f"**{j['job_id']}** ｜ {j.get('symbol')} ｜ {strat} ｜ {j.get('bar')}")
            m2.write("模拟" if j.get("is_demo") else "**真实**")
            status = j.get("status")
            alive = j.get("alive")
            if status == "running" and not alive:
                m3.markdown("🟡 孤儿(已退出)")
            elif status == "running":
                m3.markdown("🟢 运行中")
            else:
                m3.markdown("⚪ 已停止")
            m4.write(f"杠杆 {j.get('leverage')} / {(j.get('position_ratio') or 0):.0%}")
            with m5:
                if status == "running":
                    if st.button("停止", key=f"stop_{j['job_id']}"):
                        R.stop_job(j["job_id"])
                        st.rerun()
                if st.button("删除", key=f"del_{j['job_id']}"):
                    R.delete_job(j["job_id"])
                    st.rerun()

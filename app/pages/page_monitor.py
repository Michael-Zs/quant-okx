"""实盘监控页：选择任务，轮询 state/日志，显示持仓/PnL/最近信号。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from core.live import runtime as R

st.title("📈 实盘监控")
jobs = R.list_jobs()
if not jobs:
    st.info("暂无实盘任务，请先在「实盘部署」页启动。")
    st.stop()

jid = st.selectbox("选择任务", [j["job_id"] for j in jobs],
                   format_func=lambda j: f"{j} ({'模拟' if next((x for x in jobs if x['job_id']==j), {}).get('is_demo') else '真实'})",
                   key="mon_jid")

cc1, cc2 = st.columns([1, 3])
auto = cc1.checkbox("自动刷新 (10s)", value=True, key="mon_auto")
if cc2.button("🔄 立即刷新"):
    st.rerun()
if auto:
    st_autorefresh(interval=10000, key="mon_refresh")

job = R.get_job(jid)
state = R.get_state(jid) or {}

status = job.get("status")
alive = job.get("alive")
if status == "running" and not alive:
    badge = "🟡 进程已退出（孤儿任务）"
elif status == "running":
    badge = "🟢 运行中"
else:
    badge = "⚪ 已停止"
st.markdown(f"### {badge}")
st.caption(f"策略：{job.get('strategy', {}).get('name', '-')} ｜ {job.get('symbol')} ｜ "
           f"{'模拟盘' if job.get('is_demo') else '真实盘'} ｜ 杠杆 {job.get('leverage')}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("账户余额", f"{state.get('balance', 0):,.2f} USDT")
sig = state.get("last_signal", 0)
c2.metric("最新信号", {1: "做多", -1: "做空", 0: "空仓"}.get(sig, "-"))
c3.metric("持仓方向",
          {1: "多头 🟢", -1: "空头 🔴", 0: "空仓 ⚪"}.get(state.get("position_dir", 0), "-"))
c4.metric("未实现盈亏", f"{state.get('unrealized_pnl', 0):,.2f}")

c5, c6, c7 = st.columns(3)
c5.metric("最新价", f"{state.get('last_price', 0):,.2f}")
c6.metric("持仓量", f"{state.get('position_contracts', 0):.4f}")
c7.metric("开仓价", f"{state.get('entry_price', 0):,.2f}")

if state.get("last_action"):
    st.info(f"最近操作：{state['last_action']} ｜ 更新于 {state.get('updated_at', '-')}"
            f"｜ 下次检查 {state.get('next_check_at', '-')}")
if state.get("error"):
    st.error(f"错误：{state['error']}")

st.divider()
st.subheader("事件日志")
logs = R.read_logs(jid, 30)
if logs:
    st.dataframe(pd.DataFrame(logs), hide_index=True, use_container_width=True)
else:
    st.write("暂无日志")

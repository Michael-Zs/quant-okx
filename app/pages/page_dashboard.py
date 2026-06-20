"""仪表盘：回测摘要、实盘状态、API 状态、策略列表、快捷入口。"""
import sys
import socket
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.state import get, ensure_registry
from core.strategy.registry import StrategyRegistry
from core.live import runtime as R
from core.utils.config import settings

st.title("📈 仪表盘")
st.caption("OKX 量化交易控制台 · 总览")
ensure_registry()


def _port_open(port: int) -> bool:
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


# ---- KPI ----
c1, c2, c3, c4 = st.columns(4)
report = get("last_report")
if report:
    c1.metric("最近回测收益", f"{report.metrics['total_return']:.2%}")
    c2.metric("夏普比率", f"{report.metrics['sharpe']:.2f}")
    c3.metric("最大回撤", f"{report.metrics['max_drawdown']:.2%}")
else:
    c1.metric("最近回测收益", "—")
    c2.metric("夏普比率", "—")
    c3.metric("最大回撤", "—")
jobs = R.list_jobs()
running = [j for j in jobs if j.get("status") == "running" and j.get("alive")]
c4.metric("运行中实盘", len(running))

api_ok = _port_open(settings.API_PORT)
st.markdown("**REST API**：" +
            (f"🟢 在线 — http://127.0.0.1:{settings.API_PORT}/docs" if api_ok else "🔴 离线"))

st.divider()

# ---- 实盘任务摘要 ----
st.subheader("实盘任务")
if jobs:
    for j in jobs[:5]:
        alive = j.get("status") == "running" and j.get("alive")
        st.write(f"- `{j['job_id']}` ｜ {j.get('symbol')} ｜ "
                 f"{j.get('strategy', {}).get('name', '-')} ｜ "
                 f"{'🟢 运行' if alive else '⚪ 停止'}")
else:
    st.info("暂无实盘任务。前往「实盘部署」启动。")

st.divider()

# ---- 快捷入口 ----
st.subheader("快捷入口")
st.markdown(
    "- 📊 **数据与回测**：选品种/策略，一键回测，全套可视化\n"
    "- 🧩 **策略组合**：Ensemble 信号组合 / Portfolio 资金分配\n"
    "- 🛠️ **策略实验室**：用 Python 写策略，保存即用；参数网格搜索\n"
    "- 🚀 **实盘部署**：模拟/真实盘，一键启动后台 trader\n"
    "- 📈 **实盘监控**：实时持仓 / PnL / 日志\n"
    "- ⚙️ **设置**：API key、缓存管理")

st.divider()

# ---- 策略列表 ----
st.subheader("已注册策略")
for s in StrategyRegistry.info():
    st.write(f"- **{s['display_name']}**（`{s['name']}`）：{s['description']}")

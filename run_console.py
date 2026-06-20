"""OKX 量化交易控制台入口。

启动：streamlit run run_console.py
"""
import sys
import socket
import subprocess
from pathlib import Path

# 确保项目根目录在 sys.path（页面脚本与 core/app 模块可 import）
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from core.utils.config import settings
from app.styles import inject_theme

st.set_page_config(
    page_title="OKX 量化交易控制台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()


def _port_open(port: int) -> bool:
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def _ensure_api():
    """若 API 端口未占用，则后台拉起 API 服务（实现一键启动控制台 + API）。"""
    if st.session_state.get("_api_started"):
        return
    if not _port_open(settings.API_PORT):
        try:
            subprocess.Popen(
                [sys.executable, str(settings.ROOT / "api_server.py")],
                start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    st.session_state["_api_started"] = True


_ensure_api()

pg = st.navigation([
    st.Page("app/pages/page_dashboard.py", title="仪表盘", icon="📈"),
    st.Page("app/pages/page_backtest.py", title="数据与回测", icon="📊"),
    st.Page("app/pages/page_compose.py", title="策略组合", icon="🧩"),
    st.Page("app/pages/page_multi.py", title="多币策略", icon="🌐"),
    st.Page("app/pages/page_lab.py", title="策略实验室", icon="🛠️"),
    st.Page("app/pages/page_deploy.py", title="实盘部署", icon="🚀"),
    st.Page("app/pages/page_monitor.py", title="实盘监控", icon="📉"),
    st.Page("app/pages/page_settings.py", title="设置", icon="⚙️"),
])

with st.sidebar:
    st.markdown("## 📈 OKX 量化控制台")
    st.caption("策略 · 回测 · 组合 · 多币 · 实盘 · API")
    st.divider()
    api_ok = _port_open(settings.API_PORT)
    status_color = "#34d399" if api_ok else "#f87171"
    st.markdown(
        f"**REST API**　<span style='color:{status_color};font-weight:600'>"
        f"{'● 在线' if api_ok else '● 离线'}</span>",
        unsafe_allow_html=True)
    if api_ok:
        st.caption(f"`http://127.0.0.1:{settings.API_PORT}/docs`")
    st.divider()
    st.caption("⚠️ 实盘有风险 · 策略代码拥有完整权限")

pg.run()

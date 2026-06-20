"""设置页：API key 编辑（写 .env）、默认参数、缓存管理。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from core.utils.config import settings
from core.data.cache import clear_cache


def update_env(key: str, value: str):
    """更新 .env 中某个键（不存在则追加）。"""
    path = settings.ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found = False
    for i, ln in enumerate(lines):
        if ln.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


st.title("⚙️ 设置")

# ---- API 密钥 ----
st.subheader("OKX API 密钥")
st.caption("存储于本地 .env（已 gitignore，不会提交）。修改后需重启控制台生效。")
st.write(f"当前状态：{'✅ 已配置' if settings.OKX_API_KEY else '❌ 未配置'}")
with st.form("key_form"):
    k1 = st.text_input("API Key", value=settings.OKX_API_KEY, type="password")
    k2 = st.text_input("API Secret", value=settings.OKX_API_SECRET, type="password")
    k3 = st.text_input("Passphrase", value=settings.OKX_API_PASSPHRASE, type="password")
    if st.form_submit_button("保存到 .env"):
        update_env("OKX_API_KEY", k1)
        update_env("OKX_API_SECRET", k2)
        update_env("OKX_API_PASSPHRASE", k3)
        st.success("已保存。请重启控制台使配置生效。")

# ---- REST API ----
st.subheader("REST API")
st.code(f"地址：http://{settings.API_HOST}:{settings.API_PORT}\n"
        f"Token：{settings.API_TOKEN}\n"
        f"文档：http://{settings.API_HOST}:{settings.API_PORT}/docs")
st.caption("控制类接口（回测/启停实盘/查余额）需在请求头带 X-API-Token。")

# ---- 默认参数 ----
st.subheader("默认交易参数（来自 .env）")
c1, c2 = st.columns(2)
c1.write(f"默认杠杆：{settings.DEFAULT_LEVERAGE}")
c1.write(f"默认仓位比例：{settings.DEFAULT_POSITION_RATIO}")
c2.write(f"默认手续费率：{settings.DEFAULT_FEE}")
c2.write(f"默认滑点：{settings.DEFAULT_SLIPPAGE}")

# ---- 缓存 ----
st.subheader("数据缓存")
cache_dir = settings.CACHE_DIR
files = list(cache_dir.glob("*.parquet")) if cache_dir.exists() else []
st.write(f"缓存目录：`{cache_dir}` ｜ 当前 {len(files)} 个文件")
if st.button("🗑️ 清空全部缓存", type="secondary"):
    n = clear_cache()
    st.success(f"已清空 {n} 个缓存文件")

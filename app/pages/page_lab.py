"""策略实验室：streamlit-ace 编辑策略 → 保存即注册 → 参数网格搜索。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json
import re
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_ace import st_ace

from app.state import ensure_registry, get, set
from core.strategy.registry import StrategyRegistry
from core.strategy.spec import STRATEGY_SPEC
from core.utils.config import settings
from core.data.cache import get_data
from core.data.symbols import COMMON_SYMBOLS, bars_per_year
from core.backtest.engine import BacktestConfig
from core.backtest.gridsearch import grid_search, arange_values

st.title("🛠️ 策略实验室")
st.caption("用 Python 写策略，保存即注册；参数网格搜索找最优组合。")
ensure_registry()
strategies = StrategyRegistry.all()
names_all = list(strategies.keys())


def copy_to_clipboard_button(text: str, label: str = "📋 一键复制到剪贴板", key: str = "cp"):
    """渲染一个复制按钮：优先 navigator.clipboard，失败回退 textarea + execCommand。"""
    payload = json.dumps(text)
    components.html(f'''
    <button id="btn_{key}" style="padding:0.5rem 1rem;background:linear-gradient(135deg,#22d3ee,#0891b2);color:#00121a;
        border:none;border-radius:8px;cursor:pointer;font-size:0.9rem;font-weight:600;">{label}</button>
    <span id="msg_{key}" style="margin-left:0.6rem;color:#4dd0e1;font-size:0.85rem;"></span>
    <script>
    (function() {{
      const btn = document.getElementById('btn_{key}');
      const msg = document.getElementById('msg_{key}');
      const text = {payload};
      btn.addEventListener('click', async () => {{
        let ok = false;
        try {{ await navigator.clipboard.writeText(text); ok = true; }}
        catch (e) {{
          try {{
            const ta = document.createElement('textarea');
            ta.value = text; ta.style.position='fixed'; ta.style.opacity='0';
            document.body.appendChild(ta); ta.select();
            ok = document.execCommand('copy'); document.body.removeChild(ta);
          }} catch (e2) {{ ok = false; }}
        }}
        msg.textContent = ok ? '✔ 已复制！可粘贴给 AI 写策略'
                             : '⚠ 自动复制受限，请用下方代码块右上角 📋 图标复制';
      }});
    }})();
    </script>
    ''', height=42)


TEMPLATE = '''"""自定义策略：{name}"""
import pandas as pd
from core.strategy.base import Strategy, Param


class {ClassName}(Strategy):
    name = "{name}"
    display_name = "{name}"
    description = "自定义策略"
    side_mode = "long_short"

    # 参数声明示例（UI 会自动生成控件）：
    # period = Param("period", 14, 2, 100, 1, label="周期")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        # TODO: 在此编写策略逻辑，输出 signal 列（1 做多 / -1 做空 / 0 空仓）
        df["signal"] = 0
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df
'''

tab_edit, tab_gs = st.tabs(["✏️ 策略编辑器", "🔬 参数网格搜索"])

# ---------- 编辑器 ----------
with tab_edit:
    with st.expander("🤖 AI 策略开发规范（复制给 AI，让它帮你写策略）", expanded=False):
        st.caption("把这份规范复制给 AI（Claude / ChatGPT 等），描述你的策略想法，"
                   "它就能按规范输出可直接保存使用的策略代码。")
        copy_to_clipboard_button(STRATEGY_SPEC, label="📋 一键复制完整规范到剪贴板", key="spec_copy")
        st.download_button("⬇️ 或下载为 strategy_spec.md", STRATEGY_SPEC,
                           file_name="strategy_spec.md", mime="text/markdown")
        st.caption("（若按钮无效，点下方代码块右上角 📋 图标也能复制）")
        st.code(STRATEGY_SPEC, language="markdown")

    with st.container(border=True):
        st.subheader("🧑‍💻 编辑策略代码")
        st.warning("策略代码拥有完整 Python 权限（与本程序相同），请仅在自己机器上运行可信代码。", icon="⚠️")
        name = st.text_input("策略名（英文标识符，作为文件名与 registry key）",
                             value="my_strategy", key="lab_name")
        initial = st.session_state.get("lab_code") or TEMPLATE.format(
            name=name, ClassName="".join(w.capitalize() for w in name.split("_")))
        code = st_ace(value=initial, language="python", theme="tomorrow_night_bright",
                      key="lab_ace", height=420, font_size=13, auto_update=False)
        st.session_state["lab_code"] = code

        c1, c2 = st.columns(2)
        if c1.button("💾 保存并注册", type="primary"):
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
                st.error("策略名必须是合法 Python 标识符（字母/数字/下划线，不以数字开头）")
            else:
                path = settings.STRATEGIES_DIR / f"{name}.py"
                path.write_text(code, encoding="utf-8")
                StrategyRegistry.discover_dir(settings.STRATEGIES_DIR, force_reload=True)
                set("_registry_loaded", True)
                if name in StrategyRegistry.names():
                    st.success(f"✔ 已保存并注册：{name}，可在「数据与回测」页直接使用。")
                else:
                    st.error("保存失败：代码可能有语法错误或未正确定义 Strategy 子类，请查看终端日志。")
        if c2.button("🗑️ 删除该策略文件"):
            path = settings.STRATEGIES_DIR / f"{name}.py"
            if path.exists():
                path.unlink()
                StrategyRegistry.discover_dir(settings.STRATEGIES_DIR, force_reload=True)
                set("_registry_loaded", True)
                st.success(f"已删除 {name}")
            else:
                st.info("文件不存在")

    with st.container(border=True):
        st.subheader("📚 已注册策略")
        st.caption("、".join(names_all) if names_all else "暂无策略")

# ---------- 网格搜索 ----------
with tab_gs:
    df = get("df")
    if df is None or df.empty:
        df = get_data(COMMON_SYMBOLS[0], "1H", days=180)
        set("df", df)
    st.caption(f"数据：{len(df)} 根K线（取自「数据与回测」页或默认加载）")

    gs_name = st.selectbox("策略", names_all, key="lab_gs_name")
    cls = strategies[gs_name]
    numeric = [p for p in cls.param_schema() if p.kind in ("slider", "number")]
    if not numeric:
        st.info("该策略无数值参数可搜索")
    else:
        param_grid = {}
        for p in numeric:
            st.markdown(f"**{p.label or p.name}**")
            cc = st.columns(3)
            lo = cc[0].number_input("起", value=float(p.default), key=f"gs_lo_{p.name}")
            hi = cc[1].number_input("止",
                                    value=float(p.max if p.max is not None else p.default * 2),
                                    key=f"gs_hi_{p.name}")
            stp = cc[2].number_input("步", value=float(p.step if p.step else 1),
                                     min_value=0.0, key=f"gs_st_{p.name}")
            param_grid[p.name] = arange_values(lo, hi, stp)
        total = 1
        for v in param_grid.values():
            total *= len(v)
        metric = st.selectbox("优化目标", ["total_return", "sharpe", "calmar", "sortino"],
                              key="lab_gs_metric")
        n_jobs = st.number_input("并行进程", 1, 8, 1, key="lab_gs_jobs")
        st.caption(f"将测试 **{total}** 个参数组合")
        if st.button("🔬 开始搜索", type="primary") and total > 0:
            with st.spinner(f"搜索 {total} 个组合…"):
                cfg = BacktestConfig(bars_per_year=bars_per_year("1H"))
                results = grid_search(cls, df, cfg, param_grid, metric=metric, n_jobs=int(n_jobs))
            set("lab_gs_results", results)
            set("lab_gs_keys", list(param_grid.keys()))
            set("lab_gs_metric", metric)

        results = get("lab_gs_results")
        if results:
            metric = get("lab_gs_metric", "total_return")
            with st.container(border=True):
                st.subheader(f"🏆 Top 结果（按 {metric} 降序）")
                st.dataframe(pd.DataFrame(results).head(20), hide_index=True)
                keys = get("lab_gs_keys", [])
                if len(keys) == 2 and len(results) > 1:
                    dr = pd.DataFrame(results)
                    pivot = dr.pivot_table(index=keys[0], columns=keys[1], values=metric)
                    fig = go.Figure(go.Heatmap(
                        z=pivot.values, x=pivot.columns, y=pivot.index,
                        colorscale="Viridis", colorbar_title=metric))
                    fig.update_layout(template="plotly_dark", height=420,
                                      title=f"{metric} 参数热力图", margin=dict(l=40, r=20, t=40, b=20))
                    st.plotly_chart(fig, width="stretch")

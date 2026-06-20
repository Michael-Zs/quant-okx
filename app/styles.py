"""全局 UI 主题：现代深色金融风格。集中管理 CSS，由 run_console 注入。

只影响外观（配色/卡片/圆角/间距），不涉及任何功能逻辑。
"""

THEME_CSS = """
<style>
:root {
  --bg: #0a0e17;
  --bg2: #0e1320;
  --card: rgba(255,255,255,0.035);
  --card-strong: rgba(255,255,255,0.06);
  --border: rgba(255,255,255,0.09);
  --accent: #22d3ee;
  --accent-2: #a78bfa;
  --up: #34d399;
  --down: #f87171;
  --text: #e6edf3;
  --dim: #8b97a7;
  --radius: 12px;
  --radius-sm: 8px;
}

/* 全局背景渐变 */
.stApp {
  background: linear-gradient(180deg, var(--bg) 0%, var(--bg2) 100%);
  background-attachment: fixed;
  color: var(--text);
}
.stApp, .stMarkdown, p, li {
  font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* 标题层级 */
h1 { font-weight: 700 !important; letter-spacing: -0.02em; }
h2, h3 { letter-spacing: -0.01em; }
.stApp h1, .stApp h2, .stApp h3 { color: var(--text); }

/* —— 指标卡片 —— */
[data-testid="stMetric"] {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px !important;
  transition: border-color .2s, background .2s;
}
[data-testid="stMetric"]:hover { border-color: rgba(34,211,238,.35); background: var(--card-strong); }
[data-testid="stMetricLabel"] > div { color: var(--dim) !important; font-size: .76rem !important;
    text-transform: uppercase; letter-spacing: .04em; }
[data-testid="stMetricValue"] { color: var(--text) !important; font-size: 1.45rem !important;
    font-weight: 600 !important; font-variant-numeric: tabular-nums; }

/* —— 按钮 —— */
button[kind="primary"], [data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, var(--accent), #0891b2) !important;
  border: none !important; border-radius: var(--radius-sm) !important;
  color: #00121a !important; font-weight: 600 !important;
  box-shadow: 0 2px 10px rgba(34,211,238,.22); transition: box-shadow .2s;
}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  box-shadow: 0 4px 16px rgba(34,211,238,.4);
}
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {
  background: var(--card) !important; border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important; color: var(--text) !important;
}

/* —— border 容器卡片 —— */
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stVerticalBlock"] > .st-emotion-cache-1oexxx3 {
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
}

/* —— Tabs —— */
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--border); }
[data-testid="stTabs"] [data-baseweb="tab"] {
  padding: 8px 16px; color: var(--dim); font-size: .92rem;
}
[data-testid="stTabs"] [aria-selected="true"] { color: var(--accent) !important; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--accent) !important; height: 3px; }

/* —— Expander —— */
[data-testid="stExpander"] {
  background: var(--card); border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important; overflow: hidden;
}
[data-testid="stExpander"] details summary { font-weight: 600; }

/* —— 代码块 —— */
[data-testid="stCodeBlock"] {
  border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden;
}

/* —— Sidebar —— */
section[data-testid="stSidebar"] {
  background: rgba(255,255,255,0.02);
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] h3 { color: var(--accent); }

/* —— 分隔线 / 表格 / 输入 / 提示 —— */
hr { border-color: var(--border) !important; }
[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
[data-testid="stAlert"] { border-radius: var(--radius-sm) !important; }
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
  border-radius: var(--radius-sm) !important;
}

/* 滚动条 */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,.2); }
::-webkit-scrollbar-track { background: transparent; }
</style>
"""


def inject_theme():
    """注入全局主题 CSS（在 run_console 顶部调用）。"""
    import streamlit as st
    st.markdown(THEME_CSS, unsafe_allow_html=True)

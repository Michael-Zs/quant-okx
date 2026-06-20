"""Plotly 图表统一主题：透明背景融入卡片，配色与全局深色主题协调。"""
import plotly.graph_objects as go

# 与 styles.py 一致的调色板
COLORS = ["#22d3ee", "#a78bfa", "#34d399", "#f87171", "#fbbf24", "#60a5fa", "#f472b6"]


def apply_theme(fig: go.Figure) -> go.Figure:
    """统一图表外观：透明背景、淡网格、协调字色与配色。返回同一 fig。"""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8b97a7"),
        title_font=dict(color="#e6edf3", size=14),
        colorway=COLORS,
        modebar=dict(bgcolor="rgba(0,0,0,0)", color="rgba(255,255,255,0.5)"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", linecolor="rgba(255,255,255,0.12)", zerolinecolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", linecolor="rgba(255,255,255,0.12)", zerolinecolor="rgba(255,255,255,0.08)")
    return fig

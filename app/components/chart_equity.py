"""权益曲线、回撤、月度热力图、收益分布（Plotly）。"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.plotly_theme import apply_theme
from core.backtest import metrics as M
from core.backtest.report import BacktestReport


def _ts(ec: pd.DataFrame):
    return pd.to_datetime(ec["ts"])


def plot_equity(report: BacktestReport, height: int = 400) -> go.Figure:
    ec = report.equity_curve
    init = report.config.get("initial_capital", 10000.0)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_ts(ec), y=ec["equity"], mode="lines", name="权益",
        line=dict(color="#4dd0e1", width=1.6), fill="tozeroy",
        fillcolor="rgba(77,208,225,0.08)"))
    fig.add_hline(y=init, line_dash="dash", line_color="gray",
                  annotation_text=f"初始 {init:,.0f}", annotation_position="top left")
    fig.update_layout(height=height, template="plotly_dark", title="权益曲线",
                      margin=dict(l=40, r=20, t=40, b=20))
    return apply_theme(fig)


def plot_drawdown(report: BacktestReport, height: int = 300) -> go.Figure:
    ec = report.equity_curve
    eq = pd.Series(ec["equity"].values)
    dd = M.drawdown_series(eq)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_ts(ec), y=(-dd * 100), mode="lines", name="回撤",
        line=dict(color="#ff5252", width=1), fill="tozeroy", fillcolor="rgba(255,82,82,0.3)"))
    fig.update_layout(height=height, template="plotly_dark", title="回撤曲线 (%)",
                      yaxis_title="%", margin=dict(l=40, r=20, t=40, b=20))
    return apply_theme(fig)


def plot_monthly_heatmap(report: BacktestReport, height: int = 360) -> go.Figure:
    ec = report.equity_curve.copy()
    ec["ts"] = pd.to_datetime(ec["ts"])
    monthly = ec.set_index("ts")["equity"].resample("ME").last().pct_change().dropna()
    if monthly.empty:
        fig = go.Figure()
        fig.update_layout(template="plotly_dark", title="月度收益热力图（数据不足）", height=height)
        return apply_theme(fig)
    frame = monthly.to_frame("ret")
    frame["year"] = frame.index.year
    frame["month"] = frame.index.month
    pivot = frame.pivot_table(index="year", columns="month", values="ret")
    month_names = [f"{m}月" for m in pivot.columns]
    text = [[f"{v*100:.1f}%" if pd.notna(v) else "" for v in row] for row in pivot.values]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=month_names, y=[str(y) for y in pivot.index],
        colorscale="RdYlGn", zmid=0, text=text, texttemplate="%{text}",
        colorbar_title="%"))
    fig.update_layout(height=height, template="plotly_dark", title="月度收益热力图",
                      yaxis=dict(autorange="reversed"), margin=dict(l=40, r=20, t=40, b=20))
    return apply_theme(fig)


def plot_returns_dist(report: BacktestReport, height: int = 300) -> go.Figure:
    rets = report.equity_curve["equity"].pct_change().dropna()
    fig = go.Figure(go.Histogram(x=rets * 100, nbinsx=60, marker_color="#5c6bc0"))
    fig.add_vline(x=0, line_color="gray", line_dash="dash")
    fig.update_layout(height=height, template="plotly_dark",
                      title="周期收益率分布 (%)", xaxis_title="%", margin=dict(l=40, r=20, t=40, b=20))
    return apply_theme(fig)

"""K 线主图：K线 + 成交量 + 指标叠加 + 买卖点标记（Plotly）。"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from app.plotly_theme import apply_theme


def plot_kline(df: pd.DataFrame, trades: pd.DataFrame | None = None,
               indicators: list[str] | None = None, height: int = 620) -> go.Figure:
    """df: OHLCV (+ 指标列)；trades: 交易表(含 side/price)；indicators: 要叠加的列名。"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.03,
                        column_widths=[1.0])

    fig.add_trace(go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K线", increasing_line_color="#26a69a", decreasing_line_color="#ef5350"),
        row=1, col=1)
    fig.add_trace(go.Bar(
        x=df["ts"], y=df["vol"], name="成交量",
        marker_color="rgba(100,149,237,0.35)", showlegend=False),
        row=2, col=1)

    for ind in (indicators or []):
        if ind in df.columns:
            fig.add_trace(go.Scatter(
                x=df["ts"], y=df[ind], mode="lines", name=ind,
                line=dict(width=1.2), opacity=0.9), row=1, col=1)

    if trades is not None and not trades.empty:
        _add_trade_markers(fig, trades)

    fig.update_layout(
        height=height, template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=40, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.0),
    )
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    return apply_theme(fig)


def _add_trade_markers(fig: go.Figure, trades: pd.DataFrame):
    buys = trades[trades["side"] == "long"]
    sells = trades[trades["side"] == "short"]
    closes = trades[trades["side"] == "close"]
    if not buys.empty:
        fig.add_trace(go.Scatter(
            x=buys["ts"], y=buys["price"], mode="markers", name="做多",
            marker=dict(symbol="triangle-up", size=13, color="#00e676", line=dict(width=1, color="black"))),
            row=1, col=1)
    if not sells.empty:
        fig.add_trace(go.Scatter(
            x=sells["ts"], y=sells["price"], mode="markers", name="做空",
            marker=dict(symbol="triangle-down", size=13, color="#ff5252", line=dict(width=1, color="black"))),
            row=1, col=1)
    if not closes.empty:
        fig.add_trace(go.Scatter(
            x=closes["ts"], y=closes["price"], mode="markers", name="平仓",
            marker=dict(symbol="x", size=9, color="#eeeeee")),
            row=1, col=1)

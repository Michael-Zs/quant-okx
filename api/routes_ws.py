"""WebSocket 路由：拖动参数/占比时的实时回测预览推送。

前端在组合页拖动滑块时，发送 node_spec + 行情参数，服务端回测后推送 metrics + equity。
（当前为「请求-响应」式；引擎可后续改为流式 yield 中间权益做逐 K 线进度。）
"""
import math
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.strategy.registry import StrategyRegistry
from core.strategy.node import node_from_spec, NodeContext
from core.data.cache import get_data
from core.data.symbols import bars_per_year
from core.backtest.engine import run_node, BacktestConfig

router = APIRouter()


def _clean(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and (math.isinf(v) or math.isnan(v)) else v)
            for k, v in d.items()}


@router.websocket("/ws/backtest")
async def ws_backtest(ws: WebSocket):
    """接收 {node_spec, symbol/symbols, bar, days, 引擎参数}，回测并推送结果。"""
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            try:
                StrategyRegistry.discover_all()
                node = node_from_spec(msg["node_spec"])
                bar = msg.get("bar", "1H")
                symbols = msg.get("symbols") or [msg.get("symbol", "BTC-USDT-SWAP")]
                data = {sym: get_data(sym, bar, msg.get("days", 180)) for sym in symbols}
                ctx = NodeContext(data=data, primary_symbol=symbols[0], bar=bar)
                cfg = BacktestConfig(initial_capital=msg.get("initial_capital", 10000.0),
                                     leverage=msg.get("leverage", 5),
                                     position_ratio=msg.get("position_ratio", 0.1),
                                     bars_per_year=bars_per_year(bar))
                outcome = run_node(node, ctx, cfg)
                eq = outcome.equity_curve.copy()
                if "ts" in eq.columns:
                    eq["ts"] = eq["ts"].astype(str)   # Timestamp → str，可 JSON 序列化
                await ws.send_json({
                    "metrics": _clean(outcome.metrics),
                    "equity": eq.to_dict("list"),
                    "report_kind": outcome.report_kind,
                    "n_trades": len(outcome.trades),
                })
            except Exception as e:
                await ws.send_json({"error": str(e)})
    except WebSocketDisconnect:
        return

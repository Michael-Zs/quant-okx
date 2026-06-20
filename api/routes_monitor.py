"""监控类路由（GET）：行情/策略/任务/状态/回测结果。"""
import math
from fastapi import APIRouter, Depends, HTTPException

from core.strategy.registry import StrategyRegistry
from core.data.cache import get_data
from core.live import runtime as R
from api import verify_token, _last_bt

router = APIRouter(prefix="/api")


def _ensure_registry():
    StrategyRegistry.discover_all()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/strategies")
def strategies():
    _ensure_registry()
    return {"strategies": StrategyRegistry.info(), "count": len(StrategyRegistry.names())}


@router.get("/market/{symbol}")
def market(symbol: str, bar: str = "1H", days: int = 7):
    try:
        df = get_data(symbol, bar, days)
        return {
            "symbol": symbol, "bar": bar, "count": len(df),
            "first": {"ts": str(df["ts"].iloc[0]), "close": float(df["close"].iloc[0])},
            "last": {"ts": str(df["ts"].iloc[-1]), "close": float(df["close"].iloc[-1])},
        }
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/balance", dependencies=[Depends(verify_token)])
def balance(is_demo: bool = True):
    from core.live.exchange import get_exchange, get_balance
    try:
        ex = get_exchange(is_demo)
        return {"balance": get_balance(ex), "is_demo": is_demo}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/positions", dependencies=[Depends(verify_token)])
def positions(is_demo: bool = True, symbol: str = "BTC-USDT-SWAP"):
    from core.live.exchange import get_exchange, get_position
    from core.data.symbols import okx_to_ccxt
    try:
        ex = get_exchange(is_demo)
        pos = get_position(ex, okx_to_ccxt(symbol))
        return {"symbol": symbol, "is_demo": is_demo, "position": pos}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/jobs")
def jobs():
    return {"jobs": R.list_jobs()}


@router.get("/jobs/{job_id}/state")
def job_state(job_id: str):
    return R.get_state(job_id) or {}


@router.get("/backtest/results")
def backtest_results():
    return _last_bt or {"detail": "尚无回测结果（请先 POST /api/backtest）"}


def _clean(d: dict) -> dict:
    """把 inf/NaN 转为 None，保证 JSON 可序列化。"""
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            out[k] = None
        else:
            out[k] = v
    return out

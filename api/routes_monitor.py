"""监控类路由（GET）：行情/模板/部署/回测历史/账户。"""
import math
from fastapi import APIRouter, Depends, HTTPException

from core.strategy.registry import StrategyRegistry
from core.data.cache import get_data
from core.persist import repositories as R
from core.persist.db import init_db
from core.live import runtime as Rt
from api import verify_token

router = APIRouter(prefix="/api")


def _ensure():
    StrategyRegistry.discover_all()
    init_db()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/templates")
def templates():
    """策略模板列表（registry.info，含单/多币与参数 schema）。"""
    _ensure()
    return {"templates": StrategyRegistry.info(), "count": len(StrategyRegistry.names())}


@router.get("/instruments")
def instruments():
    """可用 USDT 永续合约列表（带 1 天缓存，供前端搜索选择）。拉取失败回退常用列表。"""
    from core.data.fetcher import list_swap_instruments
    from core.data.symbols import COMMON_SYMBOLS
    try:
        return {"instruments": list_swap_instruments("USDT")}
    except Exception as e:
        return {"instruments": COMMON_SYMBOLS, "fallback": True, "error": str(e)}


@router.get("/market/{symbol}")
def market(symbol: str, bar: str = "1H", days: int = 7):
    try:
        df = get_data(symbol, bar, days)
        return {"symbol": symbol, "bar": bar, "count": len(df),
                "first": {"ts": str(df["ts"].iloc[0]), "close": float(df["close"].iloc[0])},
                "last": {"ts": str(df["ts"].iloc[-1]), "close": float(df["close"].iloc[-1])}}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/balance", dependencies=[Depends(verify_token)])
def balance(is_demo: bool = True):
    from core.live.exchange import get_exchange, get_balance
    try:
        return {"balance": get_balance(get_exchange(is_demo)), "is_demo": is_demo}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/positions", dependencies=[Depends(verify_token)])
def positions(is_demo: bool = True, symbol: str = "BTC-USDT-SWAP"):
    from core.live.exchange import get_exchange, get_position
    from core.data.symbols import okx_to_ccxt
    try:
        return {"symbol": symbol, "is_demo": is_demo,
                "position": get_position(get_exchange(is_demo), okx_to_ccxt(symbol))}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/deployments")
def deployments():
    """列出部署（DB 配置 + 运行期 alive 状态）。"""
    init_db()
    out = []
    for d in R.list_deployments():
        job = Rt.get_job(d["id"])
        d["alive"] = (Rt.is_process_alive(job.get("pid"))
                      if job.get("status") == "running" else False)
        out.append(d)
    return {"deployments": out}


@router.get("/deployments/{did}/state")
def deployment_state(did: str):
    return Rt.get_state(did) or {}


@router.get("/deployments/{did}/logs")
def deployment_logs(did: str, n: int = 50):
    return {"logs": Rt.read_logs(did, n)}


@router.get("/backtests")
def backtests(ref_id: str | None = None, node_kind: str | None = None, limit: int = 50):
    init_db()
    return {"backtests": R.list_backtests(ref_id=ref_id, node_kind=node_kind, limit=limit)}


@router.get("/backtests/{bid}")
def backtest_detail(bid: str, with_equity: bool = True):
    init_db()
    bt = R.get_backtest(bid, with_equity=with_equity)
    if not bt:
        raise HTTPException(404, f"未知回测: {bid}")
    return bt


# ---- 旧 job 兼容（保留过渡） ----
@router.get("/jobs")
def jobs_legacy():
    return {"jobs": Rt.list_jobs()}


@router.get("/jobs/{job_id}/state")
def job_state_legacy(job_id: str):
    return Rt.get_state(job_id) or {}


def _clean(d: dict) -> dict:
    """把 inf/NaN 转为 None，保证 JSON 可序列化。"""
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            out[k] = None
        else:
            out[k] = v
    return out

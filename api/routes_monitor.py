"""监控类路由（GET）：行情/模板/部署/回测历史/账户。"""
from __future__ import annotations
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from core.strategy.registry import StrategyRegistry
from core.data.cache import get_data
from core.persist import repositories as R
from core.persist.db import init_db
from core.live import runtime as Rt
from api import verify_token
from api.response_sampling import sample_curve, summarize_equity

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


@router.get("/strategy_spec")
def strategy_spec(kind: str = "single"):
    """AI 策略开发规范文本（单币/多币），供前端「复制给 AI 写策略」用。

    kind=single → STRATEGY_SPEC；kind=multi → MULTI_STRATEGY_SPEC。
    """
    from core.strategy.spec import STRATEGY_SPEC, MULTI_STRATEGY_SPEC
    k = (kind or "").strip().lower()
    if k == "multi":
        return {"kind": "multi", "spec": MULTI_STRATEGY_SPEC, "filename": "multi_strategy_spec.md"}
    return {"kind": "single", "spec": STRATEGY_SPEC, "filename": "strategy_spec.md"}


@router.get("/api_spec")
def api_spec():
    """REST API 使用规范文本，供前端「设置」页复制给 Agent / 外部脚本用。"""
    from api.spec import API_SPEC
    return {"spec": API_SPEC, "filename": "api_spec.md"}


@router.get("/user_strategies")
def user_strategies():
    """列出 strategies/ 下用户 .py 文件（策略实验室保存的代码）。"""
    from core.utils.config import settings
    import re
    out = []
    if settings.STRATEGIES_DIR.exists():
        for py in sorted(settings.STRATEGIES_DIR.glob("*.py")):
            if py.name.startswith("_") or py.stem.endswith("example"):
                continue
            try:
                code = py.read_text(encoding="utf-8")
            except Exception as e:
                code = f"# 读取失败: {e}"
            out.append({"name": py.stem, "filename": py.name, "code": code,
                        "mtime": int(py.stat().st_mtime)})
    return {"files": out, "count": len(out)}


@router.get("/config")
def get_config():
    """设置页用：脱敏返回当前配置（OKX 是否配置、API 地址、默认参数、缓存信息）。"""
    from core.utils.config import settings
    from core.data.cache import cache_stats
    cache = cache_stats()
    return {
        "okx_configured": bool(settings.OKX_API_KEY and settings.OKX_API_SECRET
                                and settings.OKX_API_PASSPHRASE),
        "api_host": settings.API_HOST,
        "api_port": settings.API_PORT,
        "api_token_set": settings.API_TOKEN != "change_me",
        "defaults": {
            "leverage": settings.DEFAULT_LEVERAGE,
            "position_ratio": settings.DEFAULT_POSITION_RATIO,
            "fee": settings.DEFAULT_FEE,
            "slippage": settings.DEFAULT_SLIPPAGE,
        },
        "cache": cache,
        "strategies_dir": str(settings.STRATEGIES_DIR),
    }


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
    """返回账户余额。balance=可用余额(free)，equity=总权益(free+used+upnl)。"""
    from core.live.exchange import get_exchange, get_balance, get_equity
    try:
        ex = get_exchange(is_demo)
        return {"balance": get_balance(ex), "equity": get_equity(ex), "is_demo": is_demo}
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


@router.get("/executor/state")
def executor_state():
    """Executor 进程状态（聚合对账结果）。"""
    return Rt.get_state("executor") or {}


@router.get("/backtests")
def backtests(ref_id: Optional[str] = None, node_kind: Optional[str] = None, limit: int = 50):
    init_db()
    return {"backtests": R.list_backtests(ref_id=ref_id, node_kind=node_kind, limit=limit)}


@router.get("/backtests/{bid}")
def backtest_detail(bid: str, with_equity: bool = True, max_points: Optional[int] = 300):
    init_db()
    bt = R.get_backtest(bid, with_equity=with_equity)
    if not bt:
        raise HTTPException(404, f"未知回测: {bid}")
    if with_equity and bt.get("equity"):
        import pandas as pd
        eq = pd.DataFrame(bt["equity"])
        bt["key_points"] = summarize_equity(eq)
        bt["equity"] = sample_curve(eq, "equity", max_points)
        # 旧文件无 benchmark 列时不返回；新回测会带上该列，供前端叠加绘制。
        if "benchmark" in eq.columns:
            bt["benchmark"] = sample_curve(eq, "benchmark", max_points)
    return bt


# ---- 旧 job 兼容（保留过渡） ----
@router.get("/jobs")
def jobs_legacy():
    return {"jobs": Rt.list_jobs()}


@router.get("/jobs/{job_id}/state")
def job_state_legacy(job_id: str):
    return Rt.get_state(job_id) or {}


def _clean(d: dict) -> dict:
    """把 inf/NaN 转为 None，保证 JSON 可序列化。递归处理嵌套 dict（如 metrics.benchmark）。"""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _clean(v)
        elif isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            out[k] = None
        else:
            out[k] = v
    return out

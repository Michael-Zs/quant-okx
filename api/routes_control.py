"""控制类路由（POST/DELETE）：触发回测、启停实盘。全部需 token。"""
from fastapi import APIRouter, Depends, HTTPException

from core.strategy.registry import StrategyRegistry
from core.data.cache import get_data
from core.data.symbols import bars_per_year
from core.backtest.engine import run, BacktestConfig
from core.live import runtime as R
from api import verify_token, _last_bt
from api.schemas import BacktestRequest, StartJobRequest
from api.routes_monitor import _clean

router = APIRouter(prefix="/api", dependencies=[Depends(verify_token)])


@router.post("/backtest")
def backtest(req: BacktestRequest):
    StrategyRegistry.discover_all()
    try:
        df = get_data(req.symbol, req.bar, req.days)
        if req.is_ensemble:
            from core.strategy.ensemble import Ensemble
            subs = [StrategyRegistry.get(s["name"])(**s.get("params", {})) for s in req.ensemble_subs]
            strat = Ensemble(subs, req.ensemble_mode, req.ensemble_weights)
            name = f"ensemble_{req.ensemble_mode}"
        else:
            strat = StrategyRegistry.get(req.strategy)(**req.params)
            name = req.strategy
        sig = strat.generate_signals(df)
        cfg = BacktestConfig(
            initial_capital=req.initial_capital, leverage=req.leverage,
            position_ratio=req.position_ratio, fee_rate=req.fee_rate,
            slippage=req.slippage, bars_per_year=bars_per_year(req.bar))
        rep = run(sig, cfg, strategy_name=name, symbol=req.symbol, bar=req.bar)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

    result = {
        "strategy": name, "symbol": req.symbol, "bar": req.bar, "days": req.days,
        "metrics": _clean(rep.metrics),
        "equity_start": float(rep.equity_curve["equity"].iloc[0]),
        "equity_end": float(rep.equity_curve["equity"].iloc[-1]),
        "n_trades": len(rep.trades),
    }
    _last_bt.clear()
    _last_bt.update(result)
    return result


@router.post("/jobs")
def start_job(req: StartJobRequest):
    config = {
        "is_demo": req.is_demo, "symbol": req.symbol, "bar": req.bar,
        "strategy": {"type": "single", "name": req.strategy, "params": req.params},
        "leverage": req.leverage, "position_ratio": req.position_ratio,
        "check_interval_sec": req.check_interval_sec,
    }
    try:
        jid = R.start_job(config)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"job_id": jid, "status": "running", "config": config}


@router.delete("/jobs/{job_id}")
def stop_job(job_id: str):
    ok = R.stop_job(job_id)
    return {"job_id": job_id, "stopped": ok}

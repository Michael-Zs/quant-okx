"""API 请求模型。"""
from pydantic import BaseModel


class BacktestRequest(BaseModel):
    strategy: str
    params: dict = {}
    symbol: str = "BTC-USDT-SWAP"
    bar: str = "1H"
    days: int = 180
    # Ensemble 可选
    is_ensemble: bool = False
    ensemble_subs: list[dict] = []      # [{"name":..,"params":{..}}, ...]
    ensemble_mode: str = "vote"
    ensemble_weights: dict = {}
    # 引擎参数
    initial_capital: float = 10000.0
    leverage: int = 5
    position_ratio: float = 0.1
    fee_rate: float = 0.0005
    slippage: float = 0.0005


class StartJobRequest(BaseModel):
    is_demo: bool = True
    symbol: str = "BTC-USDT-SWAP"
    bar: str = "1H"
    strategy: str
    params: dict = {}
    leverage: int = 5
    position_ratio: float = 0.1
    check_interval_sec: int = 3600

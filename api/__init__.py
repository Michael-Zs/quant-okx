"""API 公共：token 鉴权依赖 + 共享状态。"""
from fastapi import Header, HTTPException

from core.utils.config import settings

# 最近一次回测结果缓存（供 GET /api/backtest/results 读取）
_last_bt: dict = {}


async def verify_token(x_api_token: str = Header(None, alias="X-API-Token")):
    """校验 X-API-Token 请求头。"""
    if x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=401, detail="无效或缺失 X-API-Token")

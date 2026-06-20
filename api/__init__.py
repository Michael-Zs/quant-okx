"""API 公共：token 鉴权依赖。

（旧的进程内 _last_bt 回测缓存已移除——它跨进程不可见、语义有误导；
回测结果现落 backtests 表，由 GET /api/backtests/{id} 读取。）
"""
from fastapi import Header, HTTPException

from core.utils.config import settings


async def verify_token(x_api_token: str = Header(None, alias="X-API-Token")):
    """校验 X-API-Token 请求头。"""
    if x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=401, detail="无效或缺失 X-API-Token")

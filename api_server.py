"""REST API 服务入口（FastAPI），绑 127.0.0.1，控制类接口需 X-API-Token。

启动：python api_server.py   （或 uvicorn api_server:app）
文档：http://127.0.0.1:8787/docs
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from core.utils.config import settings
from api.routes_monitor import router as monitor_router
from api.routes_control import router as control_router

app = FastAPI(title="OKX 量化交易控制台 API", version="1.0")

app.include_router(monitor_router)
app.include_router(control_router)


@app.get("/")
def root():
    return {"service": "OKX 量化控制台 API", "docs": "/docs", "health": "/api/health"}


if __name__ == "__main__":
    import uvicorn
    print(f"API 启动于 http://{settings.API_HOST}:{settings.API_PORT}  （token: {settings.API_TOKEN}）")
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)

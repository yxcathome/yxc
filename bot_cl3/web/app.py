from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from typing import Dict, List
import logging
from datetime import datetime
import asyncio

from .routes import strategy, config, monitor
from core.bot import ArbitrageTrendBot

logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Bot Dashboard")

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# 全局bot实例
bot = None

@app.on_event("startup")
async def startup_event():
    """启动时初始化bot"""
    global bot
    try:
        bot = ArbitrageTrendBot()
        # 启动bot的主循环（在后台运行）
        asyncio.create_task(bot.run())
    except Exception as e:
        logger.error(f"Bot初始化失败: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    global bot
    if bot:
        await bot.shutdown()

# 注册路由
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])

@app.get("/")
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bot_status": "running" if bot and bot.is_running else "stopped"
        }
    )

@app.get("/health")
async def health_check():
    """健康检查"""
    if not bot or not bot.is_running:
        raise HTTPException(status_code=503, detail="Bot not running")
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"全局异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )
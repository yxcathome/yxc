import asyncio
import uvicorn
from api.app import app
from models.database import Database
from models.settings import Settings
from utils.logger import setup_logger

async def init_app():
    # 初始化日志
    logger = setup_logger("main")
    logger.info("正在启动量化交易系统...")
    
    # 初始化数据库
    db = Database()
    await db.connect()
    logger.info("数据库连接成功")
    
    # 加载系统设置
    settings = Settings()
    await settings.load()
    logger.info("系统设置加载成功")
    
    return app

if __name__ == "__main__":
    # 启动FastAPI应用
    uvicorn.run(
        "main:init_app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
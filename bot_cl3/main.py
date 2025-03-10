import os
import signal
import asyncio
import logging
from datetime import datetime
from decimal import getcontext
from core.bot import ArbitrageTrendBot
from web.app import app
import uvicorn
from config.settings import CONFIG
from utils.logger import setup_logger
from dotenv import load_dotenv
load_dotenv() 
# 设置decimal精度
getcontext().prec = 10

# 设置日志
logger = setup_logger()

# 全局bot实例
bot = None

async def start_bot():
    """启动交易机器人"""
    global bot
    try:
        bot = ArbitrageTrendBot()
        
        # 设置关闭信号处理
        def signal_handler():
            logger.info("收到关闭信号")
            asyncio.create_task(shutdown())
            
        # 注册信号处理器
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
            
        # 运行机器人
        await bot.run()
        
    except Exception as e:
        logger.error(f"Bot启动异常: {e}")
        raise

async def shutdown():
    """关闭程序"""
    global bot
    logger.info("开始关闭程序...")
    
    if bot:
        await bot.shutdown()
        bot = None
        
    logger.info("程序已关闭")

async def main():
    """主函数"""
    try:
        # 验证环境变量
        required_vars = [
            'OKX_API_KEY', 'OKX_SECRET', 'OKX_PASSWORD',
            'BINANCE_API_KEY', 'BINANCE_SECRET'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise RuntimeError(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        
        # 启动Web服务器
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        # 启动bot和web服务器
        await asyncio.gather(
            start_bot(),
            server.serve()
        )
        
    except Exception as e:
        logger.error(f"程序运行异常: {e}")
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
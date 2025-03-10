import asyncio
import signal
import uvicorn
import logging
from core.bot import ArbitrageTrendBot
from web.app import app
from utils.logger import setup_logger

logger = setup_logger()
bot = ArbitrageTrendBot()

async def shutdown():
    """关闭程序，确保各任务正确退出"""
    logger.info("收到停止信号，开始关闭程序...")
    await bot.shutdown()

async def start_bot():
    """启动交易机器人"""
    try:
        await bot.run()
    except Exception as e:
        logger.error(f"Bot 启动异常：{e}", exc_info=True)

async def start_web():
    """启动 Web 服务器"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """主函数：并行启动交易机器人和 Web 服务器，同时设置退出信号监听"""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    try:
        await asyncio.gather(
            start_bot(),
            start_web()
        )
    except Exception as e:
        logger.error(f"程序运行异常：{e}", exc_info=True)
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出：{e}", exc_info=True)
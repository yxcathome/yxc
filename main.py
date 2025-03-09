import asyncio
import signal
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from bot_core import ArbitrageBot
from strategies import ArbitrageStrategy
from web_server import run_web_server

async def main():
    bot = ArbitrageBot()
    strategy = ArbitrageStrategy(bot)

    def signal_handler(signum, frame):
        logger.info("收到终止信号")
        asyncio.create_task(bot.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await asyncio.gather(
            bot.okx_tools.exchange.load_markets(),
            bot.binance_tools.exchange.load_markets()
        )
        await bot.load_common_pairs()
        if not bot.common_pairs:
            raise RuntimeError("无有效交易对")
        
        await asyncio.gather(
            strategy.find_best_arbitrage_opportunity(),
            bot.run_web_server(),
            bot.update_funding_fees()
        )
    except Exception as e:
        logger.error(f"致命错误: {str(e)}", exc_info=True)
    finally:
        await asyncio.sleep(0.5)
        logger.info("系统关闭完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except asyncio.exceptions.CancelledError:
        logger.info("收到键盘中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"运行时错误: {str(e)}")
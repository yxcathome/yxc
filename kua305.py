# arbitrage_bot_full.py
import os
import ccxt.async_support as ccxt
import asyncio
import logging
from datetime import datetime
from aiohttp import web
from tenacity import retry, stop_after_attempt, wait_exponential

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("arbitrage.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ArbitrageBot:
    def __init__(self):
        # 初始化交易所
        self.okx = self.init_okx()
        self.binance = self.init_binance()
        
        # 交易参数
        self.min_trade = float(os.getenv('MIN_TRADE', 3.0))
        self.max_trade = float(os.getenv('MAX_TRADE', 5.0))
        self.max_daily_loss = float(os.getenv('MAX_DAILY_LOSS', 0.05))
        
        # 状态管理
        self.is_running = True
        self.start_time = datetime.now()
        self.total_profit = 0.0
        self.daily_profit = 0.0
        self.active_orders = {}
        
        # Web服务器
        self.web_port = 5000
        self.app = web.Application()
        self.setup_routes()

    def init_okx(self):
        return ccxt.okx({
            'apiKey': os.getenv('OKX_API_KEY'),
            'secret': os.getenv('OKX_SECRET'),
            'password': os.getenv('OKX_PASSWORD'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

    def init_binance(self):
        return ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })

    def setup_routes(self):
        self.app.add_routes([
            web.get('/', self.handle_index),
            web.get('/data', self.handle_data),
            web.get('/ws', self.handle_websocket)
        ])

    async def handle_index(self, request):
        return web.FileResponse('./monitor.html')

    async def handle_data(self, request):
        return web.json_response({
            'total_profit': round(self.total_profit, 2),
            'daily_profit': round(self.daily_profit, 2),
            'active_orders': len(self.active_orders),
            'status': 'RUNNING' if self.is_running else 'STOPPED'
        })

    async def handle_websocket(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await ws.send_json(await self.get_realtime_data())
        return ws

    async def get_realtime_data(self):
        return {
            'timestamp': datetime.now().isoformat(),
            'okx_balance': await self.get_balance(self.okx),
            'binance_balance': await self.get_balance(self.binance)
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def safe_api_call(self, func, *args, **kwargs):  # 修复参数列表中的零宽空格
        try:
            return await func(*args, **kwargs)  # 修复调用时的零宽空格
        except ccxt.NetworkError as e:
            logger.warning(f"Network error: {str(e)}")
            raise
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error: {str(e)}")
            return None

    async def get_balance(self, exchange):
        balance = await self.safe_api_call(exchange.fetch_balance)
        return balance['USDT']['free'] if balance else 0.0

    async def risk_management(self):
        if (datetime.now() - self.start_time).days >= 1:
            self.daily_profit = 0.0
            self.start_time = datetime.now()

        if self.daily_profit < -abs(self.max_daily_loss):
            logger.error("Daily loss limit triggered!")
            await self.shutdown()

    async def execute_arbitrage(self, symbol):
        try:
            # 获取订单簿数据
            okx_symbol = f"{symbol}/USDT:USDT"
            binance_symbol = f"{symbol}USDT"
            
            okx_book = await self.safe_api_call(self.okx.fetch_order_book, okx_symbol)
            binance_book = await self.safe_api_call(self.binance.fetch_order_book, binance_symbol)
            
            if not okx_book or not binance_book:
                return

            # 计算价差
            okx_ask = okx_book['asks'][0][0]
            binance_bid = binance_book['bids'][0][0]
            spread = (binance_bid - okx_ask) / okx_ask

            if spread > 0.0015:
                # 计算交易量
                trade_size = min(
                    self.max_trade / okx_ask,
                    okx_book['asks'][0][1] * 0.8,
                    binance_book['bids'][0][1] * 0.8
                )
                
                # 执行交易
                buy_order = await self.place_order(self.okx, okx_symbol, 'buy', trade_size, okx_ask)
                sell_order = await self.place_order(self.binance, binance_symbol, 'sell', trade_size, binance_bid)
                
                if buy_order and sell_order:
                    profit = (sell_order['filled'] * sell_order['price']) - (buy_order['filled'] * buy_order['price'])
                    self.total_profit += profit
                    self.daily_profit += profit
                    logger.info(f"Arbitrage success! Profit: {profit:.2f} USDT")

        except Exception as e:
            logger.error(f"Arbitrage failed: {str(e)}")

    async def place_order(self, exchange, symbol, side, amount, price):
        try:
            params = {'posSide': 'long'} if exchange.id == 'okx' and side == 'buy' else {}
            order = await self.safe_api_call(
                exchange.create_order,
                symbol=symbol,
                type='limit',
                side=side,
                amount=amount,
                price=price,
                params=params
            )
            if order:
                self.active_orders[order['id']] = order
            return order
        except Exception as e:
            logger.error(f"Order failed: {str(e)}")
            return None

    async def monitor_orders(self):
        while self.is_running:
            for order_id in list(self.active_orders.keys()):
                order = self.active_orders[order_id]
                updated = await self.safe_api_call(
                    self.okx.fetch_order if order_id.startswith('OKX') else self.binance.fetch_order,
                    order_id,
                    order['symbol']
                )
                if updated and updated['status'] == 'closed':
                    del self.active_orders[order_id]
            await asyncio.sleep(5)

    async def shutdown(self):
        self.is_running = False
        await self.okx.close()
        await self.binance.close()
        logger.info("System shutdown complete")

    async def run(self):
        """主运行入口"""
        # 启动Web服务器
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.web_port)
        await site.start()
        logger.info(f"Web interface: http://localhost:{self.web_port}")

        # 启动交易循环
        symbols = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA']
        tasks = [
            self.trading_loop(symbols),
            self.monitor_orders(),
            self.risk_check_loop()
        ]
        await asyncio.gather(*tasks)

    async def trading_loop(self, symbols):
        while self.is_running:
            try:
                await asyncio.gather(*[self.execute_arbitrage(s) for s in symbols])
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Trading loop error: {str(e)}")

    async def risk_check_loop(self):
        while self.is_running:
            await self.risk_management()
            await asyncio.sleep(60)

if __name__ == "__main__":
    bot = ArbitrageBot()
    
    # 信号处理
    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        bot.is_running = False
    
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 运行主程序
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        loop.close()
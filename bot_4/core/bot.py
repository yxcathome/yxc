import os
import asyncio
import logging
from decimal import Decimal, getcontext
import ccxt.async_support as ccxt
from datetime import datetime
from dotenv import load_dotenv

from strategies.base import BaseStrategy
from strategies.arbitrage import ArbitrageStrategy
from strategies.grid import GridStrategy
from strategies.trend import TrendStrategy
from strategies.funding import FundingStrategy
from core.risk_manager import RiskManager
from config.settings import CONFIG
from utils.logger import get_logger

# 设置 Decimal 精度
getcontext().prec = 10

logger = get_logger(__name__)

class ArbitrageTrendBot:
    def __init__(self):
        # 加载环境变量
        load_dotenv()
        self._validate_env_vars()
        
        # 初始化交易所连接
        self.okx = self._init_okx()
        self.binance = self._init_binance()
        self._price_history = []  # 新增价格历史记录属性

        # 共同交易对，在 run() 中异步加载
        self.common_pairs = []

        # 基础变量初始化
        self.is_running = True
        self.is_shutting_down = False
        self.is_paused = False
        self.config = CONFIG
        # 采用全仓模式，即每边使用7 USDT做满仓套利
        self.balances = {'okx': Decimal('7'), 'binance': Decimal('7')}
        self.equity = {'okx': Decimal('7'), 'binance': Decimal('7')}
        self.start_equity = {}

        # 统计数据
        self.stats = {
            'start_time': datetime.now(),
            'total_checks': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_profit': Decimal('0'),
            'max_drawdown': Decimal('0')
        }

        # 初始化所有策略
        self.strategies = self._init_strategies()

        # 初始化风控模块
        self.risk_manager = RiskManager(self, self.config)

    def _validate_env_vars(self):
        required_vars = [
            'OKX_API_KEY', 'OKX_SECRET', 'OKX_PASSWORD',
            'BINANCE_API_KEY', 'BINANCE_SECRET'
        ]
        missing = [var for var in required_vars if not os.environ.get(var)]
        if missing:
            raise RuntimeError(f"缺少环境变量: {', '.join(missing)}")

    def _init_okx(self):
        return ccxt.okx({
            'apiKey': os.environ['OKX_API_KEY'],
            'secret': os.environ['OKX_SECRET'],
            'password': os.environ['OKX_PASSWORD'],
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
            'timeout': 15000
        })

    def _init_binance(self):
        return ccxt.binance({
            'apiKey': os.environ['BINANCE_API_KEY'],
            'secret': os.environ['BINANCE_SECRET'],
            'options': {
                'defaultType': 'future',
                'hedgeMode': False,
                'positionSide': 'BOTH'
            },
            'enableRateLimit': True,
            'timeout': 15000
        })

    def _init_strategies(self):
        return {
            'arbitrage': ArbitrageStrategy(self, self.config),
            'grid': GridStrategy(self, self.config),
            'trend': TrendStrategy(self, self.config),
            'funding': FundingStrategy(self, self.config)
        }

    async def update_balances(self):
        try:
            okx_balance = await self.okx.fetch_balance()
            binance_balance = await self.binance.fetch_balance()
            self.balances['okx'] = Decimal(str(okx_balance['USDT']['free'])).quantize(Decimal('0.01'))
            self.equity['okx'] = Decimal(str(okx_balance['USDT'].get('total', okx_balance['USDT']['free']))).quantize(Decimal('0.01'))
            self.balances['binance'] = Decimal(str(binance_balance['USDT']['free'])).quantize(Decimal('0.01'))
            self.equity['binance'] = Decimal(str(binance_balance['USDT'].get('total', binance_balance['USDT']['free']))).quantize(Decimal('0.01'))
            logger.info(f"余额更新 - OKX: {self.balances['okx']}，币安: {self.balances['binance']}")
        except Exception as e:
            logger.error(f"更新余额失败: {e}")

    async def _init_trading_pairs(self):
        try:
            okx_markets = await self.okx.load_markets()
            binance_markets = await self.binance.load_markets()

            okx_symbols = {symbol for symbol, market in okx_markets.items() if market.get('type') == 'swap' and market.get('quote') == 'USDT' and market.get('active')}
            binance_symbols = {symbol for symbol, market in binance_markets.items() if market.get('type') == 'swap' and market.get('quote') == 'USDT' and market.get('active')}
            common_symbols = okx_symbols.intersection(binance_symbols)
            if not common_symbols:
                logger.error("未找到共同交易对")
                raise ValueError("无有效共同交易对")
            logger.info(f"共同交易对示例: {list(common_symbols)[:5]}")
            return list(common_symbols)
        except Exception as e:
            logger.error(f"初始化交易对异常: {e}")
            raise ValueError("无有效共同交易对")

    async def get_orderbook(self, exchange, symbol):
        try:
            orderbook = await exchange.fetch_order_book(symbol)
            return orderbook
        except Exception as e:
            logger.error(f"获取 {symbol} 订单簿失败: {e}")
            return None

    # 替换原有的 calculate_trade_amount 方法
    def calculate_trade_amount(self, exchange_name: str, price: Decimal) -> Decimal:
        # 获取历史胜率（过去100次交易）
        total_trades = self.stats['successful_trades'] + self.stats['failed_trades']
        win_rate = self.stats['successful_trades'] / total_trades if total_trades > 0 else 0

        # 动态调整杠杆
        base_leverage = Decimal('20')
        if win_rate > 0.6:
            leverage = Decimal('30')
        elif self._get_volatility() > Decimal('0.03'):  # 需实现波动率计算
            leverage = Decimal('25')
        else:
            leverage = base_leverage

        available = self.balances[exchange_name]
        amount = (available * leverage) / price

        # 检查交易所最小交易量
        min_notional = Decimal('5')
        if amount * price < min_notional:
            logger.warning(f"{exchange_name} 交易量不足最小要求")
            return Decimal('0')

        return amount.quantize(Decimal('0.0001'))

    # 新增波动率计算方法
    def _get_volatility(self, window=100):
        """计算最近100根K线的价格波动率"""
        if not hasattr(self, '_price_history'):
            return Decimal('0')
        prices = [float(p) for p in self._price_history[-window:]]
        if not prices:
            return Decimal('0')
        mean = sum(prices) / len(prices)
        variance = sum((x - mean) ** 2 for x in prices) / len(prices)
        return Decimal(str(variance ** 0.5))

    async def execute_trade(self, symbol, signal):
        """
        在下单前进行双边检查：
           - 检查两边是否都满足下单条件；
           - 如果任一边不满足，则跳过此次套利机会；
           - 如果两边订单都满足，则同时下单。
        这里假设 signal 包含交易指标，具体实现由各策略定义。
        """
        # 计算两边下单量
        # 假设 signal 包含价格信息，具体价格以实际 API 为准，这里只是示例
        okx_price = Decimal(str(signal.get('okx_price')))
        binance_price = Decimal(str(signal.get('binance_price')))
        okx_amount = self.calculate_trade_amount("okx", okx_price)
        binance_amount = self.calculate_trade_amount("binance", binance_price)
        # 如果任一边计算结果为0，则跳过
        if okx_amount == Decimal('0') or binance_amount == Decimal('0'):
            logger.info(f"{symbol}下单条件不满足，跳过套利")
            return False
        # 记录下两边订单信息（此处调用的 execute 是各策略内部封装的下单方法）
        okx_result = await self.strategies['arbitrage'].execute({'symbol': symbol, 'exchange': 'okx', 'amount': str(okx_amount), 'price': str(okx_price)})
        binance_result = await self.strategies['arbitrage'].execute({'symbol': symbol, 'exchange': 'binance', 'amount': str(binance_amount), 'price': str(binance_price)})
        if okx_result and binance_result:
            logger.info(f"{symbol}双边订单执行成功")
            return True
        else:
            logger.error(f"{symbol}双边订单执行失败")
            return False

    async def main_loop(self):
        while self.is_running:
            if self.is_shutting_down or self.is_paused:
                await asyncio.sleep(1)
                continue
            try:
                for symbol in self.common_pairs:
                    if not await self.risk_manager.can_trade(symbol, {}):
                        continue
                    signal = await self.strategies['arbitrage'].analyze(symbol)
                    if signal:
                        await self.execute_trade(symbol, signal)
            except Exception as e:
                logger.error(f"主循环异常: {e}")
            await asyncio.sleep(self.config.get('request_delay', 0.5))

    async def update_balances_loop(self):
        while self.is_running:
            await self.update_balances()
            await asyncio.sleep(self.config.get('check_interval', 1))

    async def monitor_positions(self):
        while self.is_running:
            # 包括仓位检测、单边仓位平仓逻辑等
            await asyncio.sleep(5)

    async def run(self):
        try:
            self.common_pairs = await self._init_trading_pairs()
            if not self.common_pairs:
                raise RuntimeError("无有效共同交易对")
            await self.update_balances()
            self.start_equity = self.equity.copy()
            tasks = [
                self.main_loop(),
                self.update_balances_loop(),
                self.monitor_positions()
            ]
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"运行异常: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self):
        if self.is_shutting_down:
            return
        self.is_shutting_down = True
        self.is_running = False
        logger.info("开始关闭系统...")
        try:
            await asyncio.gather(
                self.okx.close(),
                self.binance.close(),
            )
            logger.info("交易所连接已关闭")
        except Exception as e:
            logger.error(f"关闭交易所异常: {e}")
        await asyncio.sleep(1)
        logger.info("系统已关闭")
import os
import asyncio
import logging
from decimal import Decimal, getcontext
import ccxt.async_support as ccxt
from typing import Dict, List
from strategies.base import BaseStrategy
from strategies.arbitrage import ArbitrageStrategy
from strategies.grid import GridStrategy
from strategies.trend import TrendStrategy
from strategies.funding import FundingStrategy
from core.risk_manager import RiskManager
from config.settings import CONFIG
from utils.logger import get_logger
from dotenv import load_dotenv
from datetime import datetime

# 设置 Decimal 精度
getcontext().prec = 10

logger = get_logger(__name__)

class ArbitrageTrendBot:
    def __init__(self):
        # 验证必要的环境变量
        self._validate_env_vars()
        
        # 初始化交易所连接
        self.okx = self._init_okx()
        self.binance = self._init_binance()

        # 初始化交易对
        self.trading_pairs = self.load_common_pairs()
        if not self.trading_pairs:
            raise ValueError("无有效共同交易对")

        # 初始化基础变量
        self.is_running = True
        self.is_shutting_down = False
        self.is_paused = False
        self.config = CONFIG
        self.balances = {'okx': Decimal('0'), 'binance': Decimal('0')}
        self.equity = {'okx': Decimal('0'), 'binance': Decimal('0')}
        self.start_equity = {}
        self.common_pairs = []
        
        # 初始化统计数据
        self.stats = {
            'start_time': datetime.now(),
            'total_checks': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_profit': Decimal('0'),
            'max_drawdown': Decimal('0')
        }
        
        # 初始化策略
        self.strategies = self._init_strategies()
        
        # 初始化风控
        self.risk_manager = RiskManager(self, self.config)

    def _validate_env_vars(self):
        """验证环境变量"""
        required_vars = [
            'OKX_API_KEY', 'OKX_SECRET', 'OKX_PASSWORD',
            'BINANCE_API_KEY', 'BINANCE_SECRET'
        ]
        missing = [var for var in required_vars if not os.environ.get(var)]
        if missing:
            raise RuntimeError(f"缺少环境变量: {', '.join(missing)}")

    def _init_okx(self):
        """初始化OKX连接"""
        return ccxt.okx({
            'apiKey': os.environ['OKX_API_KEY'],
            'secret': os.environ['OKX_SECRET'],
            'password': os.environ['OKX_PASSWORD'],
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
            'timeout': 15000
        })

    def _init_binance(self):
        """初始化Binance连接"""
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

    def _init_strategies(self) -> Dict[str, BaseStrategy]:
        """初始化策略"""
        return {
            'arbitrage': ArbitrageStrategy(self, self.config),
            'grid': GridStrategy(self, self.config),
            'trend': TrendStrategy(self, self.config),
            'funding': FundingStrategy(self, self.config)
        }

    async def update_balances(self):
        """更新账户余额"""
        try:
            okx_balance = await self.okx.fetch_balance()
            binance_balance = await self.binance.fetch_balance()
            
            self.balances['okx'] = Decimal(str(okx_balance['USDT']['free'])).quantize(Decimal('0.01'))
            self.equity['okx'] = Decimal(str(okx_balance['USDT'].get('total', okx_balance['USDT']['free']))).quantize(Decimal('0.01'))
            self.balances['binance'] = Decimal(str(binance_balance['USDT']['free'])).quantize(Decimal('0.01'))
            self.equity['binance'] = Decimal(str(binance_balance['USDT'].get('total', binance_balance['USDT']['free']))).quantize(Decimal('0.01'))
            
            logger.info(f"余额更新 - OKX: {self.balances['okx']}, Binance: {self.balances['binance']}")
        except Exception as e:
            logger.error(f"更新余额失败: {e}")

    async def _init_trading_pairs(self):
        """初始化交易对"""
        try:
            # 获取OKX可用交易对
            okx_markets = await self.exchange_manager.okx.load_markets()
            okx_symbols = set()

            # 筛选OKX的USDT永续合约
            for symbol, market in okx_markets.items():
                if (market.get('type') == 'swap' and
                    market.get('settled') and
                    market.get('quote') == 'USDT' and
                    market.get('active')):
                    okx_symbols.add(symbol)

            if not okx_symbols:
                self.logger.error("未找到OKX有效交易对")
                raise ValueError("无有效共同交易对")

            # 获取Binance可用交易对
            binance_markets = await self.exchange_manager.binance.load_markets()
            binance_symbols = set()

            # 筛选Binance的USDT永续合约
            for symbol, market in binance_markets.items():
                if (market.get('type') == 'swap' and
                    market.get('quote') == 'USDT' and
                    market.get('active')):
                    binance_symbols.add(symbol)

            if not binance_symbols:
                self.logger.error("未找到Binance有效交易对")
                raise ValueError("无有效共同交易对")

            # 找出两个交易所的交集
            common_symbols = okx_symbols.intersection(binance_symbols)

            if not common_symbols:
                self.logger.error("未找到交易所间的共同交易对")
                raise ValueError("无有效共同交易对")

            self.logger.info(f"OKX交易对数量: {len(okx_symbols)}")
            self.logger.info(f"Binance交易对数量: {len(binance_symbols)}")
            self.logger.info(f"共同交易对数量: {len(common_symbols)}")
            self.logger.info(f"部分共同交易对示例: {list(common_symbols)[:5]}...")  # 只显示前5个作为示例

            return list(common_symbols)
        except Exception as e:
            self.logger.error(f"初始化交易对异常: {str(e)}")
            raise ValueError("无有效共同交易对")

    async def run(self):
        """主运行函数"""
        try:
            # 初始化市场数据
            await self.load_common_pairs()
            if not self.common_pairs:
                raise RuntimeError("无有效共同交易对")
                
            # 初始化账户数据
            await self.update_balances()
            self.start_equity = self.equity.copy()
            
            # 启动所有任务
            tasks = [
                self.main_loop(),
                self.update_balances_loop(),
                self.monitor_positions()
            ]
            
            await asyncio.gather(*tasks)
            
        except Exception as e:
            logger.error(f"运行异常: {e}")
        finally:
            await self.shutdown()

    async def main_loop(self):
        """主循环"""
        while self.is_running:
            if self.is_shutting_down or self.is_paused:
                await asyncio.sleep(1)
                continue
            
            try:
                for okx_sym, binance_sym in self.common_pairs:
                    if not await self.risk_manager.can_trade(okx_sym, {}):
                        continue
                        
                    for strategy in self.strategies.values():
                        if not strategy.is_active:
                            continue
                            
                        signal = await strategy.analyze(okx_sym)
                        if signal and await strategy.execute(signal):
                            logger.info(f"策略 {strategy.name} 执行成功")
                            
            except Exception as e:
                logger.error(f"主循环异常: {e}")
                
            await asyncio.sleep(self.config.get('request_delay', 0.5))

    async def shutdown(self):
        """关闭系统"""
        if self.is_shutting_down:
            return
            
        self.is_shutting_down = True
        self.is_running = False
        logger.info("开始关闭系统...")
        
        try:
            # 关闭交易所连接
            await asyncio.gather(
                self.okx.close(),
                self.binance.close(),
                return_exceptions=True
            )
            logger.info("系统已关闭")
        except Exception as e:
            logger.error(f"关闭系统异常: {e}")
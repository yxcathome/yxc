import os
from typing import Dict, Optional
import ccxt.async_support as ccxt
import logging
from decimal import Decimal
import asyncio
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ExchangeManager:
    def __init__(self, config):
        self.config = config
        self.exchanges = {}
        self._init_exchanges()
        self.request_counters = {
            'okx': {'count': 0, 'reset_time': datetime.now()},
            'binance': {'count': 0, 'reset_time': datetime.now()}
        }

    def _init_exchanges(self):
        """初始化交易所连接"""
        try:
            # OKX
            self.exchanges['okx'] = ccxt.okx({
                'apiKey': os.getenv('OKX_API_KEY'),
                'secret': os.getenv('OKX_SECRET'),
                'password': os.getenv('OKX_PASSWORD'),
                'options': {
                    'defaultType': 'swap',
                    'adjustForTimeDifference': True
                },
                'enableRateLimit': True,
                'timeout': 15000
            })

            # Binance
            self.exchanges['binance'] = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY'),
                'secret': os.getenv('BINANCE_SECRET'),
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'hedgeMode': False
                },
                'enableRateLimit': True,
                'timeout': 15000
            })

        except Exception as e:
            logger.error(f"初始化交易所连接失败: {e}")
            raise

    async def get_orderbook(self, exchange_id: str, symbol: str, limit: int = 20) -> Optional[Dict]:
        """获取订单簿"""
        try:
            await self._check_rate_limit(exchange_id)
            exchange = self.exchanges[exchange_id]
            orderbook = await exchange.fetch_order_book(symbol, limit)
            return orderbook
        except Exception as e:
            logger.error(f"获取订单簿失败 {exchange_id} {symbol}: {e}")
            return None

    async def create_order(self, exchange_id: str, symbol: str, order_type: str,
                         side: str, amount: float, price: Optional[float] = None) -> Optional[Dict]:
        """创建订单"""
        try:
            await self._check_rate_limit(exchange_id)
            exchange = self.exchanges[exchange_id]
            
            params = {}
            if exchange_id == 'binance':
                params['reduceOnly'] = False
            
            order = await exchange.create_order(
                symbol,
                order_type,
                side,
                amount,
                price,
                params
            )
            
            logger.info(f"创建订单成功 {exchange_id} {symbol} {side}: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"创建订单失败 {exchange_id} {symbol}: {e}")
            return None

    async def cancel_order(self, exchange_id: str, order_id: str, symbol: str) -> bool:
        """取消订单"""
        try:
            await self._check_rate_limit(exchange_id)
            exchange = self.exchanges[exchange_id]
            await exchange.cancel_order(order_id, symbol)
            logger.info(f"取消订单成功 {exchange_id} {symbol}: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败 {exchange_id} {symbol}: {e}")
            return False

    async def get_position(self, exchange_id: str, symbol: str) -> Optional[Dict]:
        """获取持仓"""
        try:
            await self._check_rate_limit(exchange_id)
            exchange = self.exchanges[exchange_id]
            positions = await exchange.fetch_positions([symbol])
            return positions[0] if positions else None
        except Exception as e:
            logger.error(f"获取持仓失败 {exchange_id} {symbol}: {e}")
            return None

    async def get_balance(self, exchange_id: str) -> Optional[Dict]:
        """获取账户余额"""
        try:
            await self._check_rate_limit(exchange_id)
            exchange = self.exchanges[exchange_id]
            balance = await exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"获取余额失败 {exchange_id}: {e}")
            return None

    async def _check_rate_limit(self, exchange_id: str):
        """检查和控制请求频率"""
        counter = self.request_counters[exchange_id]
        now = datetime.now()
        
        # 重置计数器
        if (now - counter['reset_time']).total_seconds() >= 1:
            counter['count'] = 0
            counter['reset_time'] = now
            
        # 检查限制
        max_requests = self.config['exchange_limits'].get(exchange_id, 20)
        if counter['count'] >= max_requests:
            await asyncio.sleep(1)
            counter['count'] = 0
            counter['reset_time'] = datetime.now()
            
        counter['count'] += 1

    async def close_all(self):
        """关闭所有交易所连接"""
        for exchange in self.exchanges.values():
            await exchange.close()
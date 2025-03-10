from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from decimal import Decimal
import asyncio
from datetime import datetime
import logging
from utils.logger import setup_logger
from config.settings import EXCHANGE_CONFIG

class BaseExchange(ABC):
    def __init__(self, name: str):
        self.name = name
        self.config = EXCHANGE_CONFIG[name]
        self.logger = setup_logger(f"exchange.{name}")
        self.markets = {}
        self.positions = {}
        self.orderbook = {}
        self.last_update = {}
        self.active = False
        self._ws = None
        self._ws_lock = asyncio.Lock()

    @abstractmethod
    async def connect(self) -> bool:
        """连接交易所"""
        pass

    @abstractmethod
    async def load_markets(self) -> Dict:
        """加载市场数据"""
        pass

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """获取最新行情"""
        pass

    @abstractmethod
    async def create_order(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None) -> Dict:
        """创建订单"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        pass

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> Dict:
        """查询订单状态"""
        pass

    @abstractmethod
    async def fetch_position(self, symbol: str) -> Dict:
        """获取持仓信息"""
        pass

    @abstractmethod
    async def fetch_balance(self) -> Dict:
        """获取账户余额"""
        pass

    async def update_orderbook(self, symbol: str, data: Dict):
        """更新订单簿"""
        try:
            self.orderbook[symbol] = {
                'bids': sorted([(Decimal(str(p)), Decimal(str(q))) 
                              for p, q in data['bids']], reverse=True),
                'asks': sorted([(Decimal(str(p)), Decimal(str(q))) 
                              for p, q in data['asks']]),
                'timestamp': datetime.utcnow()
            }
        except Exception as e:
            self.logger.error(f"更新订单簿失败: {e}")

    async def get_best_price(self, symbol: str) -> Dict[str, Decimal]:
        """获取最优价格"""
        try:
            ob = self.orderbook.get(symbol)
            if not ob or (datetime.utcnow() - ob['timestamp']).total_seconds() > 5:
                return None

            return {
                'bid': ob['bids'][0][0] if ob['bids'] else None,
                'ask': ob['asks'][0][0] if ob['asks'] else None
            }
        except Exception as e:
            self.logger.error(f"获取最优价格失败: {e}")
            return None

    async def calculate_effective_price(self, symbol: str, side: str, 
                                     amount: Decimal) -> Optional[Decimal]:
        """计算有效价格（考虑深度）"""
        try:
            ob = self.orderbook.get(symbol)
            if not ob:
                return None

            orders = ob['bids'] if side == 'sell' else ob['asks']
            total_amount = Decimal('0')
            weighted_price = Decimal('0')

            for price, qty in orders:
                if total_amount >= amount:
                    break
                available = min(qty, amount - total_amount)
                weighted_price += price * available
                total_amount += available

            if total_amount < amount:
                return None

            return weighted_price / amount

        except Exception as e:
            self.logger.error(f"计算有效价格失败: {e}")
            return None

    async def check_order_status(self, order_id: str, symbol: str, 
                               max_retries: int = 5) -> Dict:
        """检查订单状态（带重试）"""
        for i in range(max_retries):
            try:
                order = await self.fetch_order(order_id, symbol)
                if order['status'] in ['closed', 'canceled', 'expired']:
                    return order
                await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"检查订单状态失败 (重试 {i+1}/{max_retries}): {e}")
                await asyncio.sleep(1)
        return None
from typing import Dict, Optional
from decimal import Decimal, ROUND_DOWN
import time
from config import Config
from logger import Logger
from market_data import MarketData

class PositionManager:
    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.logger = Logger("PositionManager")
        self.market_data = MarketData(exchange_id)
        self.exchange = self.market_data.exchange
        self.positions = {}
        self.orders = {}
    
    def open_position(self, symbol: str, side: str, 
                     amount: float, price: float) -> bool:
        """
        开仓操作
        """
        try:
            # 检查是否已有相同方向的仓位
            current_position = self.get_position(symbol)
            if current_position and current_position['side'] == side:
                self.logger.warning(
                    f"Already have {side} position for {symbol}"
                )
                return False
            
            # 确保amount满足交易所最小交易量要求
            amount = self._normalize_amount(symbol, amount)
            
            # 执行市价单
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=amount,
                type='market'
            )
            
            self.orders[order['id']] = order
            
            # 记录开仓信息
            self.positions[symbol] = {
                'side': side,
                'amount': amount,
                'entry_price': price,
                'order_id': order['id']
            }
            
            self.logger.trade_log(
                'OPEN',
                symbol,
                price,
                amount,
                side
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error opening position: {str(e)}")
            return False
    
    def close_position(self, symbol: str, reason: str = '') -> bool:
        """
        平仓操作
        """
        try:
            position = self.get_position(symbol)
            if not position:
                return False
            
            # 计算平仓方向
            close_side = 'sell' if position['side'] == 'buy' else 'buy'
            
            # 执行市价平仓
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=close_side,
                amount=position['amount'],
                type='market'
            )
            
            current_price = self.market_data.get_current_price(symbol)
            
            self.logger.trade_log(
                'CLOSE',
                symbol,
                current_price,
                position['amount'],
                close_side,
                f"Reason: {reason}"
            )
            
            # 清除仓位记录
            del self.positions[symbol]
            self.orders[order['id']] = order
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
            return False
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        获取当前仓位信息
        """
        try:
            positions = self.exchange.fetch_positions([symbol])
            for position in positions:
                if position['contracts'] > 0:
                    return {
                        'side': 'buy' if position['side'] == 'long' else 'sell',
                        'amount': position['contracts'],
                        'entry_price': position['entryPrice'],
                        'unrealized_pnl': position['unrealizedPnl']
                    }
            return None
        except Exception as e:
            self.logger.error(f"Error fetching position: {str(e)}")
            return None
    
    def _normalize_amount(self, symbol: str, amount: float) -> float:
        """
        标准化下单数量，确保满足交易所规则
        """
        try:
            market = self.exchange.market(symbol)
            
            # 获取数量精度
            precision = market['precision']['amount']
            
            # 转换为Decimal进行精确计算
            normalized = Decimal(str(amount))
            
            # 根据精度截断
            normalized = normalized.quantize(
                Decimal('1e-' + str(precision)),
                rounding=ROUND_DOWN
            )
            
            # 确保大于最小交易量
            min_amount = market['limits']['amount']['min']
            normalized = max(normalized, Decimal(str(min_amount)))
            
            return float(normalized)
            
        except Exception as e:
            self.logger.error(f"Error normalizing amount: {str(e)}")
            raise
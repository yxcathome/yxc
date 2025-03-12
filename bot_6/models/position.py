from typing import Dict, Optional
from datetime import datetime
from decimal import Decimal
import uuid

class Position:
    def __init__(self, id: Optional[str] = None, **kwargs):
        self.id = id or str(uuid.uuid4())
        self.strategy_id = kwargs.get('strategy_id')
        self.symbol = kwargs.get('symbol', '')
        self.direction = kwargs.get('direction', '')  # 'long' or 'short'
        self.amount = Decimal(str(kwargs.get('amount', '0')))
        self.entry_price = Decimal(str(kwargs.get('entry_price', '0')))
        self.current_price = Decimal(str(kwargs.get('current_price', '0')))
        self.unrealized_pnl = Decimal(str(kwargs.get('unrealized_pnl', '0')))
        self.realized_pnl = Decimal(str(kwargs.get('realized_pnl', '0')))
        self.status = kwargs.get('status', 'open')  # 'open' or 'closed'
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.updated_at = kwargs.get('updated_at', datetime.utcnow())
        
        # 计算收益率
        self.roi = None
        self._calculate_roi()
        
    async def update_price(self, price: Decimal):
        """更新当前价格和未实现盈亏"""
        try:
            self.current_price = price
            
            # 计算未实现盈亏
            if self.direction == 'long':
                self.unrealized_pnl = (self.current_price - self.entry_price) * self.amount
            else:
                self.unrealized_pnl = (self.entry_price - self.current_price) * self.amount
                
            self._calculate_roi()
            self.updated_at = datetime.utcnow()
            
        except Exception as e:
            raise Exception(f"更新持仓价格失败: {e}")
            
    async def close(self, price: Optional[Decimal] = None):
        """平仓"""
        try:
            if price:
                await self.update_price(price)
                
            # 更新已实现盈亏
            self.realized_pnl += self.unrealized_pnl
            self.unrealized_pnl = Decimal('0')
            
            self.status = 'closed'
            self.updated_at = datetime.utcnow()
            
        except Exception as e:
            raise Exception(f"平仓失败: {e}")
            
    def _calculate_roi(self):
        """计算收益率"""
        try:
            if self.entry_price > 0:
                total_pnl = self.unrealized_pnl + self.realized_pnl
                investment = self.amount * self.entry_price
                self.roi = total_pnl / investment
            else:
                self.roi = Decimal('0')
                
        except Exception as e:
            self.roi = Decimal('0')
            
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'strategyId': self.strategy_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'amount': float(self.amount),
            'entryPrice': float(self.entry_price),
            'currentPrice': float(self.current_price),
            'unrealizedPnL': float(self.unrealized_pnl),
            'realizedPnL': float(self.realized_pnl),
            'roi': float(self.roi) if self.roi is not None else 0,
            'status': self.status,
            'holdTime': (datetime.utcnow() - self.created_at).total_seconds(),
            'createdAt': self.created_at.isoformat(),
            'updatedAt': self.updated_at.isoformat()
        }
from abc import ABC, abstractmethod
from typing import Dict, Optional
import pandas as pd
from config import Config
from logger import Logger
from market_data import MarketData

class StrategyBase(ABC):
    def __init__(self, exchange_id: str, symbol: str):
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.logger = Logger(self.__class__.__name__)
        self.market_data = MarketData(exchange_id)
    
    @abstractmethod
    def generate_signal(self) -> Dict[str, any]:
        """
        生成交易信号
        返回字典包含：
        - 'action': 'buy' | 'sell' | 'hold'
        - 'price': float
        - 'reason': str
        """
        pass
    
    def get_position_size(self, price: float) -> float:
        """
        计算开仓数量
        """
        try:
            config = Config.EXCHANGES[self.exchange_id]
            
            # 获取账户余额
            balance = self.get_available_balance()
            position_value = balance * Config.POSITION_SIZE_PCT
            
            # 确保满足最小下单金额
            position_value = max(position_value, config.min_order_value)
            
            # 计算合约数量
            contract_qty = position_value / price
            
            # 确保满足最小合约数量
            contract_qty = max(contract_qty, config.min_contract_qty)
            
            return contract_qty
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {str(e)}")
            raise
    
    def get_available_balance(self) -> float:
        """
        获取可用余额
        """
        try:
            balance = self.market_data.exchange.fetch_balance()
            return float(balance['USDT']['free'])
        except Exception as e:
            self.logger.error(f"Error fetching balance: {str(e)}")
            raise
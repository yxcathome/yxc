from decimal import Decimal
from typing import Dict, Optional
import math
from config.settings import EXCHANGE_RULES

class QuantityConverter:
    def __init__(self):
        self.rules = EXCHANGE_RULES

    def normalize_okx_quantity(self, symbol: str, amount: Decimal, 
                             price: Decimal) -> Optional[int]:
        """标准化OKX合约数量"""
        try:
            contract_value = self.rules['okx']['contract_values'][symbol]
            min_size = self.rules['okx']['min_sizes'][symbol]

            # 计算合约张数
            contracts = int(amount / (contract_value * price))
            
            # 确保达到最小张数
            contracts = max(contracts, min_size)
            
            return contracts

        except Exception as e:
            logging.error(f"OKX数量标准化失败: {e}")
            return None

    def normalize_binance_quantity(self, symbol: str, amount: Decimal,
                                 price: Decimal) -> Optional[Decimal]:
        """标准化Binance数量"""
        try:
            min_notional = self.rules['binance']['min_notional'][symbol]
            step_size = self.rules['binance']['step_sizes'][symbol]

            # 计算数量
            quantity = amount / price
            
            # 确保达到最小名义价值
            if quantity * price < min_notional:
                quantity = min_notional / price

            # 调整到步长
            quantity = math.floor(float(quantity) / float(step_size)) * float(step_size)
            
            return Decimal(str(quantity))

        except Exception as e:
            logging.error(f"Binance数量标准化失败: {e}")
            return None

    def validate_order_quantity(self, exchange: str, symbol: str,
                              quantity: Decimal, price: Decimal) -> bool:
        """验证订单数量是否有效"""
        try:
            if exchange == 'okx':
                min_size = self.rules['okx']['min_sizes'][symbol]
                contract_value = self.rules['okx']['contract_values'][symbol]
                return quantity >= min_size and quantity * contract_value * price >= 5

            elif exchange == 'binance':
                min_notional = self.rules['binance']['min_notional'][symbol]
                return quantity * price >= min_notional

            return False

        except Exception as e:
            logging.error(f"订单数量验证失败: {e}")
            return False
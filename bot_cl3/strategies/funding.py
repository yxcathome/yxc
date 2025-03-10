from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
import logging
from .base import BaseStrategy

class FundingStrategy(BaseStrategy):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.name = "funding"
        self.is_active = config['enabled_strategies']['funding']
        
        # 从配置中获取资金费率策略参数
        funding_config = config['funding']
        self.min_rate = Decimal(str(funding_config['min_rate']))
        self.hold_hours = funding_config['hold_hours']  # 修改这里：使用 hold_hours
        self.position_size = Decimal(str(funding_config['position_size']))
        
        # 初始化状态
        self.positions = {}
        self.last_check = {}

    async def analyze(self, symbol: str) -> Optional[Dict]:
        """分析资金费率并生成交易信号"""
        try:
            # 获取资金费率
            funding_rates = await self._get_funding_rates(symbol)
            if not funding_rates:
                return None

            # 分析资金费率差异
            signal = self._analyze_rates(symbol, funding_rates)
            return signal

        except Exception as e:
            self.logger.error(f"资金费率分析异常: {e}")
            return None

    async def execute(self, signal: Dict) -> bool:
        """执行资金费率套利交易"""
        try:
            if not signal or 'action' not in signal:
                return False

            symbol = signal['symbol']
            action = signal['action']
            amount = signal.get('amount', self.position_size)

            if action == 'open_long':
                # 开多仓
                order = await self.bot.okx.create_market_buy_order(
                    symbol=symbol,
                    amount=float(amount)
                )
                if order['status'] == 'closed':
                    self.positions[symbol] = {
                        'side': 'long',
                        'entry_time': datetime.utcnow(),
                        'amount': Decimal(str(amount))
                    }
                    self.logger.info(f"资金费率策略开多仓成功: {symbol}")
                    return True

            elif action == 'open_short':
                # 开空仓
                order = await self.bot.okx.create_market_sell_order(
                    symbol=symbol,
                    amount=float(amount)
                )
                if order['status'] == 'closed':
                    self.positions[symbol] = {
                        'side': 'short',
                        'entry_time': datetime.utcnow(),
                        'amount': Decimal(str(amount))
                    }
                    self.logger.info(f"资金费率策略开空仓成功: {symbol}")
                    return True

            elif action == 'close':
                # 平仓
                if symbol in self.positions:
                    position = self.positions[symbol]
                    if position['side'] == 'long':
                        order = await self.bot.okx.create_market_sell_order(
                            symbol=symbol,
                            amount=float(position['amount'])
                        )
                    else:
                        order = await self.bot.okx.create_market_buy_order(
                            symbol=symbol,
                            amount=float(position['amount'])
                        )
                    
                    if order['status'] == 'closed':
                        del self.positions[symbol]
                        self.logger.info(f"资金费率策略平仓成功: {symbol}")
                        return True

            return False

        except Exception as e:
            self.logger.error(f"执行资金费率交易异常: {e}")
            return False

    async def _get_funding_rates(self, symbol: str) -> Optional[Dict]:
        """获取资金费率"""
        try:
            # 获取OKX资金费率
            okx_funding = await self.bot.okx.fetch_funding_rate(symbol)
            
            # 可以添加其他交易所的资金费率获取
            
            return {
                'okx': Decimal(str(okx_funding['fundingRate']))
            }
            
        except Exception as e:
            self.logger.error(f"获取资金费率异常: {e}")
            return None

    def _analyze_rates(self, symbol: str, rates: Dict) -> Optional[Dict]:
        """分析资金费率并生成信号"""
        try:
            okx_rate = rates['okx']
            
            # 检查是否已有持仓
            if symbol in self.positions:
                position = self.positions[symbol]
                hold_time = datetime.utcnow() - position['entry_time']
                
                # 检查是否达到预定持仓时间
                if hold_time >= timedelta(hours=self.hold_hours):
                    return {
                        'action': 'close',
                        'symbol': symbol
                    }
                return None
            
            # 生成开仓信号
            if abs(okx_rate) >= self.min_rate:
                if okx_rate > 0:
                    return {
                        'action': 'open_short',
                        'symbol': symbol,
                        'amount': self.position_size
                    }
                else:
                    return {
                        'action': 'open_long',
                        'symbol': symbol,
                        'amount': self.position_size
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"分析资金费率异常: {e}")
            return None

    async def on_tick(self):
        """定时检查持仓状态"""
        try:
            current_time = datetime.utcnow()
            
            for symbol in list(self.positions.keys()):
                position = self.positions[symbol]
                hold_time = current_time - position['entry_time']
                
                # 检查是否达到预定持仓时间
                if hold_time >= timedelta(hours=self.hold_hours):
                    await self.execute({
                        'action': 'close',
                        'symbol': symbol
                    })
                    
        except Exception as e:
            self.logger.error(f"定时检查异常: {e}")
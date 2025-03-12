from decimal import Decimal
from typing import Dict, Optional, List
import asyncio
from datetime import datetime
from strategies.base_strategy import BaseStrategy
import numpy as np

class FundingArbitrageStrategy(BaseStrategy):
    def __init__(self, exchange_manager, risk_manager):
        super().__init__("funding_arbitrage", exchange_manager, risk_manager)
        
        # 策略参数
        self.min_funding_diff = Decimal('0.0001')  # 最小资金费率差异 0.01%
        self.max_hold_time = 28800  # 最大持仓时间 8小时
        self.min_volume = Decimal('1000')  # 最小交易量
        self.funding_check_interval = 300  # 检查间隔 5分钟
        
        # 状态变量
        self.funding_rates = {}  # 资金费率缓存
        self.next_funding_times = {}  # 下次资金费率时间
        
    async def initialize(self) -> bool:
        """初始化策略"""
        try:
            # 加载配置
            config = self.config.get('arbitrage', {}).get('funding_arb', {})
            if config:
                self.min_funding_diff = Decimal(str(config.get('min_funding_diff', self.min_funding_diff)))
                self.max_hold_time = config.get('max_hold_time', self.max_hold_time)
                self.min_volume = Decimal(str(config.get('min_volume', self.min_volume)))
                
            # 启动监控任务
            asyncio.create_task(self._monitor_funding_rates())
            
            self.logger.info("资金费率套利策略初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"资金费率套利策略初始化失败: {e}")
            return False
            
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 检查资金费率数据是否完整
            if not await self._check_funding_data(symbol):
                return None
                
            # 寻找资金费率差异机会
            opportunity = await self._find_funding_opportunity(symbol)
            if not opportunity:
                return None
                
            # 验证交易量
            if not await self._validate_volume(symbol, opportunity):
                return None
                
            return {
                'symbol': symbol,
                'type': 'funding_arbitrage',
                'timestamp': datetime.utcnow(),
                'funding_data': opportunity,
                'next_funding_time': min(
                    time for time in self.next_funding_times[symbol].values()
                )
            }
            
        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            return None
            
    async def calculate_position_size(self, symbol: str, signal: Dict) -> Optional[Decimal]:
        """计算仓位大小"""
        try:
            # 获取可用资金
            available_balance = await self.risk_manager.get_available_balance()
            if not available_balance:
                return None
                
            # 计算预期收益
            funding_data = signal['funding_data']
            expected_return = funding_data['funding_diff']
            
            # 根据预期收益调整仓位
            if expected_return < self.min_funding_diff * Decimal('2'):
                position_ratio = Decimal('0.1')
            elif expected_return < self.min_funding_diff * Decimal('3'):
                position_ratio = Decimal('0.15')
            else:
                position_ratio = Decimal('0.2')
                
            # 计算基础仓位
            base_position = available_balance * position_ratio
            
            # 根据距离下次资金费率时间调整
            time_to_funding = (
                signal['next_funding_time'] - datetime.utcnow()
            ).total_seconds()
            if time_to_funding < 1800:  # 30分钟内
                base_position *= Decimal('1.2')
                
            # 确保符合最小交易金额
            min_notional = Decimal('5')
            return max(base_position, min_notional)
            
        except Exception as e:
            self.logger.error(f"计算仓位大小失败: {e}")
            return None
            
    async def _monitor_funding_rates(self):
        """监控资金费率"""
        while self.active:
            try:
                for symbol in self.exchange_manager.symbols:
                    # 更新资金费率数据
                    await self._update_funding_data(symbol)
                    
                    # 检查持仓是否需要平仓
                    positions = [
                        pos for pos in self.positions.values()
                        if pos['symbol'] == symbol
                    ]
                    for position in positions:
                        if await self._should_close_position(position):
                            await self.close_position(
                                position['id'],
                                'funding_condition_changed'
                            )
                            
                await asyncio.sleep(self.funding_check_interval)
                
            except Exception as e:
                self.logger.error(f"监控资金费率异常: {e}")
                await asyncio.sleep(5)
                
    async def _update_funding_data(self, symbol: str):
        """更新资金费率数据"""
        try:
            if symbol not in self.funding_rates:
                self.funding_rates[symbol] = {}
            if symbol not in self.next_funding_times:
                self.next_funding_times[symbol] = {}
                
            for exchange_name, exchange in self.exchange_manager.exchanges.items():
                # 获取资金费率
                funding_rate = await exchange.fetch_funding_rate(symbol)
                next_funding_time = await exchange.fetch_next_funding_time(symbol)
                
                if funding_rate is not None:
                    self.funding_rates[symbol][exchange_name] = Decimal(str(funding_rate))
                if next_funding_time:
                    self.next_funding_times[symbol][exchange_name] = next_funding_time
                    
        except Exception as e:
            self.logger.error(f"更新资金费率数据失败: {e}")
            
    async def _check_funding_data(self, symbol: str) -> bool:
        """检查资金费率数据是否完整"""
        try:
            if symbol not in self.funding_rates or symbol not in self.next_funding_times:
                return False
                
            # 检查是否所有交易所都有数据
            exchanges = self.exchange_manager.exchanges.keys()
            if not all(ex in self.funding_rates[symbol] for ex in exchanges):
                return False
            if not all(ex in self.next_funding_times[symbol] for ex in exchanges):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查资金费率数据失败: {e}")
            return False
            
    async def _find_funding_opportunity(self, symbol: str) -> Optional[Dict]:
        """寻找资金费率差异机会"""
        try:
            rates = self.funding_rates[symbol]
            
            # 找出最高和最低资金费率
            max_rate = max(rates.items(), key=lambda x: x[1])
            min_rate = min(rates.items(), key=lambda x: x[1])
            
            funding_diff = max_rate[1] - min_rate[1]
            
            # 检查是否满足最小差异要求
            if funding_diff > self.min_funding_diff:
                return {
                    'high_exchange': max_rate[0],
                    'low_exchange': min_rate[0],
                    'funding_diff': funding_diff,
                    'high_rate': max_rate[1],
                    'low_rate': min_rate[1]
                }
                
            return None
            
        except Exception as e:
            self.logger.error(f"寻找资金费率机会失败: {e}")
            return None
            
    async def _validate_volume(self, symbol: str, opportunity: Dict) -> bool:
        """验证交易量"""
        try:
            # 检查高费率交易所的成交量
            high_exchange = self.exchange_manager.exchanges[opportunity['high_exchange']]
            high_ticker = await high_exchange.fetch_ticker(symbol)
            
            # 检查低费率交易所的成交量
            low_exchange = self.exchange_manager.exchanges[opportunity['low_exchange']]
            low_ticker = await low_exchange.fetch_ticker(symbol)
            
            if not high_ticker or not low_ticker:
                return False
                
            # 验证24小时成交量
            high_volume = Decimal(str(high_ticker['quoteVolume']))
            low_volume = Decimal(str(low_ticker['quoteVolume']))
            
            return min(high_volume, low_volume) > self.min_volume
            
        except Exception as e:
            self.logger.error(f"验证交易量失败: {e}")
            return False
            
    async def _should_close_position(self, position: Dict) -> bool:
        """检查是否应该平仓"""
        try:
            # 检查持仓时间
            hold_time = (datetime.utcnow() - position['entry_time']).total_seconds()
            if hold_time > self.max_hold_time:
                return True
                
            # 检查资金费率差异是否仍然存在
            funding_data = position['signal']['funding_data']
            current_rates = self.funding_rates[position['symbol']]
            
            high_rate = current_rates[funding_data['high_exchange']]
            low_rate = current_rates[funding_data['low_exchange']]
            current_diff = high_rate - low_rate
            
            # 如果费率差异消失，平仓
            if current_diff < self.min_funding_diff:
                return True
                
            # 如果费率差异反转，平仓
            if current_diff < 0:
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"检查平仓条件失败: {e}")
            return False
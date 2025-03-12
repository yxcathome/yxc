from decimal import Decimal
from typing import Dict, Optional, List, Tuple
import asyncio
from datetime import datetime
import numpy as np
from strategies.base_strategy import BaseStrategy

class BounceStrategy(BaseStrategy):
    def __init__(self, exchange_manager, risk_manager):
        super().__init__("bounce_trading", exchange_manager, risk_manager)
        # 策略参数
        self.mean_period = 20         # 均值计算周期
        self.std_threshold = Decimal('2.0')  # 标准差阈值
        self.min_volume = Decimal('1000')    # 最小成交量要求
        self.min_profit = Decimal('0.008')   # 最小目标利润 0.8%
        self.max_hold_time = 1800    # 最大持仓时间（秒）
        
        # 均值回归参数
        self.mean_reversion_threshold = Decimal('0.6')  # 回归阈值
        self.profit_take_ratio = Decimal('0.7')        # 获利比例
        
        # 数据缓存
        self.price_data = {}
        self.mean_data = {}
        self.std_data = {}
        
    async def start(self):
        """启动策略"""
        self.active = True
        asyncio.create_task(self._data_collector())
        asyncio.create_task(self._mean_calculator())
        self.logger.info("均值回归策略启动")
        
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 检查数据充分性
            if not self._check_data_sufficient(symbol):
                return None
                
            # 获取当前价格与统计数据
            stats = await self._get_current_stats(symbol)
            if not stats:
                return None
                
            # 检测均值回归机会
            signal = await self._detect_reversion_opportunity(symbol, stats)
            if signal:
                # 验证交易量
                if await self._validate_volume(symbol):
                    signal['volume_validated'] = True
                    return signal
                    
            return None
            
        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            return None
            
    async def calculate_position_size(self, symbol: str, signal: Dict) -> Optional[Decimal]:
        """计算仓位大小"""
        try:
            available_balance = await self.risk_manager.get_available_balance()
            if not available_balance:
                return None
                
            # 基于偏离度计算仓位
            deviation = signal['deviation']
            volume_multiplier = Decimal('1.2') if signal.get('volume_validated') else Decimal('1.0')
            
            # 基础仓位
            base_size = available_balance * Decimal('0.1')  # 使用10%可用资金
            
            # 根据偏离度调整仓位
            if deviation < self.std_threshold * Decimal('1.2'):
                position_size = base_size * Decimal('0.6')
            elif deviation < self.std_threshold * Decimal('1.5'):
                position_size = base_size * Decimal('0.8')
            else:
                position_size = base_size
                
            # 应用成交量调整
            position_size *= volume_multiplier
            
            # 确保符合最小交易金额
            min_notional = Decimal('5')
            return max(position_size, min_notional)
            
        except Exception as e:
            self.logger.error(f"计算仓位大小失败: {e}")
            return None
            
    async def _data_collector(self):
        """收集市场数据"""
        while self.active:
            try:
                for exchange in self.exchange_manager.exchanges.values():
                    for symbol in exchange.markets:
                        # 获取K线数据
                        klines = await exchange.fetch_ohlcv(symbol, '1m', limit=30)
                        if not klines:
                            continue
                            
                        # 更新价格缓存
                        if symbol not in self.price_data:
                            self.price_data[symbol] = {
                                exchange.name: {
                                    'close': [],
                                    'high': [],
                                    'low': [],
                                    'volume': [],
                                    'timestamp': []
                                }
                            }
                        elif exchange.name not in self.price_data[symbol]:
                            self.price_data[symbol][exchange.name] = {
                                'close': [],
                                'high': [],
                                'low': [],
                                'volume': [],
                                'timestamp': []
                            }
                            
                        cache = self.price_data[symbol][exchange.name]
                        
                        # 更新数据
                        for kline in klines:
                            timestamp, _, high, low, close, volume = kline
                            cache['close'].append(Decimal(str(close)))
                            cache['high'].append(Decimal(str(high)))
                            cache['low'].append(Decimal(str(low)))
                            cache['volume'].append(Decimal(str(volume)))
                            cache['timestamp'].append(datetime.fromtimestamp(timestamp/1000))
                            
                        # 保持数据窗口大小
                        max_size = self.mean_period + 10
                        for key in cache:
                            cache[key] = cache[key][-max_size:]
                            
                await asyncio.sleep(30)  # 每30秒更新一次
                
            except Exception as e:
                self.logger.error(f"数据收集异常: {e}")
                await asyncio.sleep(5)
                
    async def _mean_calculator(self):
        """计算移动均值和标准差"""
        while self.active:
            try:
                for symbol in self.price_data:
                    for exchange_name, data in self.price_data[symbol].items():
                        if len(data['close']) < self.mean_period:
                            continue
                            
                        prices = np.array([float(p) for p in data['close'][-self.mean_period:]])
                        mean = Decimal(str(np.mean(prices)))
                        std = Decimal(str(np.std(prices)))
                        
                        if symbol not in self.mean_data:
                            self.mean_data[symbol] = {}
                        if symbol not in self.std_data:
                            self.std_data[symbol] = {}
                            
                        self.mean_data[symbol][exchange_name] = mean
                        self.std_data[symbol][exchange_name] = std
                        
                await asyncio.sleep(5)  # 每5秒更新一次
                
            except Exception as e:
                self.logger.error(f"均值计算异常: {e}")
                await asyncio.sleep(5)
                
    async def _get_current_stats(self, symbol: str) -> Optional[Dict]:
        """获取当前统计数据"""
        try:
            stats = {}
            for exchange_name in self.exchange_manager.exchanges:
                if (symbol in self.mean_data and 
                    exchange_name in self.mean_data[symbol] and
                    symbol in self.std_data and
                    exchange_name in self.std_data[symbol]):
                    
                    current_price = await self._get_current_price(symbol, exchange_name)
                    if not current_price:
                        continue
                        
                    mean = self.mean_data[symbol][exchange_name]
                    std = self.std_data[symbol][exchange_name]
                    
                    # 计算z-score
                    z_score = (current_price - mean) / std if std > 0 else 0
                    
                    stats[exchange_name] = {
                        'price': current_price,
                        'mean': mean,
                        'std': std,
                        'z_score': Decimal(str(z_score))
                    }
                    
            return stats if stats else None
            
        except Exception as e:
            self.logger.error(f"获取统计数据失败: {e}")
            return None
            
    async def _detect_reversion_opportunity(self, symbol: str, stats: Dict) -> Optional[Dict]:
        """检测均值回归机会"""
        try:
            opportunities = {}
            for exchange_name, stat in stats.items():
                z_score = stat['z_score']
                if abs(z_score) > self.std_threshold:
                    direction = 'buy' if z_score < 0 else 'sell'
                    target_price = stat['mean']
                    current_price = stat['price']
                    
                    # 计算预期盈利
                    if direction == 'buy':
                        expected_profit = (target_price - current_price) / current_price
                    else:
                        expected_profit = (current_price - target_price) / current_price
                        
                    if expected_profit > self.min_profit:
                        opportunities[exchange_name] = {
                            'direction': direction,
                            'deviation': abs(z_score),
                            'price': current_price,
                            'target': target_price,
                            'expected_profit': expected_profit
                        }
                        
            # 如果多个交易所都确认机会
            if len(opportunities) >= 2:
                directions = set(o['direction'] for o in opportunities.values())
                if len(directions) == 1:  # 方向一致
                    avg_deviation = sum(o['deviation'] for o in opportunities.values()) / len(opportunities)
                    return {
                        'symbol': symbol,
                        'type': 'mean_reversion',
                        'direction': list(directions)[0],
                        'deviation': avg_deviation,
                        'timestamp': datetime.utcnow(),
                        'exchanges': opportunities
                    }
                    
            return None
            
        except Exception as e:
            self.logger.error(f"检测均值回归机会失败: {e}")
            return None
            
    async def _validate_volume(self, symbol: str) -> bool:
        """验证交易量"""
        try:
            valid_count = 0
            for exchange_name, data in self.price_data.get(symbol, {}).items():
                if len(data['volume']) < 3:
                    continue
                    
                recent_volume = sum(data['volume'][-3:]) / 3
                if recent_volume > self.min_volume:
                    valid_count += 1
                    
            return valid_count >= 2  # 至少两个交易所满足条件
            
        except Exception as e:
            self.logger.error(f"验证交易量失败: {e}")
            return False
            
    async def _calculate_profit_target(self, symbol: str, position: Dict) -> Optional[Dict]:
        """计算止盈目标"""
        try:
            targets = {}
            for exchange_name, order in position['orders'].items():
                if exchange_name not in self.mean_data[symbol]:
                    continue
                    
                mean = self.mean_data[symbol][exchange_name]
                entry_price = Decimal(str(order['price']))
                
                if position['direction'] == 'buy':
                    price_diff = mean - entry_price
                    target = entry_price + (price_diff * self.profit_take_ratio)
                else:
                    price_diff = entry_price - mean
                    target = entry_price - (price_diff * self.profit_take_ratio)
                    
                targets[exchange_name] = target
                
            return targets if targets else None
            
        except Exception as e:
            self.logger.error(f"计算止盈目标失败: {e}")
            return None
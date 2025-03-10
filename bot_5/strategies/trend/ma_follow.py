from decimal import Decimal
from typing import Dict, Optional, List
import asyncio
from datetime import datetime
import numpy as np
from strategies.base_strategy import BaseStrategy

class MATrendStrategy(BaseStrategy):
    def __init__(self, exchange_manager, risk_manager):
        super().__init__("ma_trend", exchange_manager, risk_manager)
        # MA参数
        self.fast_ma = 5      # 快速MA周期
        self.slow_ma = 20     # 慢速MA周期
        self.volume_ma = 10   # 成交量MA周期
        
        # 趋势确认参数
        self.trend_confirm_periods = 3  # 趋势确认所需周期数
        self.min_trend_strength = Decimal('0.002')  # 最小趋势强度
        
        # 数据缓存
        self.price_cache = {}  # 价格缓存
        self.ma_cache = {}    # 均线缓存
        self.volume_cache = {}  # 成交量缓存
        
    async def start(self):
        """启动策略"""
        self.active = True
        asyncio.create_task(self._data_collector())
        self.logger.info("MA趋势策略启动")
        
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 检查数据是否足够
            if not self._check_data_sufficient(symbol):
                return None
                
            # 计算均线
            fast_ma = await self._calculate_ma(symbol, self.fast_ma)
            slow_ma = await self._calculate_ma(symbol, self.slow_ma)
            volume_ma = await self._calculate_volume_ma(symbol)
            
            if not all([fast_ma, slow_ma, volume_ma]):
                return None
                
            # 判断趋势
            trend_signal = await self._detect_trend(symbol, fast_ma, slow_ma, volume_ma)
            return trend_signal
            
        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            return None
            
    async def calculate_position_size(self, symbol: str, signal: Dict) -> Optional[Decimal]:
        """计算仓位大小"""
        try:
            available_balance = await self.risk_manager.get_available_balance()
            if not available_balance:
                return None
                
            # 基于趋势强度计算仓位
            trend_strength = signal['trend_strength']
            base_size = available_balance * Decimal('0.1')  # 使用10%可用资金
            
            # 根据趋势强度调整仓位
            if trend_strength < self.min_trend_strength * Decimal('1.5'):
                position_size = base_size * Decimal('0.5')
            elif trend_strength < self.min_trend_strength * Decimal('2.0'):
                position_size = base_size * Decimal('0.8')
            else:
                position_size = base_size
                
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
                        if symbol not in self.price_cache:
                            self.price_cache[symbol] = {
                                exchange.name: {
                                    'close': [],
                                    'volume': [],
                                    'timestamp': []
                                }
                            }
                        elif exchange.name not in self.price_cache[symbol]:
                            self.price_cache[symbol][exchange.name] = {
                                'close': [],
                                'volume': [],
                                'timestamp': []
                            }
                            
                        cache = self.price_cache[symbol][exchange.name]
                        
                        # 更新数据
                        for kline in klines:
                            timestamp, _, _, _, close, volume = kline
                            cache['close'].append(Decimal(str(close)))
                            cache['volume'].append(Decimal(str(volume)))
                            cache['timestamp'].append(datetime.fromtimestamp(timestamp/1000))
                            
                        # 保持数据窗口大小
                        max_size = max(self.slow_ma, self.volume_ma) + 10
                        if len(cache['close']) > max_size:
                            cache['close'] = cache['close'][-max_size:]
                            cache['volume'] = cache['volume'][-max_size:]
                            cache['timestamp'] = cache['timestamp'][-max_size:]
                            
                await asyncio.sleep(60)  # 每分钟更新一次
                
            except Exception as e:
                self.logger.error(f"数据收集异常: {e}")
                await asyncio.sleep(5)
                
    async def _calculate_ma(self, symbol: str, period: int) -> Optional[Dict[str, Decimal]]:
        """计算移动平均线"""
        try:
            ma_values = {}
            for exchange_name, data in self.price_cache.get(symbol, {}).items():
                if len(data['close']) < period:
                    continue
                    
                prices = np.array([float(p) for p in data['close']])
                ma = np.mean(prices[-period:])
                ma_values[exchange_name] = Decimal(str(ma))
                
            return ma_values if ma_values else None
            
        except Exception as e:
            self.logger.error(f"计算MA失败: {e}")
            return None
            
    async def _calculate_volume_ma(self, symbol: str) -> Optional[Dict[str, Decimal]]:
        """计算成交量移动平均线"""
        try:
            volume_ma_values = {}
            for exchange_name, data in self.price_cache.get(symbol, {}).items():
                if len(data['volume']) < self.volume_ma:
                    continue
                    
                volumes = np.array([float(v) for v in data['volume']])
                volume_ma = np.mean(volumes[-self.volume_ma:])
                volume_ma_values[exchange_name] = Decimal(str(volume_ma))
                
            return volume_ma_values if volume_ma_values else None
            
        except Exception as e:
            self.logger.error(f"计算成交量MA失败: {e}")
            return None
            
    async def _detect_trend(self, symbol: str, fast_ma: Dict, slow_ma: Dict, 
                          volume_ma: Dict) -> Optional[Dict]:
        """检测趋势"""
        try:
            trends = {}
            for exchange_name in fast_ma.keys():
                if exchange_name not in slow_ma or exchange_name not in volume_ma:
                    continue
                    
                fast = fast_ma[exchange_name]
                slow = slow_ma[exchange_name]
                vol = volume_ma[exchange_name]
                
                # 计算趋势强度
                trend_strength = abs(fast - slow) / slow
                
                # 判断趋势方向
                if trend_strength > self.min_trend_strength:
                    current_volume = self.price_cache[symbol][exchange_name]['volume'][-1]
                    
                    # 确认成交量放大
                    if current_volume > vol:
                        direction = 'buy' if fast > slow else 'sell'
                        trends[exchange_name] = {
                            'direction': direction,
                            'strength': trend_strength,
                            'volume_ratio': current_volume / vol
                        }
                        
            # 如果两个交易所趋势一致，生成信号
            if len(trends) >= 2 and len(set(t['direction'] for t in trends.values())) == 1:
                direction = list(trends.values())[0]['direction']
                avg_strength = sum(t['strength'] for t in trends.values()) / len(trends)
                
                return {
                    'symbol': symbol,
                    'type': 'ma_trend',
                    'direction': direction,
                    'trend_strength': avg_strength,
                    'timestamp': datetime.utcnow(),
                    'volume_confirmation': True,
                    'exchanges': trends
                }
                
            return None
            
        except Exception as e:
            self.logger.error(f"检测趋势失败: {e}")
            return None
            
    def _check_data_sufficient(self, symbol: str) -> bool:
        """检查数据是否足够"""
        try:
            if symbol not in self.price_cache:
                return False
                
            required_periods = max(self.slow_ma, self.volume_ma)
            
            for exchange_data in self.price_cache[symbol].values():
                if len(exchange_data['close']) < required_periods:
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"检查数据充分性失败: {e}")
            return False
            
    async def _update_stop_loss(self, symbol: str, position: Dict):
        """更新止损价格"""
        try:
            # 获取当前价格
            current_prices = {}
            for exchange in self.exchange_manager.exchanges.values():
                price_info = await exchange.get_best_price(symbol)
                if price_info:
                    current_prices[exchange.name] = (
                        price_info['bid'] if position['direction'] == 'buy' 
                        else price_info['ask']
                    )
                    
            if not current_prices:
                return
                
            # 计算新的止损价格
            entry_prices = {
                ex_name: Decimal(str(order['price']))
                for ex_name, order in position['orders'].items()
            }
            
            for exchange_name, current_price in current_prices.items():
                if exchange_name not in entry_prices:
                    continue
                    
                entry_price = entry_prices[exchange_name]
                
                if position['direction'] == 'buy':
                    profit = (current_price - entry_price) / entry_price
                    if profit > Decimal('0.01'):  # 1%盈利时更新止损
                        new_stop = current_price * Decimal('0.995')  # 设置0.5%回撤止损
                        if 'stop_loss' not in position or new_stop > position['stop_loss'][exchange_name]:
                            if 'stop_loss' not in position:
                                position['stop_loss'] = {}
                            position['stop_loss'][exchange_name] = new_stop
                            
                else:  # sell
                    profit = (entry_price - current_price) / entry_price
                    if profit > Decimal('0.01'):
                        new_stop = current_price * Decimal('1.005')
                        if 'stop_loss' not in position or new_stop < position['stop_loss'][exchange_name]:
                            if 'stop_loss' not in position:
                                position['stop_loss'] = {}
                            position['stop_loss'][exchange_name] = new_stop
                            
        except Exception as e:
            self.logger.error(f"更新止损价格失败: {e}")
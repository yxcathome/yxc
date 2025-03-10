from decimal import Decimal
from typing import Dict, Optional, List
import asyncio
from datetime import datetime
import numpy as np
from strategies.base_strategy import BaseStrategy

class BreakoutStrategy(BaseStrategy):
    def __init__(self, exchange_manager, risk_manager):
        super().__init__("breakout", exchange_manager, risk_manager)
        # 突破参数
        self.lookback_periods = 24   # 观察周期
        self.breakout_threshold = Decimal('0.02')  # 突破阈值 2%
        self.volume_threshold = Decimal('2.0')     # 成交量放大阈值
        self.confirmation_periods = 2  # 确认周期数
        
        # 止损参数
        self.initial_stop_loss = Decimal('0.015')  # 初始止损 1.5%
        self.trailing_stop = Decimal('0.01')       # 跟踪止损 1%
        
        # 数据缓存
        self.price_data = {}
        self.volume_data = {}
        self.range_cache = {}
        
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 检查数据充分性
            if not self._check_data_sufficient(symbol):
                return None
                
            # 计算价格区间
            ranges = await self._calculate_price_range(symbol)
            if not ranges:
                return None
                
            # 检测突破
            signal = await self._detect_breakout(symbol, ranges)
            if signal:
                # 确认成交量
                if await self._confirm_volume(symbol, signal['direction']):
                    signal['volume_confirmed'] = True
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
                
            # 基于突破强度计算仓位
            breakout_strength = signal['breakout_strength']
            volume_multiplier = Decimal('1.2') if signal.get('volume_confirmed') else Decimal('1.0')
            
            # 计算基础仓位
            base_size = available_balance * Decimal('0.12')  # 使用12%可用资金
            
            # 根据突破强度调整仓位
            if breakout_strength < self.breakout_threshold * Decimal('1.2'):
                position_size = base_size * Decimal('0.7')
            elif breakout_strength < self.breakout_threshold * Decimal('1.5'):
                position_size = base_size * Decimal('0.9')
            else:
                position_size = base_size
                
            # 应用成交量确认加成
            position_size *= volume_multiplier
            
            # 确保符合最小交易金额
            min_notional = Decimal('5')
            return max(position_size, min_notional)
            
        except Exception as e:
            self.logger.error(f"计算仓位大小失败: {e}")
            return None
            
    async def _calculate_price_range(self, symbol: str) -> Optional[Dict]:
        """计算价格区间"""
        try:
            ranges = {}
            for exchange_name, data in self.price_data.get(symbol, {}).items():
                if len(data['high']) < self.lookback_periods:
                    continue
                    
                highs = np.array([float(h) for h in data['high'][-self.lookback_periods:]])
                lows = np.array([float(l) for l in data['low'][-self.lookback_periods:]])
                
                resistance = Decimal(str(np.max(highs)))
                support = Decimal(str(np.min(lows)))
                mid_price = (resistance + support) / 2
                
                ranges[exchange_name] = {
                    'resistance': resistance,
                    'support': support,
                    'mid_price': mid_price,
                    'range_size': (resistance - support) / mid_price
                }
                
            return ranges if ranges else None
            
        except Exception as e:
            self.logger.error(f"计算价格区间失败: {e}")
            return None
            
    async def _detect_breakout(self, symbol: str, ranges: Dict) -> Optional[Dict]:
        """检测突破"""
        try:
            breakouts = {}
            for exchange_name, range_data in ranges.items():
                current_price = await self._get_current_price(symbol, exchange_name)
                if not current_price:
                    continue
                    
                resistance = range_data['resistance']
                support = range_data['support']
                
                # 计算突破强度
                if current_price > resistance:
                    strength = (current_price - resistance) / resistance
                    if strength > self.breakout_threshold:
                        breakouts[exchange_name] = {
                            'direction': 'buy',
                            'strength': strength,
                            'price': current_price,
                            'level': resistance
                        }
                elif current_price < support:
                    strength = (support - current_price) / support
                    if strength > self.breakout_threshold:
                        breakouts[exchange_name] = {
                            'direction': 'sell',
                            'strength': strength,
                            'price': current_price,
                            'level': support
                        }
                        
            # 如果多个交易所都确认突破
            if len(breakouts) >= 2:
                directions = set(b['direction'] for b in breakouts.values())
                if len(directions) == 1:  # 方向一致
                    avg_strength = sum(b['strength'] for b in breakouts.values()) / len(breakouts)
                    return {
                        'symbol': symbol,
                        'type': 'breakout',
                        'direction': list(directions)[0],
                        'breakout_strength': avg_strength,
                        'timestamp': datetime.utcnow(),
                        'exchanges': breakouts
                    }
                    
            return None
            
        except Exception as e:
            self.logger.error(f"检测突破失败: {e}")
            return None
            
    async def _confirm_volume(self, symbol: str, direction: str) -> bool:
        """确认成交量"""
        try:
            confirmations = 0
            for exchange_name, data in self.volume_data.get(symbol, {}).items():
                if len(data) < self.lookback_periods:
                    continue
                    
                recent_volume = np.mean([float(v) for v in data[-3:]])  # 最近3个周期平均成交量
                base_volume = np.mean([float(v) for v in data[-self.lookback_periods:-3]])  # 基准成交量
                
                if recent_volume > base_volume * float(self.volume_threshold):
                    confirmations += 1
                    
            return confirmations >= 2  # 至少两个交易所确认
            
        except Exception as e:
            self.logger.error(f"确认成交量失败: {e}")
            return False
            
    async def _get_current_price(self, symbol: str, exchange_name: str) -> Optional[Decimal]:
        """获取当前价格"""
        try:
            exchange = self.exchange_manager.exchanges[exchange_name]
            price_info = await exchange.get_best_price(symbol)
            if price_info:
                return (price_info['bid'] + price_info['ask']) / 2
            return None
            
        except Exception as e:
            self.logger.error(f"获取当前价格失败: {e}")
            return None
            
    async def _update_trailing_stop(self, symbol: str, position: Dict):
        """更新跟踪止损"""
        try:
            current_prices = {}
            for exchange_name in position['orders'].keys():
                price = await self._get_current_price(symbol, exchange_name)
                if price:
                    current_prices[exchange_name] = price
                    
            if not current_prices:
                return
                
            for exchange_name, current_price in current_prices.items():
                entry_price = Decimal(str(position['orders'][exchange_name]['price']))
                
                if position['direction'] == 'buy':
                    profit = (current_price - entry_price) / entry_price
                    if profit > self.trailing_stop:
                        new_stop = current_price * (1 - float(self.trailing_stop))
                        if 'trailing_stop' not in position:
                            position['trailing_stop'] = {}
                        if (exchange_name not in position['trailing_stop'] or 
                            new_stop > position['trailing_stop'][exchange_name]):
                            position['trailing_stop'][exchange_name] = Decimal(str(new_stop))
                            
                else:  # sell
                    profit = (entry_price - current_price) / entry_price
                    if profit > self.trailing_stop:
                        new_stop = current_price * (1 + float(self.trailing_stop))
                        if 'trailing_stop' not in position:
                            position['trailing_stop'] = {}
                        if (exchange_name not in position['trailing_stop'] or 
                            new_stop < position['trailing_stop'][exchange_name]):
                            position['trailing_stop'][exchange_name] = Decimal(str(new_stop))
                            
        except Exception as e:
            self.logger.error(f"更新跟踪止损失败: {e}")
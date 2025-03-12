import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from .strategy_base import StrategyBase
from config import Config

class BreakoutStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str):
        super().__init__(exchange_id, symbol)
        self.required_history = 100
        self.breakout_period = 20
        self.volume_threshold = 2.0  # 突破确认的成交量放大倍数
        self.volatility_filter = 0.02  # 最小波动率阈值
        
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算突破指标
            indicators = self._calculate_breakout_indicators(df)
            
            # 评估突破质量
            breakout_quality = self._evaluate_breakout_quality(df, indicators)
            
            current_price = df['close'].iloc[-1]
            signal = self._generate_breakout_signal(df, indicators, breakout_quality, current_price)
            
            self.logger.info(
                f"Breakout Signal - Price: {current_price:.2f}, "
                f"Breakout Score: {breakout_quality['breakout_score']:.2f}, "
                f"Level: {breakout_quality['breakout_level']:.2f}, "
                f"Volume Surge: {indicators['volume_surge']:.2f}, "
                f"Signal: {signal['action']}"
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating breakout signal: {str(e)}")
            raise
            
    def _calculate_breakout_indicators(self, df: pd.DataFrame) -> Dict:
        """
        计算突破相关指标
        """
        # 计算关键价格水平
        df['high_ma'] = df['high'].rolling(window=self.breakout_period).mean()
        df['low_ma'] = df['low'].rolling(window=self.breakout_period).mean()
        df['pivot'] = (df['high'] + df['low'] + df['close']) / 3
        
        # 计算波动性指标
        df['tr'] = self._calculate_true_range(df)
        df['atr'] = df['tr'].rolling(window=14).mean()
        df['atr_pct'] = df['atr'] / df['close']
        
        # 计算成交量指标
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_std'] = df['volume'].rolling(window=20).std()
        df['volume_z_score'] = (df['volume'] - df['volume_ma']) / df['volume_std']
        
        # 计算价格通道
        df['upper_channel'] = df['high'].rolling(window=self.breakout_period).max()
        df['lower_channel'] = df['low'].rolling(window=self.breakout_period).min()
        df['channel_width'] = df['upper_channel'] - df['lower_channel']
        
        # 计算动量指标
        df['momentum'] = df['close'].pct_change(5)
        df['momentum_ma'] = df['momentum'].rolling(window=10).mean()
        
        # 计算成交量压力
        df['volume_price_high'] = df['high'] * df['volume']
        df['volume_price_low'] = df['low'] * df['volume']
        df['volume_price_mean'] = (df['volume_price_high'] + df['volume_price_low']) / 2
        
        return {
            'upper_channel': df['upper_channel'].iloc[-1],
            'lower_channel': df['lower_channel'].iloc[-1],
            'channel_width': df['channel_width'].iloc[-1],
            'atr': df['atr'].iloc[-1],
            'atr_pct': df['atr_pct'].iloc[-1],
            'volume_surge': df['volume_z_score'].iloc[-1],
            'momentum': df['momentum'].iloc[-1],
            'momentum_ma': df['momentum_ma'].iloc[-1],
            'volume_pressure': df['volume_price_mean'].iloc[-1]
        }
        
    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """计算真实波幅"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        return ranges.max(axis=1)
        
    def _evaluate_breakout_quality(self, df: pd.DataFrame, 
                                 indicators: Dict) -> Dict:
        """
        评估突破质量
        """
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        
        # 判断突破方向
        if current_price > indicators['upper_channel']:
            breakout_direction = 1
            breakout_level = indicators['upper_channel']
        elif current_price < indicators['lower_channel']:
            breakout_direction = -1
            breakout_level = indicators['lower_channel']
        else:
            breakout_direction = 0
            breakout_level = current_price
            
        # 计算突破强度
        if breakout_direction != 0:
            price_movement = abs(current_price - breakout_level) / indicators['atr']
            volume_confirmation = max(indicators['volume_surge'], 0) / 2
            momentum_confirmation = (
                1 if np.sign(indicators['momentum']) == breakout_direction else -1
            )
            
            # 综合突破得分
            breakout_score = (
                (price_movement * 0.4) +
                (volume_confirmation * 0.4) +
                (momentum_confirmation * 0.2)
            )
        else:
            breakout_score = 0
            
        return {
            'breakout_direction': breakout_direction,
            'breakout_level': breakout_level,
            'breakout_score': breakout_score,
            'price_movement': price_movement if breakout_direction != 0 else 0,
            'volume_confirmation': volume_confirmation if breakout_direction != 0 else 0
        }
        
    def _generate_breakout_signal(self, df: pd.DataFrame, 
                                indicators: Dict, 
                                breakout_quality: Dict,
                                current_price: float) -> Dict:
        """
        生成突破交易信号
        """
        # 获取当前持仓
        current_position = self.get_position(self.symbol)
        
        # 检查是否需要平仓
        if current_position:
            if self._check_breakout_exit_conditions(current_position, 
                                                  indicators, 
                                                  breakout_quality,
                                                  current_price):
                return {
                    'action': 'close',
                    'price': current_price,
                    'reason': 'Breakout failure or target reached'
                }
        
        # 确认突破信号
        if breakout_quality['breakout_score'] > 1.5:  # 突破确认阈值
            if breakout_quality['breakout_direction'] > 0:
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Upward breakout confirmed',
                    'score': breakout_quality['breakout_score'],
                    'size_factor': min(breakout_quality['breakout_score'] / 3, 1)
                }
            elif breakout_quality['breakout_direction'] < 0:
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Downward breakout confirmed',
                    'score': breakout_quality['breakout_score'],
                    'size_factor': min(breakout_quality['breakout_score'] / 3, 1)
                }
        
        return {
            'action': 'hold',
            'price': current_price,
            'reason': 'No valid breakout signal'
        }
        
    def _check_breakout_exit_conditions(self, position: Dict, 
                                      indicators: Dict,
                                      breakout_quality: Dict,
                                      current_price: float) -> bool:
        """
        检查突破策略的平仓条件
        """
        entry_price = position['entry_price']
        
        # 计算移动止损
        atr_multiple = 2.0
        if position['side'] == 'buy':
            stop_level = max(
                entry_price - (indicators['atr'] * atr_multiple),
                current_price - (indicators['atr'] * atr_multiple)
            )
            if current_price < stop_level:
                return True
        else:
            stop_level = min(
                entry_price + (indicators['atr'] * atr_multiple),
                current_price + (indicators['atr'] * atr_multiple)
            )
            if current_price > stop_level:
                return True
                
        # 检查突破失败
        if (position['side'] == 'buy' and 
            current_price < breakout_quality['breakout_level']):
            return True
        if (position['side'] == 'sell' and 
            current_price > breakout_quality['breakout_level']):
            return True
            
        # 检查动量减弱
        if (position['side'] == 'buy' and 
            indicators['momentum'] < indicators['momentum_ma']):
            return True
        if (position['side'] == 'sell' and 
            indicators['momentum'] > indicators['momentum_ma']):
            return True
            
        return False
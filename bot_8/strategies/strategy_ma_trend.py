import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from .strategy_base import StrategyBase
from config import Config

class MATrendStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str):
        super().__init__(exchange_id, symbol)
        self.required_history = 100
        self.trend_confirmation_periods = 3
        self.volume_threshold = 1.5  # 成交量放大阈值
        
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算趋势指标
            indicators = self._calculate_trend_indicators(df)
            
            # 评估趋势质量
            trend_quality = self._evaluate_trend_quality(df, indicators)
            
            current_price = df['close'].iloc[-1]
            signal = self._generate_trend_signal(df, indicators, trend_quality, current_price)
            
            self.logger.info(
                f"MA Trend Signal - Price: {current_price:.2f}, "
                f"Trend Score: {trend_quality['trend_score']:.2f}, "
                f"Trend Strength: {indicators['trend_strength']:.2f}, "
                f"Signal: {signal['action']}, "
                f"Confidence: {signal.get('confidence', 0):.2f}"
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating trend signal: {str(e)}")
            raise
            
    def _calculate_trend_indicators(self, df: pd.DataFrame) -> Dict:
        """
        计算趋势相关指标
        """
        # 计算多周期均线
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # 计算趋势强度
        df['trend_strength'] = ((df['ema10'] - df['ema50']) / df['ema50'] * 100)
        
        # 计算价格动量
        df['momentum'] = df['close'].pct_change(10)
        
        # 计算波动率
        df['volatility'] = df['close'].pct_change().rolling(window=20).std() * np.sqrt(252)
        
        # MACD计算（不使用ta-lib）
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['signal_line']
        
        # 计算成交量趋势
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # ADX计算（使用简化版本）
        df['tr'] = self._calculate_true_range(df)
        df['dx'] = self._calculate_directional_index(df)
        df['adx'] = df['dx'].rolling(window=14).mean()
        
        return {
            'trend_strength': df['trend_strength'].iloc[-1],
            'momentum': df['momentum'].iloc[-1],
            'volatility': df['volatility'].iloc[-1],
            'macd': df['macd'].iloc[-1],
            'macd_hist': df['macd_hist'].iloc[-1],
            'volume_ratio': df['volume_ratio'].iloc[-1],
            'adx': df['adx'].iloc[-1],
            'ema_values': {
                'ema10': df['ema10'].iloc[-1],
                'ema20': df['ema20'].iloc[-1],
                'ema50': df['ema50'].iloc[-1]
            }
        }
        
    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """计算真实波幅"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        return ranges.max(axis=1)
        
    def _calculate_directional_index(self, df: pd.DataFrame) -> pd.Series:
        """计算方向指数"""
        up_move = df['high'] - df['high'].shift()
        down_move = df['low'].shift() - df['low']
        
        pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        tr14 = self._calculate_true_range(df).rolling(window=14).sum()
        pos_di14 = 100 * pd.Series(pos_dm).rolling(window=14).sum() / tr14
        neg_di14 = 100 * pd.Series(neg_dm).rolling(window=14).sum() / tr14
        
        dx = 100 * np.abs(pos_di14 - neg_di14) / (pos_di14 + neg_di14)
        return dx
        
    def _evaluate_trend_quality(self, df: pd.DataFrame, 
                              indicators: Dict) -> Dict:
        """
        评估趋势质量
        """
        # 趋势一致性检查
        ema_alignment = (
            indicators['ema_values']['ema10'] > indicators['ema_values']['ema20'] and
            indicators['ema_values']['ema20'] > indicators['ema_values']['ema50']
        )
        
        # 趋势强度评分
        trend_strength_score = min(abs(indicators['trend_strength']) / 20, 1)
        
        # ADX趋势强度
        adx_score = min(indicators['adx'] / 50, 1)
        
        # 成交量支持度
        volume_support = min(indicators['volume_ratio'] - 1, 1) if indicators['volume_ratio'] > 1 else 0
        
        # MACD动量
        macd_score = abs(indicators['macd_hist']) / df['close'].mean() * 100
        
        # 计算综合趋势得分
        trend_score = (
            (trend_strength_score * 0.3) +
            (adx_score * 0.3) +
            (volume_support * 0.2) +
            (macd_score * 0.2)
        ) * (1 if ema_alignment else 0.5)
        
        # 趋势方向
        trend_direction = np.sign(indicators['trend_strength'])
        
        return {
            'trend_score': trend_score,
            'trend_direction': trend_direction,
            'ema_alignment': ema_alignment,
            'volume_support': volume_support > 0.5
        }
        
    def _generate_trend_signal(self, df: pd.DataFrame, 
                             indicators: Dict, 
                             trend_quality: Dict,
                             current_price: float) -> Dict:
        """
        生成趋势交易信号
        """
        # 获取当前持仓
        current_position = self.get_position(self.symbol)
        
        # 检查是否需要平仓
        if current_position:
            if self._check_trend_exit_conditions(current_position, 
                                               indicators, 
                                               trend_quality):
                return {
                    'action': 'close',
                    'price': current_price,
                    'reason': 'Trend reversal or deterioration',
                    'confidence': trend_quality['trend_score']
                }
        
        # 开仓信号生成
        if trend_quality['trend_score'] > 0.7:  # 强趋势阈值
            if trend_quality['trend_direction'] > 0 and trend_quality['ema_alignment']:
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Strong uptrend detected',
                    'confidence': trend_quality['trend_score'],
                    'size_factor': min(trend_quality['trend_score'], 1)
                }
            elif trend_quality['trend_direction'] < 0 and not trend_quality['ema_alignment']:
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Strong downtrend detected',
                    'confidence': trend_quality['trend_score'],
                    'size_factor': min(trend_quality['trend_score'], 1)
                }
        
        return {
            'action': 'hold',
            'price': current_price,
            'reason': 'No clear trend signal',
            'confidence': trend_quality['trend_score']
        }
        
    def _check_trend_exit_conditions(self, position: Dict, 
                                   indicators: Dict, 
                                   trend_quality: Dict) -> bool:
        """
        检查趋势策略的平仓条件
        """
        # 趋势反转
        trend_reversal = (
            (position['side'] == 'buy' and trend_quality['trend_direction'] < 0) or
            (position['side'] == 'sell' and trend_quality['trend_direction'] > 0)
        )
        
        # 趋势强度减弱
        trend_weakening = trend_quality['trend_score'] < 0.3
        
        # MACD背离
        macd_divergence = (
            (position['side'] == 'buy' and indicators['macd_hist'] < 0) or
            (position['side'] == 'sell' and indicators['macd_hist'] > 0)
        )
        
        # 成交量支持减弱
        volume_weakening = not trend_quality['volume_support']
        
        return trend_reversal or (trend_weakening and macd_divergence) or \
               (trend_weakening and volume_weakening)
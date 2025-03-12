import numpy as np
import pandas as pd
from typing import Dict
from .strategy_base import StrategyBase
from config import Config

class MeanReversionStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str):
        super().__init__(exchange_id, symbol)
        self.required_history = 100
        self.entry_threshold = 2.0  # 标准差倍数
        self.exit_threshold = 0.5   # 回归至均值的比例
        
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算核心指标
            indicators = self._calculate_advanced_indicators(df)
            
            current_price = df['close'].iloc[-1]
            signal = self._evaluate_trading_conditions(df, indicators, current_price)
            
            # 记录信号生成的详细信息
            self.logger.info(
                f"Mean Reversion Signal - Price: {current_price:.2f}, "
                f"Upper: {indicators['upper_band']:.2f}, "
                f"Lower: {indicators['lower_band']:.2f}, "
                f"Mean: {indicators['mean']:.2f}, "
                f"Position Score: {indicators['position_score']:.2f}, "
                f"Signal: {signal['action']}"
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating mean reversion signal: {str(e)}")
            raise
            
    def _calculate_advanced_indicators(self, df: pd.DataFrame) -> Dict:
        """
        计算高级技术指标
        """
        # 自适应波动率周期
        volatility = df['close'].pct_change().std()
        lookback = int(20 * (1 + volatility))  # 根据波动率调整回看周期
        
        # 计算动态均值
        df['ema'] = df['close'].ewm(span=lookback, adjust=False).mean()
        df['std'] = df['close'].rolling(window=lookback).std()
        
        # 考虑成交量的价格压力
        volume_price_mean = (df['close'] * df['volume']).rolling(window=lookback).sum() / \
                           df['volume'].rolling(window=lookback).sum()
        
        # 计算布林带
        upper_band = df['ema'] + (self.entry_threshold * df['std'])
        lower_band = df['ema'] - (self.entry_threshold * df['std'])
        
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # 计算价格动量
        momentum = df['close'].diff(5) / df['close'].shift(5)
        
        # 计算成交量趋势
        volume_trend = df['volume'].rolling(window=20).mean() / \
                      df['volume'].rolling(window=50).mean()
        
        return {
            'upper_band': upper_band.iloc[-1],
            'lower_band': lower_band.iloc[-1],
            'mean': df['ema'].iloc[-1],
            'std': df['std'].iloc[-1],
            'volume_price_mean': volume_price_mean.iloc[-1],
            'rsi': rsi.iloc[-1],
            'momentum': momentum.iloc[-1],
            'volume_trend': volume_trend.iloc[-1],
            'position_score': self._calculate_position_score(df, rsi.iloc[-1], 
                                                          momentum.iloc[-1], 
                                                          volume_trend.iloc[-1])
        }
        
    def _calculate_position_score(self, df: pd.DataFrame, 
                                rsi: float, momentum: float, 
                                volume_trend: float) -> float:
        """
        计算仓位得分，用于确定开仓时机和仓位大小
        """
        # RSI权重
        rsi_score = (70 - rsi) / 30 if rsi > 70 else (30 - rsi) / 30 if rsi < 30 else 0
        
        # 动量权重
        momentum_score = -np.sign(momentum) * min(abs(momentum), 1)
        
        # 成交量趋势权重
        volume_score = 1 if volume_trend > 1.2 else -1 if volume_trend < 0.8 else 0
        
        # 价格波动率权重
        volatility = df['close'].pct_change().std() * np.sqrt(252)
        volatility_score = 1 - min(volatility * 10, 1)  # 波动率越低越好
        
        # 综合得分
        total_score = (
            rsi_score * 0.4 +
            momentum_score * 0.3 +
            volume_score * 0.2 +
            volatility_score * 0.1
        )
        
        return total_score
        
    def _evaluate_trading_conditions(self, df: pd.DataFrame, 
                                   indicators: Dict, 
                                   current_price: float) -> Dict:
        """
        评估交易条件并生成信号
        """
        position_score = indicators['position_score']
        
        # 检查现有仓位
        current_position = self.get_position(self.symbol)
        
        # 平仓条件检查
        if current_position:
            if self._check_exit_conditions(current_position, current_price, indicators):
                return {
                    'action': 'close',
                    'price': current_price,
                    'reason': 'Position exit conditions met'
                }
        
        # 开仓条件检查
        if abs(position_score) > 0.5:  # 仓位得分阈值
            if current_price > indicators['upper_band'] and position_score < 0:
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Price above upper band with negative score',
                    'size_factor': abs(position_score)
                }
            elif current_price < indicators['lower_band'] and position_score > 0:
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Price below lower band with positive score',
                    'size_factor': abs(position_score)
                }
        
        return {
            'action': 'hold',
            'price': current_price,
            'reason': 'No clear signal'
        }
        
    def _check_exit_conditions(self, position: Dict, 
                             current_price: float, 
                             indicators: Dict) -> bool:
        """
        检查平仓条件
        """
        # 计算当前收益率
        entry_price = position['entry_price']
        pnl_pct = (current_price - entry_price) / entry_price
        if position['side'] == 'sell':
            pnl_pct = -pnl_pct
            
        # 止损检查
        if pnl_pct < -Config.STOP_LOSS_PERCENTAGE:
            return True
            
        # 止盈检查
        if pnl_pct > Config.TAKE_PROFIT_PERCENTAGE:
            return True
            
        # 均值回归检查
        price_mean_diff = (current_price - indicators['mean']) / indicators['std']
        if abs(price_mean_diff) < self.exit_threshold:
            return True
            
        # 趋势反转检查
        if (position['side'] == 'buy' and indicators['position_score'] < -0.3) or \
           (position['side'] == 'sell' and indicators['position_score'] > 0.3):
            return True
            
        return False
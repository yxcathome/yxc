import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from .strategy_base import StrategyBase
from config import Config

class ArbitrageStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str):
        super().__init__(exchange_id, symbol)
        self.required_history = 50
        self.price_threshold = 0.002  # 价格偏离阈值
        self.min_profit_threshold = 0.003  # 最小利润阈值
        self.position_holding_time = 3600  # 最大持仓时间（秒）
        
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算套利指标
            indicators = self._calculate_arbitrage_indicators(df)
            
            # 评估套利机会
            arb_opportunity = self._evaluate_arbitrage_opportunity(df, indicators)
            
            current_price = df['close'].iloc[-1]
            signal = self._generate_arbitrage_signal(df, indicators, arb_opportunity, current_price)
            
            self.logger.info(
                f"Arbitrage Signal - Price: {current_price:.2f}, "
                f"Fair Value: {indicators['fair_value']:.2f}, "
                f"Deviation: {indicators['price_deviation']:.4f}, "
                f"Profit Score: {arb_opportunity['profit_score']:.4f}, "
                f"Signal: {signal['action']}"
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating arbitrage signal: {str(e)}")
            raise
            
    def _calculate_arbitrage_indicators(self, df: pd.DataFrame) -> Dict:
        """
        计算套利相关指标
        """
        # 计算VWAP
        df['vwap'] = (df['close'] * df['volume']).rolling(window=20).sum() / \
                     df['volume'].rolling(window=20).sum()
        
        # 计算价格均值和标准差
        df['price_ma'] = df['close'].rolling(window=20).mean()
        df['price_std'] = df['close'].rolling(window=20).std()
        df['z_score'] = (df['close'] - df['price_ma']) / df['price_std']
        
        # 计算价格波动率
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std() * np.sqrt(365 * 24)
        
        # 计算流动性指标
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['liquidity_score'] = df['volume'] / df['volume_ma']
        
        # 计算价格压力
        df['buying_pressure'] = (df['close'] - df['low']) / (df['high'] - df['low'])
        df['pressure_ma'] = df['buying_pressure'].rolling(window=20).mean()
        
        # 计算市场效率系数
        price_distance = abs(df['close'] - df['close'].shift(20))
        path_length = df['returns'].abs().rolling(window=20).sum()
        df['efficiency_ratio'] = price_distance / path_length
        
        current_price = df['close'].iloc[-1]
        fair_value = df['vwap'].iloc[-1]
        price_deviation = (current_price - fair_value) / fair_value
        
        return {
            'fair_value': fair_value,
            'price_deviation': price_deviation,
            'z_score': df['z_score'].iloc[-1],
            'volatility': df['volatility'].iloc[-1],
            'liquidity_score': df['liquidity_score'].iloc[-1],
            'buying_pressure': df['pressure_ma'].iloc[-1],
            'efficiency_ratio': df['efficiency_ratio'].iloc[-1],
            'vwap': df['vwap'].iloc[-1]
        }
        
    def _evaluate_arbitrage_opportunity(self, df: pd.DataFrame, 
                                     indicators: Dict) -> Dict:
        """
        评估套利机会质量
        """
        # 价格偏离度评分
        deviation_score = min(abs(indicators['price_deviation']) / self.price_threshold, 2.0)
        
        # 流动性评分
        liquidity_score = min(indicators['liquidity_score'], 2.0)
        
        # 波动率评分（低波动率更好）
        volatility_score = max(1 - indicators['volatility'] * 10, 0)
        
        # 市场效率评分（低效率市场更适合套利）
        efficiency_score = max(1 - indicators['efficiency_ratio'], 0)
        
        # 计算预期利润率
        expected_profit = abs(indicators['price_deviation']) - Config.FEE_RATE * 2
        profit_multiplier = max(expected_profit / self.min_profit_threshold, 0)
        
        # 综合评分
        opportunity_score = (
            deviation_score * 0.3 +
            liquidity_score * 0.2 +
            volatility_score * 0.2 +
            efficiency_score * 0.1 +
            profit_multiplier * 0.2
        )
        
        return {
            'opportunity_score': opportunity_score,
            'profit_score': profit_multiplier,
            'deviation_score': deviation_score,
            'liquidity_score': liquidity_score,
            'expected_profit': expected_profit
        }
        
    def _generate_arbitrage_signal(self, df: pd.DataFrame, 
                                 indicators: Dict,
                                 arb_opportunity: Dict,
                                 current_price: float) -> Dict:
        """
        生成套利交易信号
        """
        # 获取当前持仓
        current_position = self.get_position(self.symbol)
        
        # 检查是否需要平仓
        if current_position:
            if self._check_arbitrage_exit_conditions(current_position, 
                                                   indicators,
                                                   arb_opportunity,
                                                   current_price):
                return {
                    'action': 'close',
                    'price': current_price,
                    'reason': 'Arbitrage target reached or timeout'
                }
        
        # 生成开仓信号
        if arb_opportunity['opportunity_score'] > 1.0:
            if indicators['price_deviation'] > self.price_threshold:
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Price above fair value',
                    'score': arb_opportunity['opportunity_score'],
                    'size_factor': min(arb_opportunity['opportunity_score'] / 2, 1)
                }
            elif indicators['price_deviation'] < -self.price_threshold:
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Price below fair value',
                    'score': arb_opportunity['opportunity_score'],
                    'size_factor': min(arb_opportunity['opportunity_score'] / 2, 1)
                }
        
        return {
            'action': 'hold',
            'price': current_price,
            'reason': 'No valid arbitrage opportunity'
        }
        
    def _check_arbitrage_exit_conditions(self, position: Dict,
                                       indicators: Dict,
                                       arb_opportunity: Dict,
                                       current_price: float) -> bool:
        """
        检查套利策略的平仓条件
        """
        # 检查持仓时间
        holding_time = (datetime.utcnow() - position['entry_time']).total_seconds()
        if holding_time > self.position_holding_time:
            return True
            
        # 检查价格回归
        if position['side'] == 'buy':
            if current_price >= indicators['fair_value']:
                return True
        else:
            if current_price <= indicators['fair_value']:
                return True
                
        # 检查利润目标
        pnl_pct = (current_price - position['entry_price']) / position['entry_price']
        if position['side'] == 'sell':
            pnl_pct = -pnl_pct
            
        if pnl_pct >= self.min_profit_threshold:
            return True
            
        # 检查趋势反转
        if (position['side'] == 'buy' and indicators['buying_pressure'] < 0.3) or \
           (position['side'] == 'sell' and indicators['buying_pressure'] > 0.7):
            return True
            
        return False

    def _calculate_position_size(self, price: float, 
                               arb_opportunity: Dict) -> float:
        """
        计算套利仓位大小
        """
        # 基础仓位
        base_size = self.calculate_base_position_size(price)
        
        # 根据套利机会调整仓位
        opportunity_multiplier = min(arb_opportunity['opportunity_score'], 1.5)
        
        # 根据波动率调整仓位
        volatility_factor = max(1 - arb_opportunity['volatility_score'], 0.5)
        
        # 最终仓位
        position_size = base_size * opportunity_multiplier * volatility_factor
        
        return self.normalize_amount(position_size)
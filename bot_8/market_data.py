import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from config import Config
from logger import Logger

class MarketData:
    def __init__(self, exchange_id: str):
        self.logger = Logger("MarketData")
        self.exchange = getattr(ccxt, exchange_id)({
            'apiKey': Config.EXCHANGES[exchange_id].api_key,
            'secret': Config.EXCHANGES[exchange_id].api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.data_cache = {}
        self.last_update = {}
        
    def update_market_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """获取并更新市场数据"""
        try:
            current_time = datetime.now()
            if (symbol in self.last_update and 
                current_time - self.last_update[symbol] < timedelta(seconds=Config.MARKET_UPDATE_INTERVAL)):
                return self.data_cache[symbol][timeframe]

            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # 计算基础技术指标
            df = self.calculate_technical_indicators(df)
            
            if symbol not in self.data_cache:
                self.data_cache[symbol] = {}
            self.data_cache[symbol][timeframe] = df
            self.last_update[symbol] = current_time
            
            return df
        except Exception as e:
            self.logger.error(f"Error updating market data: {str(e)}")
            raise

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算关键技术指标"""
        # 价格动量指标
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log1p(df['returns'])
        
        # 波动率指标
        df['volatility'] = df['returns'].rolling(window=20).std() * np.sqrt(365 * 24)
        
        # VWAP计算
        df['vwap'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['vwap'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        # 自适应布林带
        df['ma20'] = df['close'].rolling(window=20).mean()
        volatility_factor = df['volatility'] / df['volatility'].rolling(window=100).mean()
        df['bb_std'] = df['close'].rolling(window=20).std() * volatility_factor
        df['bb_upper'] = df['ma20'] + (2 * df['bb_std'])
        df['bb_lower'] = df['ma20'] - (2 * df['bb_std'])
        
        # RSI优化版本
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 趋势强度指标
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['trend_strength'] = ((df['ema20'] - df['ema50']) / df['ema50'] * 100)
        
        # 成交量分析
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # OBV计算
        df['obv'] = (df['volume'] * np.where(df['close'] > df['close'].shift(1), 1, 
                                           np.where(df['close'] < df['close'].shift(1), -1, 0))).cumsum()
        
        # 动量指标
        df['momentum'] = df['close'] / df['close'].shift(10) - 1
        
        # 价格波动范围
        df['true_range'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            )
        )
        df['atr'] = df['true_range'].rolling(window=14).mean()
        
        return df

    def get_market_state(self, symbol: str) -> Tuple[MarketState, dict]:
        """
        深化的市场状态判断，结合多个指标
        """
        try:
            df = self.update_market_data(symbol, Config.BASE_TIMEFRAME)
            
            # 市场强度评分（0-100）
            market_strength = self._calculate_market_strength(df)
            
            # 趋势可靠性评分
            trend_reliability = self._calculate_trend_reliability(df)
            
            # 市场效率系数
            market_efficiency = self._calculate_market_efficiency(df)
            
            # 综合指标
            indicators = {
                'market_strength': market_strength,
                'trend_reliability': trend_reliability,
                'market_efficiency': market_efficiency,
                'volatility': df['volatility'].iloc[-1],
                'volume_ratio': df['volume_ratio'].iloc[-1],
                'rsi': df['rsi'].iloc[-1],
                'trend_strength': df['trend_strength'].iloc[-1]
            }
            
            # 市场状态判定
            if market_efficiency > 0.7 and trend_reliability > 0.65:
                state = MarketState.TRENDING
            elif market_strength < 30 and df['volatility'].iloc[-1] > df['volatility'].mean() * 1.5:
                state = MarketState.VOLATILE
            elif market_efficiency < 0.3 and trend_reliability < 0.4:
                state = MarketState.RANGING
            else:
                state = MarketState.SIDEWAYS
            
            return state, indicators
            
        except Exception as e:
            self.logger.error(f"Error determining market state: {str(e)}")
            raise

    def _calculate_market_strength(self, df: pd.DataFrame) -> float:
        """
        计算市场强度评分
        """
        # 价格动量
        price_momentum = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100
        
        # 成交量支撑
        volume_support = (df['volume_ratio'].iloc[-5:] > 1.2).sum() / 5
        
        # RSI趋势
        rsi_trend = 1 if df['rsi'].iloc[-1] > df['rsi'].iloc[-5:].mean() else 0
        
        # 趋势确认
        trend_confirm = (df['close'].iloc[-1] > df['ema20'].iloc[-1] and 
                        df['ema20'].iloc[-1] > df['ema50'].iloc[-1])
        
        # 综合评分
        strength_score = (
            price_momentum * 0.3 +
            volume_support * 30 +
            rsi_trend * 20 +
            trend_confirm * 20
        )
        
        return min(max(strength_score, 0), 100)

    def _calculate_trend_reliability(self, df: pd.DataFrame) -> float:
        """
        计算趋势可靠性
        """
        # 价格与移动平均线的关系
        price_ma_alignment = (
            (df['close'] > df['ema20']).rolling(window=10).mean().iloc[-1]
        )
        
        # 成交量支持度
        volume_support = (
            df['volume_ratio'].rolling(window=10).mean().iloc[-1]
        )
        
        # 趋势持续性
        trend_persistence = abs(
            df['trend_strength'].rolling(window=10).mean().iloc[-1]
        ) / 100
        
        # 综合评分
        reliability = (
            price_ma_alignment * 0.4 +
            volume_support * 0.3 +
            trend_persistence * 0.3
        )
        
        return min(max(reliability, 0), 1)

    def _calculate_market_efficiency(self, df: pd.DataFrame) -> float:
        """
        计算市场效率系数
        """
        # 计算实际价格路径长度
        price_path = np.sum(np.abs(df['returns'].iloc[-20:]))
        
        # 计算起点到终点的直线距离
        direct_path = abs(
            df['close'].iloc[-1] / df['close'].iloc[-20] - 1
        )
        
        # 效率系数 = 直线距离 / 实际路径
        if price_path == 0:
            return 0
            
        efficiency = direct_path / price_path
        return min(max(efficiency, 0), 1)

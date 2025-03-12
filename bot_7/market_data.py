import ccxt
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from config import Config, MarketState
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
        self.cached_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        self.last_update: Dict[str, datetime] = {}
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """
        获取K线数据
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV data: {str(e)}")
            raise
    
    def update_market_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        更新市场数据
        """
        current_time = datetime.now()
        if (symbol in self.last_update and 
            current_time - self.last_update[symbol] < timedelta(seconds=Config.MARKET_UPDATE_INTERVAL)):
            return self.cached_data[symbol][timeframe]
        
        df = self.fetch_ohlcv(symbol, timeframe)
        if symbol not in self.cached_data:
            self.cached_data[symbol] = {}
        self.cached_data[symbol][timeframe] = df
        self.last_update[symbol] = current_time
        return df
    
    def get_market_state(self, symbol: str) -> Tuple[MarketState, dict]:
        """
        判断市场状态
        """
        try:
            df = self.update_market_data(symbol, Config.BASE_TIMEFRAME)
            
            # 计算技术指标
            returns = df['close'].pct_change()
            volatility = returns.std() * np.sqrt(len(df))
            ma20 = df['close'].rolling(window=20).mean()
            ma50 = df['close'].rolling(window=50).mean()
            
            atr = self.calculate_atr(df)
            trend_strength = self.calculate_trend_strength(df)
            
            indicators = {
                'volatility': volatility,
                'trend_strength': trend_strength,
                'atr': atr,
                'ma20': ma20.iloc[-1],
                'ma50': ma50.iloc[-1]
            }
            
            # 判断市场状态
            if volatility > Config.VOLATILITY_THRESHOLD:
                return MarketState.VOLATILE, indicators
            elif trend_strength > Config.TREND_STRENGTH_THRESHOLD:
                return MarketState.TRENDING, indicators
            elif volatility < Config.VOLATILITY_THRESHOLD * 0.5:
                return MarketState.SIDEWAYS, indicators
            else:
                return MarketState.RANGING, indicators
                
        except Exception as e:
            self.logger.error(f"Error determining market state: {str(e)}")
            raise
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        计算ATR指标
        """
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(period).mean().iloc[-1]
        return atr
    
    def calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """
        计算趋势强度
        """
        ma20 = df['close'].rolling(window=20).mean()
        ma50 = df['close'].rolling(window=50).mean()
        trend_direction = np.sign(ma20.iloc[-1] - ma50.iloc[-1])
        price_above_ma = (df['close'] > ma20).sum() / len(df)
        return abs(price_above_ma - 0.5) * 2 * trend_direction
    
    def get_current_price(self, symbol: str) -> float:
        """
        获取当前价格
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            self.logger.error(f"Error fetching current price: {str(e)}")
            raise
    
    def get_orderbook(self, symbol: str) -> dict:
        """
        获取订单簿数据
        """
        try:
            return self.exchange.fetch_order_book(symbol)
        except Exception as e:
            self.logger.error(f"Error fetching orderbook: {str(e)}")
            raise
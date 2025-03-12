import numpy as np
import pandas as pd
from .strategy_base import StrategyBase
from config import Config

class BreakoutStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str, 
                 period: int = 20, threshold: float = 2.0):
        super().__init__(exchange_id, symbol)
        self.period = period
        self.threshold = threshold
    
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算ATR
            df['TR'] = pd.DataFrame({
                'HL': df['high'] - df['low'],
                'HC': abs(df['high'] - df['close'].shift(1)),
                'LC': abs(df['low'] - df['close'].shift(1))
            }).max(axis=1)
            df['ATR'] = df['TR'].rolling(window=self.period).mean()
            
            # 计算通道
            df['Upper'] = df['high'].rolling(window=self.period).max()
            df['Lower'] = df['low'].rolling(window=self.period).min()
            
            current_price = df['close'].iloc[-1]
            current_atr = df['ATR'].iloc[-1]
            
            # 判断突破
            if (current_price > df['Upper'].iloc[-2] + 
                self.threshold * current_atr):
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Upward breakout detected'
                }
            elif (current_price < df['Lower'].iloc[-2] - 
                  self.threshold * current_atr):
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Downward breakout detected'
                }
            else:
                return {
                    'action': 'hold',
                    'price': current_price,
                    'reason': 'No breakout detected'
                }
                
        except Exception as e:
            self.logger.error(f"Error generating breakout signal: {str(e)}")
            raise
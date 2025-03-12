import numpy as np
import pandas as pd
from .strategy_base import StrategyBase
from config import Config

class MATrendStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str, 
                 fast_period: int = 10, slow_period: int = 20):
        super().__init__(exchange_id, symbol)
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算快速和慢速均线
            df['FastMA'] = df['close'].rolling(window=self.fast_period).mean()
            df['SlowMA'] = df['close'].rolling(window=self.slow_period).mean()
            
            current_price = df['close'].iloc[-1]
            
            # 判断趋势方向
            if (df['FastMA'].iloc[-1] > df['SlowMA'].iloc[-1] and 
                df['FastMA'].iloc[-2] <= df['SlowMA'].iloc[-2]):
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Fast MA crossed above Slow MA'
                }
            elif (df['FastMA'].iloc[-1] < df['SlowMA'].iloc[-1] and 
                  df['FastMA'].iloc[-2] >= df['SlowMA'].iloc[-2]):
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Fast MA crossed below Slow MA'
                }
            else:
                return {
                    'action': 'hold',
                    'price': current_price,
                    'reason': 'No MA crossover'
                }
                
        except Exception as e:
            self.logger.error(f"Error generating MA trend signal: {str(e)}")
            raise
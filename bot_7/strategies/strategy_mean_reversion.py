import numpy as np
import pandas as pd
from .strategy_base import StrategyBase
from config import Config

class MeanReversionStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str, 
                 period: int = 20, std_dev: float = 2.0):
        super().__init__(exchange_id, symbol)
        self.period = period
        self.std_dev = std_dev
    
    def generate_signal(self) -> dict:
        try:
            df = self.market_data.update_market_data(self.symbol, Config.BASE_TIMEFRAME)
            
            # 计算布林带
            df['MA'] = df['close'].rolling(window=self.period).mean()
            df['STD'] = df['close'].rolling(window=self.period).std()
            df['Upper'] = df['MA'] + (self.std_dev * df['STD'])
            df['Lower'] = df['MA'] - (self.std_dev * df['STD'])
            
            current_price = df['close'].iloc[-1]
            
            if current_price < df['Lower'].iloc[-1]:
                return {
                    'action': 'buy',
                    'price': current_price,
                    'reason': 'Price below lower Bollinger Band'
                }
            elif current_price > df['Upper'].iloc[-1]:
                return {
                    'action': 'sell',
                    'price': current_price,
                    'reason': 'Price above upper Bollinger Band'
                }
            else:
                return {
                    'action': 'hold',
                    'price': current_price,
                    'reason': 'Price within Bollinger Bands'
                }
                
        except Exception as e:
            self.logger.error(f"Error generating mean reversion signal: {str(e)}")
            raise
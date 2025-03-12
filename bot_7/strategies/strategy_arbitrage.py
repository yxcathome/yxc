import numpy as np
from .strategy_base import StrategyBase
from config import Config

class ArbitrageStrategy(StrategyBase):
    def __init__(self, exchange_id: str, symbol: str, 
                 min_spread: float = 0.002):
        super().__init__(exchange_id, symbol)
        self.min_spread = min_spread
    
    def generate_signal(self) -> dict:
        try:
            orderbook = self.market_data.get_orderbook(self.symbol)
            
            best_bid = orderbook['bids'][0][0]
            best_ask = orderbook['asks'][0][0]
            spread = (best_ask - best_bid) / best_bid
            
            current_price = (best_bid + best_ask) / 2
            
            if spread > self.min_spread:
                # 检查价格趋势
                df = self.market_data.update_market_data(
                    self.symbol, Config.BASE_TIMEFRAME
                )
                price_trend = (
                    df['close'].iloc[-1] - df['close'].iloc[-5]
                ) / df['close'].iloc[-5]
                
                if price_trend > 0:
                    return {
                        'action': 'buy',
                        'price': current_price,
                        'reason': f'Large spread ({spread:.4f}) with upward trend'
                    }
                elif price_trend < 0:
                    return {
                        'action': 'sell',
                        'price': current_price,
                        'reason': f'Large spread ({spread:.4f}) with downward trend'
                    }
            
            return {
                'action': 'hold',
                'price': current_price,
                'reason': f'Insufficient spread ({spread:.4f})'
            }
            
        except Exception as e:
            self.logger.error(f"Error generating arbitrage signal: {str(e)}")
            raise
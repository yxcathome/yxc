from typing import List, Dict, Tuple
import pandas as pd
import numpy as np
from config import Config
from logger import Logger
from market_data import MarketData

class CoinSelector:
    def __init__(self, exchange_id: str):
        self.logger = Logger("CoinSelector")
        self.market_data = MarketData(exchange_id)
        
    def select_coins(self, max_coins: int = 3) -> List[str]:
        """
        根据多个指标选择合适的交易币对
        """
        try:
            coin_metrics = []
            
            for symbol in Config.TRADING_PAIRS:
                try:
                    metrics = self._calculate_coin_metrics(symbol)
                    coin_metrics.append({
                        'symbol': symbol,
                        **metrics
                    })
                except Exception as e:
                    self.logger.warning(f"Error calculating metrics for {symbol}: {str(e)}")
                    continue
            
            if not coin_metrics:
                self.logger.warning("No valid coins found for selection")
                return []
            
            # 转换为DataFrame进行排序
            df = pd.DataFrame(coin_metrics)
            
            # 根据综合得分排序
            df['total_score'] = (
                df['volume_score'] * 0.3 +
                df['volatility_score'] * 0.3 +
                df['liquidity_score'] * 0.4
            )
            
            selected_coins = df.nlargest(max_coins, 'total_score')['symbol'].tolist()
            
            self.logger.info(f"Selected coins: {selected_coins}")
            return selected_coins
            
        except Exception as e:
            self.logger.error(f"Error in coin selection: {str(e)}")
            return []
    
    def _calculate_coin_metrics(self, symbol: str) -> Dict[str, float]:
        """
        计算币对的各项指标
        """
        df = self.market_data.update_market_data(symbol, Config.BASE_TIMEFRAME)
        
        # 计算成交量得分
        volume = df['volume'].mean()
        volume_std = df['volume'].std()
        volume_score = volume / (volume_std + 1e-8)
        
        # 计算波动性得分
        returns = df['close'].pct_change()
        volatility = returns.std() * np.sqrt(len(df))
        volatility_score = volatility
        
        # 计算流动性得分
        orderbook = self.market_data.get_orderbook(symbol)
        spread = (orderbook['asks'][0][0] - orderbook['bids'][0][0]) / orderbook['bids'][0][0]
        liquidity_score = 1 / (spread + 1e-8)
        
        return {
            'volume_score': volume_score,
            'volatility_score': volatility_score,
            'liquidity_score': liquidity_score
        }
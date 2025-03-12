from typing import Optional, Dict
import ccxt
from config import Config, ExchangeConfig
from logger import Logger

class ExchangeSelector:
    def __init__(self):
        self.logger = Logger("ExchangeSelector")
        self._exchanges = {}
        
    def select_exchange(self) -> Tuple[str, ExchangeConfig]:
        """
        选择最适合的交易所
        """
        try:
            exchange_scores = {}
            
            for exchange_id, config in Config.EXCHANGES.items():
                try:
                    score = self._evaluate_exchange(exchange_id, config)
                    exchange_scores[exchange_id] = score
                except Exception as e:
                    self.logger.warning(f"Error evaluating exchange {exchange_id}: {str(e)}")
                    continue
            
            if not exchange_scores:
                raise Exception("No viable exchanges found")
            
            # 选择得分最高的交易所
            selected_exchange = max(exchange_scores.items(), key=lambda x: x[1])[0]
            
            self.logger.info(f"Selected exchange: {selected_exchange}")
            return selected_exchange, Config.EXCHANGES[selected_exchange]
            
        except Exception as e:
            self.logger.error(f"Error in exchange selection: {str(e)}")
            raise
    
    def _evaluate_exchange(self, exchange_id: str, config: ExchangeConfig) -> float:
        """
        评估交易所的各项指标
        """
        exchange = self._get_exchange(exchange_id, config)
        
        # 检查API连接
        exchange.fetch_balance()
        
        # 评分标准
        fee_score = 1 - (config.taker_fee * 2)  # 手续费得分
        
        # 检查交易对支持情况
        markets = exchange.fetch_markets()
        supported_pairs = sum(1 for pair in Config.TRADING_PAIRS 
                            if any(m['symbol'] == pair for m in markets))
        pair_support_score = supported_pairs / len(Config.TRADING_PAIRS)
        
        # 获取最近的交易所状态
        status = exchange.fetch_status()
        stability_score = 1.0 if status['status'] == 'ok' else 0.0
        
        # 计算综合得分
        total_score = (
            fee_score * 0.3 +
            pair_support_score * 0.4 +
            stability_score * 0.3
        )
        
        return total_score
    
    def _get_exchange(self, exchange_id: str, config: ExchangeConfig) -> ccxt.Exchange:
        """
        获取或创建交易所实例
        """
        if exchange_id not in self._exchanges:
            self._exchanges[exchange_id] = getattr(ccxt, exchange_id)({
                'apiKey': config.api_key,
                'secret': config.api_secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
        return self._exchanges[exchange_id]
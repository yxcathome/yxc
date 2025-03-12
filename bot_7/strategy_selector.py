from typing import Type
from config import Config, MarketState
from logger import Logger
from market_data import MarketData
from strategies.strategy_base import StrategyBase
from strategies.strategy_mean_reversion import MeanReversionStrategy
from strategies.strategy_ma_trend import MATrendStrategy
from strategies.strategy_breakout import BreakoutStrategy
from strategies.strategy_arbitrage import ArbitrageStrategy

class StrategySelector:
    def __init__(self, exchange_id: str):
        self.logger = Logger("StrategySelector")
        self.market_data = MarketData(exchange_id)
        self.current_strategy = None
        self.strategy_map = {
            MarketState.RANGING: MeanReversionStrategy,
            MarketState.TRENDING: MATrendStrategy,
            MarketState.VOLATILE: BreakoutStrategy,
            MarketState.SIDEWAYS: ArbitrageStrategy
        }
    
    def select_strategy(self, symbol: str) -> Type[StrategyBase]:
        """
        根据市场状态选择适当的策略
        """
        try:
            market_state, indicators = self.market_data.get_market_state(symbol)
            
            strategy_class = self.strategy_map[market_state]
            
            if (self.current_strategy is None or 
                not isinstance(self.current_strategy, strategy_class)):
                
                self.logger.info(
                    f"Switching strategy to {strategy_class.__name__} "
                    f"based on market state: {market_state.value}"
                )
                self.logger.market_log(
                    market_state.value,
                    indicators
                )
                
                self.current_strategy = strategy_class
            
            return self.current_strategy
            
        except Exception as e:
            self.logger.error(f"Error in strategy selection: {str(e)}")
            raise
    
    def get_strategy_parameters(self, strategy_class: Type[StrategyBase]) -> dict:
        """
        获取策略参数
        """
        try:
            if strategy_class == MeanReversionStrategy:
                return {
                    'period': Config.MEAN_REVERSION_PERIOD,
                    'std_dev': Config.MEAN_REVERSION_STD
                }
            elif strategy_class == MATrendStrategy:
                return {
                    'fast_period': Config.FAST_MA_PERIOD,
                    'slow_period': Config.SLOW_MA_PERIOD
                }
            elif strategy_class == BreakoutStrategy:
                return {
                    'period': Config.BREAKOUT_PERIOD,
                    'threshold': Config.BREAKOUT_THRESHOLD
                }
            elif strategy_class == ArbitrageStrategy:
                return {
                    'min_spread': Config.MIN_ARBITRAGE_SPREAD
                }
            else:
                raise ValueError(f"Unknown strategy class: {strategy_class.__name__}")
                
        except Exception as e:
            self.logger.error(f"Error getting strategy parameters: {str(e)}")
            raise
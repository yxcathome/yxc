import time
import sys
import signal
from typing import Dict, Optional
from config import Config
from logger import Logger
from market_data import MarketData
from coin_selector import CoinSelector
from exchange_selector import ExchangeSelector
from strategy_selector import StrategySelector
from position_manager import PositionManager
from risk_manager import RiskManager

class TradingBot:
    def __init__(self):
        self.logger = Logger("TradingBot")
        self.running = True
        self.setup_signal_handlers()
        
        try:
            # 初始化交易所选择器
            exchange_selector = ExchangeSelector()
            self.exchange_id, self.exchange_config = exchange_selector.select_exchange()
            
            # 初始化其他组件
            self.coin_selector = CoinSelector(self.exchange_id)
            self.strategy_selector = StrategySelector(self.exchange_id)
            self.position_manager = PositionManager(self.exchange_id)
            self.risk_manager = RiskManager(self.exchange_id)
            
            self.logger.info(f"Trading bot initialized with exchange: {self.exchange_id}")
            
        except Exception as e:
            self.logger.critical(f"Failed to initialize trading bot: {str(e)}")
            sys.exit(1)
    
    def setup_signal_handlers(self):
        """
        设置信号处理器以优雅地处理终止信号
        """
        def signal_handler(signum, frame):
            self.logger.info("Received termination signal. Closing positions...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def execute_trades(self, symbol: str, strategy_class) -> bool:
        """
        执行交易逻辑
        """
        try:
            # 实例化策略
            strategy = strategy_class(self.exchange_id, symbol)
            params = self.strategy_selector.get_strategy_parameters(strategy_class)
            for key, value in params.items():
                setattr(strategy, key, value)
            
            # 获取交易信号
            signal = strategy.generate_signal()
            
            current_position = self.position_manager.get_position(symbol)
            
            # 根据信号执行交易
            if signal['action'] != 'hold':
                # 检查是否需要平仓
                if current_position:
                    if ((signal['action'] == 'buy' and current_position['side'] == 'sell') or
                        (signal['action'] == 'sell' and current_position['side'] == 'buy')):
                        self.position_manager.close_position(
                            symbol,
                            f"Signal reversed: {signal['reason']}"
                        )
                
                # 开新仓
                if not current_position:
                    amount = strategy.get_position_size(signal['price'])
                    self.position_manager.open_position(
                        symbol,
                        signal['action'],
                        amount,
                        signal['price']
                    )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error executing trades: {str(e)}")
            return False
    
    def run(self):
        """
        运行交易机器人
        """
        self.logger.info("Starting trading bot...")
        
        last_coin_selection = 0
        selected_coins = []
        
        while self.running:
            try:
                current_time = time.time()
                
                # 每小时重新选择交易对
                if current_time - last_coin_selection > 3600:
                    selected_coins = self.coin_selector.select_coins(
                        max_coins=Config.MAX_POSITIONS
                    )
                    last_coin_selection = current_time
                    self.logger.info(f"Selected trading pairs: {selected_coins}")
                
                # 检查账户风险
                if not self.risk_manager.check_account_risk():
                    self.logger.warning("Account risk check failed")
                    time.sleep(60)  # 等待一分钟后重试
                    continue
                
                # 遍历选中的交易对
                for symbol in selected_coins:
                    try:
                        # 检查市场风险
                        if not self.risk_manager.check_market_risk(symbol):
                            self.logger.warning(f"Market risk check failed for {symbol}")
                            continue
                        
                        # 检查持仓风险
                        if not self.risk_manager.check_position(symbol):
                            self.logger.warning(f"Position risk check failed for {symbol}")
                            continue
                        
                        # 选择策略
                        strategy_class = self.strategy_selector.select_strategy(symbol)
                        
                        # 执行交易
                        self.execute_trades(symbol, strategy_class)
                        
                    except Exception as e:
                        self.logger.error(f"Error processing {symbol}: {str(e)}")
                        continue
                
                # 休眠以控制循环频率
                time.sleep(Config.MARKET_UPDATE_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {str(e)}")
                time.sleep(60)  # 发生错误时等待较长时间
    
    def shutdown(self):
        """
        关闭交易机器人
        """
        self.logger.info("Shutting down trading bot...")
        self.running = False
        
        # 关闭所有持仓
        for symbol in list(self.position_manager.positions.keys()):
            self.position_manager.close_position(symbol, "Bot shutdown")
        
        self.logger.info("Trading bot shutdown completed")

if __name__ == "__main__":
    bot = TradingBot()
    try:
        bot.run()
    except Exception as e:
        bot.logger.critical(f"Fatal error: {str(e)}")
    finally:
        bot.shutdown()
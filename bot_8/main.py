import sys
import signal
import time
from datetime import datetime, timezone
import threading
from typing import Dict, Optional
import json
import queue

from market_data import MarketData
from order_manager import OrderManager
from risk_manager import RiskManager
from position_manager import PositionManager
from strategies.strategy_mean_reversion import MeanReversionStrategy
from strategies.strategy_ma_trend import MATrendStrategy
from strategies.strategy_breakout import BreakoutStrategy
from strategies.strategy_arbitrage import ArbitrageStrategy
from data_storage import DataStorage
from logger import Logger
from config import Config

class TradingSystem:
    def __init__(self):
        self.logger = Logger("TradingSystem")
        self.running = True
        self.initialized = False
        
        # 初始化数据存储
        self.data_storage = DataStorage()
        
        # 初始化消息队列
        self.message_queue = queue.Queue()
        
        try:
            # 初始化各个组件
            self._initialize_components()
            
            # 设置信号处理
            self._setup_signal_handlers()
            
            # 启动监控线程
            self._start_monitor_threads()
            
            self.initialized = True
            self.logger.info("Trading system initialized successfully")
            
        except Exception as e:
            self.logger.critical(f"Failed to initialize trading system: {str(e)}")
            self.shutdown()
            sys.exit(1)
            
    def _initialize_components(self):
        """初始化交易系统组件"""
        try:
            # 市场数据模块
            self.market_data = MarketData(Config.PRIMARY_EXCHANGE)
            
            # 订单管理模块
            self.order_manager = OrderManager(Config.PRIMARY_EXCHANGE)
            
            # 风控模块
            self.risk_manager = RiskManager(Config.PRIMARY_EXCHANGE)
            
            # 仓位管理模块
            self.position_manager = PositionManager(Config.PRIMARY_EXCHANGE)
            
            # 策略实例化
            self.strategies = {
                'mean_reversion': MeanReversionStrategy(Config.PRIMARY_EXCHANGE, None),
                'ma_trend': MATrendStrategy(Config.PRIMARY_EXCHANGE, None),
                'breakout': BreakoutStrategy(Config.PRIMARY_EXCHANGE, None),
                'arbitrage': ArbitrageStrategy(Config.PRIMARY_EXCHANGE, None)
            }
            
            # 加载交易对配置
            self.trading_pairs = Config.TRADING_PAIRS
            
        except Exception as e:
            self.logger.error(f"Error initializing components: {str(e)}")
            raise
            
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info("Received termination signal")
            self.shutdown()
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
    def _start_monitor_threads(self):
        """启动监控线程"""
        # 市场数据更新线程
        threading.Thread(
            target=self._market_data_update_loop,
            daemon=True
        ).start()
        
        # 策略执行线程
        threading.Thread(
            target=self._strategy_execution_loop,
            daemon=True
        ).start()
        
        # 风控监控线程
        threading.Thread(
            target=self._risk_monitor_loop,
            daemon=True
        ).start()
        
        # 消息处理线程
        threading.Thread(
            target=self._message_processing_loop,
            daemon=True
        ).start()
        
    def _market_data_update_loop(self):
        """市场数据更新循环"""
        while self.running:
            try:
                for symbol in self.trading_pairs:
                    self.market_data.update_market_data(symbol, Config.BASE_TIMEFRAME)
                    
                time.sleep(Config.MARKET_UPDATE_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Error updating market data: {str(e)}")
                self.message_queue.put({
                    'type': 'error',
                    'component': 'market_data',
                    'message': str(e)
                })
                
    def _strategy_execution_loop(self):
        """策略执行循环"""
        while self.running:
            try:
                for symbol in self.trading_pairs:
                    # 获取市场状态
                    market_state = self.market_data.get_market_state(symbol)
                    
                    # 选择合适的策略
                    strategy = self._select_strategy(market_state)
                    
                    # 检查风控状态
                    if not self.risk_manager.check_trading_allowed(symbol):
                        continue
                        
                    # 生成交易信号
                    signal = strategy.generate_signal()
                    
                    # 执行交易
                    if signal['action'] != 'hold':
                        self._execute_trade(symbol, signal)
                        
                time.sleep(Config.STRATEGY_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Error in strategy execution: {str(e)}")
                self.message_queue.put({
                    'type': 'error',
                    'component': 'strategy',
                    'message': str(e)
                })
                
    def _risk_monitor_loop(self):
        """风控监控循环"""
        while self.running:
            try:
                # 检查账户风险
                account_risk = self.risk_manager.check_account_risk()
                
                # 检查持仓风险
                position_risk = self.risk_manager.check_position_risks()
                
                # 记录风险指标
                self.data_storage.save_risk_metrics({
                    'timestamp': datetime.now(timezone.utc),
                    'account_risk': account_risk,
                    'position_risk': position_risk
                })
                
                time.sleep(Config.RISK_CHECK_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Error in risk monitoring: {str(e)}")
                self.message_queue.put({
                    'type': 'error',
                    'component': 'risk',
                    'message': str(e)
                })
                
    def _message_processing_loop(self):
        """消息处理循环"""
        while self.running:
            try:
                message = self.message_queue.get(timeout=1)
                self._handle_message(message)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error processing message: {str(e)}")
                
    def _handle_message(self, message: Dict):
        """处理系统消息"""
        try:
            if message['type'] == 'error':
                self._handle_error_message(message)
            elif message['type'] == 'trade':
                self._handle_trade_message(message)
            elif message['type'] == 'risk':
                self._handle_risk_message(message)
        except Exception as e:
            self.logger.error(f"Error handling message: {str(e)}")
            
    def _select_strategy(self, market_state: str) -> object:
        """根据市场状态选择策略"""
        strategy_mapping = {
            'ranging': self.strategies['mean_reversion'],
            'trending': self.strategies['ma_trend'],
            'volatile': self.strategies['breakout'],
            'sideways': self.strategies['arbitrage']
        }
        return strategy_mapping.get(market_state, self.strategies['mean_reversion'])
        
    def _execute_trade(self, symbol: str, signal: Dict):
        """执行交易"""
        try:
            # 验证信号
            if not self._validate_signal(signal):
                return
                
            # 计算交易量
            amount = self.position_manager.calculate_position_size(
                symbol,
                signal['price'],
                signal.get('size_factor', 1.0)
            )
            
            # 检查风控限制
            if not self.risk_manager.check_position_risk(symbol, signal['action'], amount):
                return
                
            # 执行订单
            order = self.order_manager.place_order(
                symbol=symbol,
                order_type='market',
                side=signal['action'],
                amount=amount
            )
            
            # 记录交易
            self.data_storage.save_trade({
                'timestamp': datetime.now(timezone.utc),
                'symbol': symbol,
                'action': signal['action'],
                'amount': amount,
                'price': signal['price'],
                'order_id': order['id']
            })
            
        except Exception as e:
            self.logger.error(f"Error executing trade: {str(e)}")
            
    def _validate_signal(self, signal: Dict) -> bool:
        """验证交易信号"""
        required_fields = ['action', 'price']
        return all(field in signal for field in required_fields)
        
    def shutdown(self):
        """关闭交易系统"""
        self.logger.info("Shutting down trading system...")
        self.running = False
        
        try:
            # 关闭所有持仓
            self.position_manager.close_all_positions("System shutdown")
            
            # 取消所有未完成订单
            self.order_manager.cancel_all_orders()
            
            # 保存最终状态
            self._save_final_state()
            
            # 关闭数据存储连接
            self.data_storage.close()
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
            
        self.logger.info("Trading system shutdown completed")
        
    def _save_final_state(self):
        """保存系统最终状态"""
        final_state = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'positions': self.position_manager.get_all_positions(),
            'risk_metrics': self.risk_manager.get_risk_metrics(),
            'execution_stats': self.order_manager.get_execution_stats()
        }
        
        self.data_storage.save_system_state(final_state)
        
def main():
    trading_system = TradingSystem()
    
    if not trading_system.initialized:
        sys.exit(1)
        
    try:
        while trading_system.running:
            time.sleep(1)
    except KeyboardInterrupt:
        trading_system.shutdown()
        
if __name__ == "__main__":
    main()
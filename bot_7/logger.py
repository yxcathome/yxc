import logging
import sys
from logging.handlers import RotatingFileHandler
from config import Config

class Logger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.getLevelName(Config.LOG_LEVEL))
        
        if not self.logger.handlers:
            # 配置文件处理器
            file_handler = RotatingFileHandler(
                Config.LOG_FILE,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(logging.Formatter(Config.LOG_FORMAT))
            self.logger.addHandler(file_handler)
            
            # 配置控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(logging.Formatter(Config.LOG_FORMAT))
            self.logger.addHandler(console_handler)
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def critical(self, message: str):
        self.logger.critical(message)
    
    def trade_log(self, action: str, symbol: str, price: float, amount: float, 
                 side: str, order_type: str = "market"):
        """
        记录交易相关日志
        """
        message = (f"TRADE - {action.upper()} - {symbol} - {side.upper()} - "
                  f"Price: {price:.8f} - Amount: {amount:.8f} - Type: {order_type}")
        self.info(message)
    
    def strategy_log(self, strategy_name: str, action: str, details: str):
        """
        记录策略相关日志
        """
        message = f"STRATEGY - {strategy_name} - {action} - {details}"
        self.info(message)
    
    def market_log(self, market_state: str, indicators: dict):
        """
        记录市场状态相关日志
        """
        message = f"MARKET - State: {market_state} - Indicators: {indicators}"
        self.info(message)
    
    def risk_log(self, check_type: str, status: str, details: str):
        """
        记录风控相关日志
        """
        message = f"RISK - {check_type} - Status: {status} - {details}"
        self.info(message)
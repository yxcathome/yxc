import logging
import sys
from datetime import datetime
import os
import json
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Dict, Any
import threading

class Logger:
    _instances = {}
    _lock = threading.Lock()
    
    def __new__(cls, name: str):
        with cls._lock:
            if name not in cls._instances:
                cls._instances[name] = super().__new__(cls)
            return cls._instances[name]
            
    def __init__(self, name: str):
        if not hasattr(self, 'initialized'):
            self.name = name
            self.logger = logging.getLogger(name)
            self.logger.setLevel(logging.INFO)
            self.setup_handlers()
            self.initialized = True
            
    def setup_handlers(self):
        """设置日志处理器"""
        # 确保日志目录存在
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        
        # 文件处理器 (按大小rotating)
        file_handler = RotatingFileHandler(
            f"logs/{self.name}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        
        # 错误日志处理器 (按时间rotating)
        error_handler = TimedRotatingFileHandler(
            f"logs/{self.name}_error.log",
            when='midnight',
            interval=1,
            backupCount=7
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        
        # 性能日志处理器
        perf_handler = RotatingFileHandler(
            f"logs/{self.name}_performance.log",
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        perf_handler.setLevel(logging.INFO)
        perf_formatter = logging.Formatter(
            '%(asctime)s - %(message)s'
        )
        perf_handler.setFormatter(perf_formatter)
        
        # 添加处理器
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        self.performance_logger = perf_handler
        
    def info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)
        
    def error(self, message: str):
        """记录错误日志"""
        self.logger.error(message, exc_info=True)
        
    def warning(self, message: str):
        """记录警告日志"""
        self.logger.warning(message)
        
    def critical(self, message: str):
        """记录严重错误日志"""
        self.logger.critical(message, exc_info=True)
        
    def debug(self, message: str):
        """记录调试日志"""
        self.logger.debug(message)
        
    def log_performance(self, metrics: Dict[str, Any]):
        """记录性能指标"""
        try:
            metrics['timestamp'] = datetime.utcnow().isoformat()
            self.performance_logger.handle(
                logging.makeLogRecord({
                    'msg': json.dumps(metrics),
                    'levelname': 'INFO'
                })
            )
        except Exception as e:
            self.error(f"Error logging performance metrics: {str(e)}")
            
    def log_trade(self, trade_data: Dict):
        """记录交易信息"""
        try:
            trade_log = {
                'timestamp': datetime.utcnow().isoformat(),
                'trade': trade_data
            }
            self.logger.info(f"Trade executed: {json.dumps(trade_log)}")
        except Exception as e:
            self.error(f"Error logging trade: {str(e)}")
            
    def log_system_metrics(self, metrics: Dict):
        """记录系统指标"""
        try:
            metrics['timestamp'] = datetime.utcnow().isoformat()
            self.logger.info(f"System metrics: {json.dumps(metrics)}")
        except Exception as e:
            self.error(f"Error logging system metrics: {str(e)}")
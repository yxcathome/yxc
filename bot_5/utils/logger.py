import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

def setup_logger(name: str, level: str = 'INFO') -> logging.Logger:
    """设置日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))

    # 创建日志目录
    log_dir = os.path.join(os.path.dirname(__file__), '../logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 文件处理器
    log_file = os.path.join(log_dir, f'{name}_{datetime.now().strftime("%Y%m%d")}.log')
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(getattr(logging, level))

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level))

    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
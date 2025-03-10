import logging
import sys
from datetime import datetime
from pathlib import Path

def setup_logger(name='trading_bot'):
    # 创建logs目录
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 设置文件处理器
    log_file = log_dir / f"{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    
    # 设置控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # 设置logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def get_logger(name):
    return logging.getLogger(name)
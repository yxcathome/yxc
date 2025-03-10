import logging

def setup_logger():
    """
    配置日志格式及级别，返回 logger 对象。
    """
    logger = logging.getLogger()
    if not logger.handlers:
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(name)s: %(message)s')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

def get_logger(name):
    """
    为模块创建单独 logger
    """
    return logging.getLogger(name)
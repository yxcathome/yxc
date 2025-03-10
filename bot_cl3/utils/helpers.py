from decimal import Decimal
from typing import Union, Dict
import time
import json

def decimal_to_str(dec: Decimal) -> str:
    """将Decimal转换为字符串，去除尾随零"""
    return str(dec.normalize())

def format_number(num: Union[float, Decimal], decimals: int = 8) -> str:
    """格式化数字为指定精度的字符串"""
    return f"{float(num):.{decimals}f}"

def calculate_profit_percentage(entry: Decimal, exit: Decimal) -> Decimal:
    """计算利润百分比"""
    return (exit - entry) / entry * Decimal('100')

class JSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，支持Decimal"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def retry_on_exception(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        raise
                    await asyncio.sleep(delay * (i + 1))
        return wrapper
    return decorator
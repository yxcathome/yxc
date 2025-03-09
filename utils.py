import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

def to_decimal(value, _type: str):
    """安全转换函数，将值转换为Decimal类型"""
    if value is None:
        return Decimal('0')
    try:
        if isinstance(value, Decimal):
            return value
        value_str = str(value).strip()
        if not value_str:
            return Decimal('0')
        decimal_value = Decimal(value_str)
        if _type == 'price':
            return decimal_value
        else:
            return decimal_value.quantize(Decimal('1e-8'))
    except Exception as e:
        logger.error(f"数值转换失败: {value} | {str(e)}")
        return Decimal('0')
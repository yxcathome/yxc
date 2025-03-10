from abc import ABC, abstractmethod
from typing import Optional, Dict
import logging
from decimal import Decimal
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.name = "base"
        self.is_active = False
        self.min_profit = Decimal(str(config.get('min_profit_margin', '0.001')))

    @abstractmethod
    async def analyze(self, symbol: str) -> Optional[Dict]:
        """
        分析市场数据，寻找交易信号
        :param symbol: 交易对
        :return: 交易信号字典或None
        """
        pass

    @abstractmethod
    async def execute(self, signal: Dict) -> bool:
        """
        执行交易信号
        :param signal: 交易信号
        :return: 是否执行成功
        """
        pass

    def update_config(self, new_config: Dict) -> None:
        """
        更新策略配置
        :param new_config: 新的配置字典
        """
        self.config.update(new_config)
        self.min_profit = Decimal(str(self.config.get('min_profit_margin', '0.001')))

    async def validate_signal(self, signal: Dict) -> bool:
        """
        验证交易信号
        :param signal: 交易信号
        :return: 信号是否有效
        """
        try:
            required_fields = ['symbol', 'type']
            return all(field in signal for field in required_fields)
        except Exception as e:
            logger.error(f"信号验证失败: {e}")
            return False
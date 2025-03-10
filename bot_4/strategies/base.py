from abc import ABC, abstractmethod
from typing import Dict, Optional

class BaseStrategy(ABC):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.name = "base"
        self.is_active = True

    @abstractmethod
    async def analyze(self, symbol: str) -> Optional[Dict]:
        """
        分析指定交易对是否存在交易机会，返回信号字典或 None
        """
        pass

    @abstractmethod
    async def execute(self, signal: Dict) -> bool:
        """
        根据分析生成的信号执行交易，下单动作及补偿逻辑在此实现。
        返回交易是否成功
        """
        pass

    async def validate_signal(self, signal: Dict) -> bool:
        """
        校验信号有效性，默认返回 True，
        可在子类中覆写加入额外校验逻辑。
        """
        return True
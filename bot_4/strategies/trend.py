from decimal import Decimal
from typing import Optional, Dict
import logging
from .base import BaseStrategy

logger = logging.getLogger(__name__)

class TrendStrategy(BaseStrategy):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.name = "trend"
        self.is_active = config['enabled_strategies']['trend']
        # 添加 EMA 周期参数
        self.ema_period_short = 12
        self.ema_period_long = 26

    async def analyze(self, symbol: str) -> Optional[Dict]:
        try:
            # 获取 OKX 交易所的 K 线数据
            klines = await self.bot.exchanges['okx'].fetch_ohlcv(symbol, '1m', limit=100)
            closes = [Decimal(str(k[4])) for k in klines]

            # 计算短期和长期 EMA
            ema12 = self._calc_ema(closes, self.ema_period_short)
            ema26 = self._calc_ema(closes, self.ema_period_long)

            # 根据 EMA 交叉情况生成交易信号
            if ema12 > ema26 * Decimal('1.0015'):
                return {'action': 'long', 'symbol': symbol, 'confidence': (ema12 - ema26) / ema26}
            elif ema12 < ema26 * Decimal('0.9985'):
                return {'action': 'short', 'symbol': symbol, 'confidence': (ema26 - ema12) / ema26}
        except Exception as e:
            logger.error(f"趋势分析失败: {e}")
        return None

    def _calc_ema(self, closes, period):
        # 计算 EMA 的平滑系数
        alpha = Decimal(2) / (period + 1)
        ema = closes[0]
        # 迭代计算 EMA
        for price in closes[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema

    async def execute(self, signal: Dict) -> bool:
        """
        简单示例：直接返回 False
        """
        logger.info(f"Trend 策略执行，尚未实现详细下单逻辑。信号：{signal}")
        return False
from decimal import Decimal
from typing import Optional, Dict
import logging
from .base import BaseStrategy
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ArbitrageStrategy(BaseStrategy):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.name = "arbitrage"
        self.is_active = config['enabled_strategies']['arbitrage']
        self.min_spread = Decimal(str(config['arbitrage']['min_spread']))

    async def analyze(self, symbol: str) -> Optional[Dict]:
        try:
            # 获取两个交易所的订单簿
            okx_book = await self.bot.get_orderbook(self.bot.okx, symbol)
            binance_book = await self.bot.get_orderbook(self.bot.binance, symbol)
            
            if not okx_book or not binance_book:
                return None

            # 计算加权平均价格
            okx_bid = self._calculate_weighted_price(okx_book['bids'][:3])
            okx_ask = self._calculate_weighted_price(okx_book['asks'][:3])
            binance_bid = self._calculate_weighted_price(binance_book['bids'][:3])
            binance_ask = self._calculate_weighted_price(binance_book['asks'][:3])

            # 计算差价
            spread1 = (binance_bid - okx_ask) / okx_ask
            spread2 = (okx_bid - binance_ask) / binance_ask

            # 生成信号
            if spread1 > self.min_spread:
                return {
                    'type': 'arbitrage',
                    'direction': 'okx_to_binance',
                    'symbol': symbol,
                    'spread': float(spread1),
                    'entry_exchange': 'okx',
                    'exit_exchange': 'binance',
                    'entry_price': float(okx_ask),
                    'exit_price': float(binance_bid)
                }
            elif spread2 > self.min_spread:
                return {
                    'type': 'arbitrage',
                    'direction': 'binance_to_okx',
                    'symbol': symbol,
                    'spread': float(spread2),
                    'entry_exchange': 'binance',
                    'exit_exchange': 'okx',
                    'entry_price': float(binance_ask),
                    'exit_price': float(okx_bid)
                }

        except Exception as e:
            logger.error(f"套利分析异常: {e}")
        return None

    async def execute(self, signal: Dict) -> bool:
        try:
            if not await self.validate_signal(signal):
                return False

            symbol = signal['symbol']
            amount = self.bot.calculate_trade_amount(
                signal['entry_exchange'],
                Decimal(str(signal['entry_price']))
            )

            # 执行交易
            entry_exchange = self.bot.okx if signal['entry_exchange'] == 'okx' else self.bot.binance
            exit_exchange = self.bot.binance if signal['exit_exchange'] == 'binance' else self.bot.okx

            # 买入
            entry_order = await entry_exchange.create_order(
                symbol,
                'market',
                'buy',
                float(amount),
                None
            )

            if not entry_order:
                logger.error("入场订单失败")
                return False

            # 卖出
            exit_order = await exit_exchange.create_order(
                symbol,
                'market',
                'sell',
                float(amount),
                None
            )

            if not exit_order:
                logger.error("出场订单失败")
                # 这里应该添加补偿逻辑
                return False

            logger.info(f"套利执行成功: {symbol}, 利润: {signal['spread']:.4%}")
            return True

        except Exception as e:
            logger.error(f"套利执行异常: {e}")
            return False

    def _calculate_weighted_price(self, levels) -> Decimal:
        """计算加权平均价格"""
        total_volume = sum(Decimal(str(amount)) for _, amount in levels)
        weighted_price = sum(
            Decimal(str(price)) * Decimal(str(amount)) / total_volume
            for price, amount in levels
        )
        return weighted_price
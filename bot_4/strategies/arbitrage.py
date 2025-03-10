from decimal import Decimal
from typing import Optional, Dict
import logging
from .base import BaseStrategy

logger = logging.getLogger(__name__)

class ArbitrageStrategy(BaseStrategy):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.name = "arbitrage"
        self.is_active = config['enabled_strategies']['arbitrage']
        self.min_spread = Decimal(str(config['arbitrage']['min_spread']))
        # 添加手续费和滑点属性
        self.fee_rate = Decimal('0.0005')  # 双边手续费
        self.slippage = Decimal('0.0002')   # 预估滑点

    async def analyze(self, symbol: str) -> Optional[Dict]:
        try:
            # 修改获取订单簿的方式
            okx_book = await self.bot.exchanges['okx'].fetch_order_book(symbol)
            binance_book = await self.bot.exchanges['binance'].fetch_order_book(symbol)

            okx_bid = self._weighted_price(okx_book['bids'][:3])
            okx_ask = self._weighted_price(okx_book['asks'][:3])
            binance_bid = self._weighted_price(binance_book['bids'][:3])
            binance_ask = self._weighted_price(binance_book['asks'][:3])

            if not all([okx_bid, okx_ask, binance_bid, binance_ask]):
                return None

            # 计算实际有效价差（扣除手续费和滑点）
            spread1 = (binance_bid*(1-self.slippage) - okx_ask*(1+self.slippage)) / okx_ask
            spread1 -= 2 * self.fee_rate
            spread2 = (okx_bid*(1-self.slippage) - binance_ask*(1+self.slippage)) / binance_ask
            spread2 -= 2 * self.fee_rate

            if spread1 > self.min_spread:
                return {
                    'type': 'arbitrage',
                    'direction': 'okx_to_binance',
                    'symbol': symbol,
                    'entry_price': float(okx_ask),
                    'exit_price': float(binance_bid),
                    'effective_spread': float(spread1)
                }
            elif spread2 > self.min_spread:
                return {
                    'type': 'arbitrage',
                    'direction': 'binance_to_okx',
                    'symbol': symbol,
                    'entry_price': float(binance_ask),
                    'exit_price': float(okx_bid),
                    'effective_spread': float(spread2)
                }
        except Exception as e:
            logger.error(f"套利分析异常: {e}")
        return None

    # 修改加权平均价格计算函数名
    def _weighted_price(self, levels):
        total = Decimal('0')
        weighted_sum = Decimal('0')
        for level in levels[:3]:
            price, qty = Decimal(str(level[0])), Decimal(str(level[1]))
            total += qty
            weighted_sum += price * qty
        return weighted_sum / total if total != 0 else None

    async def execute(self, signal: Dict) -> bool:
        """
        执行套利交易：依次下买入与卖出订单，
        注意：下单失败后应有完善的补偿和撤单逻辑。
        """
        try:
            if not await self.validate_signal(signal):
                return False

            symbol = signal['symbol']
            amount = self.bot.calculate_trade_amount(signal['entry_exchange'], 
                                                       Decimal(str(signal['entry_price'])))
            entry_exchange = self.bot.okx if signal['entry_exchange'] == 'okx' else self.bot.binance
            exit_exchange = self.bot.binance if signal['exit_exchange'] == 'binance' else self.bot.okx

            entry_order = await entry_exchange.create_order(
                symbol, 'market', 'buy', float(amount), None
            )
            if not entry_order:
                logger.error("入场订单失败")
                return False

            exit_order = await exit_exchange.create_order(
                symbol, 'market', 'sell', float(amount), None
            )
            if not exit_order:
                logger.error("出场订单失败")
                # 此处建议添加撤单或补偿逻辑
                return False

            logger.info(f"套利执行成功: {symbol}, 利润: {signal['spread']:.4%}")
            return True
        except Exception as e:
            logger.error(f"套利执行异常: {e}")
            return False
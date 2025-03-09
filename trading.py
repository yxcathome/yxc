from decimal import Decimal
from typing import Dict, Optional, Any
from exchange_tools import CryptoExchangeTools
from config import TRADE_CONFIG, FEES_CONFIG
import asyncio
import logging

logger = logging.getLogger(__name__)

class TradingManager:
    def __init__(self, bot):
        self.bot = bot

    async def place_order(self, exchange, symbol: str, side: str, amount: Decimal, price: Decimal) -> Optional[Dict]:
        try:
            market = exchange.market(symbol)
            precise_amount = exchange.amount_to_precision(symbol, float(amount))
            precise_price = exchange.price_to_precision(symbol, float(price))

            params = {}
            if exchange.id == 'binance':
                if side == 'buy':
                    params['positionSide'] = 'LONG'
                else:
                    params['positionSide'] = 'SHORT'
                params['timeInForce'] = 'GTC'
            elif exchange.id == 'okx':
                if side == 'buy':
                    params['posSide'] = 'long'
                else:
                    params['posSide'] = 'short'

            order = await exchange.create_order(
                symbol=symbol,
                type='limit',
                side=side,
                amount=precise_amount,
                price=precise_price,
                params=params
            )
            order_info = {
                'id': order['id'],
                'exchange': exchange.id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price,
                'status': order['status'],
                'timestamp': datetime.now().isoformat()
            }
            self.bot.active_orders.append(order_info)
            logger.info(f"下单成功: {exchange.id} {symbol} {side} {amount:.4f}@{price:.4f}")
            return order_info
        except Exception as e:
            logger.error(f"下单失败: {str(e)}")
            return None

    async def execute_arbitrage(self, opp: Dict) -> bool:
        try:
            if opp['strategy'] == 'OKX买入->Binance卖出':
                buy_ex, sell_ex = self.bot.okx_tools.exchange, self.bot.binance_tools.exchange
                buy_sym, sell_sym = opp['okx_symbol'], opp['binance_symbol']
            else:
                buy_ex, sell_ex = self.bot.binance_tools.exchange, self.bot.okx_tools.exchange
                buy_sym, sell_sym = opp['binance_symbol'], opp['okx_symbol']

            buy_book_task = self.bot.get_orderbook(buy_ex, buy_sym)
            sell_book_task = self.bot.get_orderbook(sell_ex, sell_sym)
            buy_book, sell_book = await asyncio.gather(buy_book_task, sell_book_task)

            if not buy_book or not sell_book:
                logger.info(f"订单簿为空: {buy_sym} 或 {sell_sym}")
                return False

            if not buy_book['asks'] or not sell_book['bids']:
                logger.info(f"订单簿为空: {buy_sym} 或 {sell_sym}")
                return False

            def to_decimal(value, _type: str):
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

            buy_ask_price = to_decimal(buy_book['asks'][0][0], 'price')
            buy_ask_qty = to_decimal(buy_book['asks'][0][1], 'qty')

            sell_bid_price = to_decimal(sell_book['bids'][0][0], 'price')
            sell_bid_qty = to_decimal(sell_book['bids'][0][1], 'qty')

            spread = (sell_bid_price - buy_ask_price) / buy_ask_price
            threshold = self.bot.calc_dynamic_spread(
                buy_ex.id, sell_ex.id, 
                buy_sym, sell_sym
            )

            required_spread = threshold + self.bot.trade_config['slippage_allowance']
            if spread <= required_spread:
                logger.info(f"利差不足: {spread:.4%} < 要求: {required_spread:.4%}")
                return False

            await self.bot.update_balances()
            balance = self.bot.balances[buy_ex.id]

            amount_candidates = [
                self.bot.trade_usdt / buy_ask_price,
                buy_ask_qty * Decimal('0.8'),
                sell_bid_qty * Decimal('0.8'),
                (balance * self.bot.trade_config['position_risk']) / buy_ask_price
            ]
            raw_amount = min(amount_candidates)

            market = buy_ex.market(buy_sym)
            min_amount = Decimal(str(market['limits']['amount']['min']))
            if raw_amount < min_amount:
                raw_amount = min_amount

            precise_amount = buy_ex.amount_to_precision(
                buy_sym, 
                float(raw_amount)
            )
            final_amount = Decimal(str(precise_amount))

            if final_amount < min_amount:
                logger.info(f"交易量过小: {final_amount} < {min_amount}")
                return False

            buy_order = await self.place_order(
                buy_ex, buy_sym, 'buy', 
                final_amount, buy_ask_price
            )
            if not buy_order:
                return False

            sell_order = await self.place_order(
                sell_ex, sell_sym, 'sell', 
                final_amount, sell_bid_price
            )

            if not sell_order:
                await buy_ex.cancel_order(buy_order['id'], buy_sym)
                return False

            gross_profit = (sell_bid_price - buy_ask_price) * final_amount
            fee_cost = (
                (buy_ask_price * final_amount * self.bot.fees_config[buy_ex.id]['taker']) +
                (sell_bid_price * final_amount * self.bot.fees_config[sell_ex.id]['taker'])
            )
            net_profit = gross_profit - fee_cost

            self.bot.profits['total'] += net_profit
            self.bot.profits['realized'] += net_profit
            self.bot.profits['today'] += net_profit
            self.bot.stats['successful_trades'] += 1

            if net_profit > Decimal('0') and self.bot.trade_config['compound_enabled']:
                self.bot.trade_usdt = min(
                    self.bot.trade_usdt * (Decimal('1') + self.bot.trade_config['compound_percent']),
                    self.bot.trade_config['max_trade_usdt']
                )
                logger.info(f"复利升级: 新额度 {self.bot.trade_usdt:.2f} USDT")
            else:
                self.bot.trade_usdt = self.bot.trade_config['initial_trade_usdt']
                logger.info("重置交易额度")

            logger.info(
                f"套利成功 | 利润: {net_profit:.4f} USDT | "
                f"数量: {final_amount:.6f} | "
                f"买价: {buy_ask_price:.2f} | 卖价: {sell_bid_price:.2f}"
            )
            return True
        except Exception as e:
            logger.error(f"执行失败: {str(e)}", exc_info=True)
            self.bot.stats['failed_trades'] += 1
            return False
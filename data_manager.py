import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Optional, List, Any
from exchange_tools import CryptoExchangeTools
from config import TRADE_CONFIG, SYSTEM_CONFIG

logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, bot):
        self.bot = bot

    async def get_orderbook(self, exchange, symbol: str) -> Optional[Dict]:
        try:
            symbol = symbol.upper() if exchange.id == 'binance' else symbol
            orderbook = await exchange.fetch_order_book(symbol, limit=self.bot.trade_config['orderbook_depth'])

            if exchange.id == 'binance':
                min_notional = Decimal('5.0')
                best_ask = Decimal(str(orderbook['asks'][0][0]))
                best_bid = Decimal(str(orderbook['bids'][0][0]))
                if best_ask * self.bot.trade_config['initial_trade_usdt'] < min_notional:
                    logger.debug(f"名义价值不足: {symbol} (需要至少5U)")
                    return None

            return orderbook
        except ccxt.BadSymbol:
            logger.debug(f"交易对不存在: {exchange.id} {symbol}")
            return None

    async def update_balances(self):
        try:
            okx_balance = await self.bot.okx_tools.exchange.fetch_balance(params={'type': 'swap'})
            binance_balance = await self.bot.binance_tools.exchange.fetch_balance(params={'type': 'future'})
            self.bot.balances['okx'] = Decimal(str(okx_balance['USDT']['free']))
            self.bot.balances['binance'] = Decimal(str(binance_balance['USDT']['free']))
        except Exception as e:
            logger.error(f"余额更新失败: {str(e)}")

    async def fetch_funding_rate(self, exchange, symbol: str) -> Decimal:
        try:
            if symbol in self.bot.funding_fees[exchange.id]:
                return self.bot.funding_fees[exchange.id][symbol]
            else:
                if exchange.id == 'okx':
                    res = await exchange.public_get_public_funding_rate({'instId': symbol})
                    return Decimal(res['data'][0]['fundingRate'])
                elif exchange.id == 'binance':
                    res = await exchange.fetch_funding_rate(symbol)
                    return Decimal(res['fundingRate'])
                else:
                    return Decimal('0')
        except Exception as e:
            logger.error(f"获取资金费率失败: {exchange.id} {symbol} - {str(e)}")
            return Decimal('0')

    async def update_funding_fees(self):
        while self.bot.is_running:
            try:
                current_time = datetime.now()
                if (current_time - self.bot.last_funding_update).total_seconds() >= 3600:
                    tasks = []
                    for okx_sym, binance_sym in self.bot.common_pairs:
                        tasks.append(self._update_fee(self.bot.okx_tools.exchange, okx_sym))
                        tasks.append(self._update_fee(self.bot.binance_tools.exchange, binance_sym))
                    await asyncio.gather(*tasks)
                    self.bot.last_funding_update = current_time
                    logger.info("资金费率已更新")
                else:
                    logger.debug("资金费率缓存有效，跳过更新")
            except Exception as e:
                logger.error(f"资金费率更新失败: {str(e)}")
            await asyncio.sleep(60)

    async def _update_fee(self, exchange, symbol: str):
        fee = await self.fetch_funding_rate(exchange, symbol)
        self.bot.funding_fees[exchange.id][symbol] = fee
        logger.info(f"更新费率 {exchange.id} {symbol}: {fee:.4%}")

    async def load_common_pairs(self):
        def normalize_symbol(exchange_id: str, symbol: str) -> Optional[str]:
            symbol = symbol.replace('XBT', 'BTC').replace('BCHSV', 'BSV')
            if exchange_id == 'okx':
                parts = symbol.split('-')
                if len(parts) < 2 or parts[-1] != 'SWAP':
                    return None
                return parts[0].upper()
            elif exchange_id == 'binance':
                if '_' in symbol:
                    return None
                if not symbol.endswith('USDT'):
                    return None
                return symbol[:-4].upper()
            return None

        okx_coins = {}
        for m in self.bot.okx_tools.exchange.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('okx', m['id'])
            if coin:
                okx_coins[coin] = m['id']

        binance_coins = {}
        for m in self.bot.binance_tools.exchange.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('binance', m['id'])
            if coin:
                binance_coins[coin] = m['id']

        common_coins = set(okx_coins) & set(binance_coins)
        self.bot.common_pairs = [
            (okx_coins[coin], binance_coins[coin])
            for coin in common_coins
        ]

        logger.info(f"OKX永续合约数: {len(okx_coins)} 样例: {list(okx_coins.values())[:5]}")
        logger.info(f"Binance永续合约数: {len(binance_coins)} 样例: {list(binance_coins.values())[:5]}")
        logger.info(f"有效共同交易对: {len(self.bot.common_pairs)} 样例: {self.bot.common_pairs[:5]}")
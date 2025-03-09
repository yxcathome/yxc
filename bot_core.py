import asyncio
import logging
from decimal import Decimal, getcontext
from datetime import datetime
import signal
from typing import Dict, Optional, List, Any
from contextlib import suppress

from exchange_tools import CryptoExchangeTools
from config import TRADE_CONFIG, FEES_CONFIG, SYSTEM_CONFIG
from tenacity import retry, stop_after_attempt, wait_exponential
import os

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArbitrageBot:
    def __init__(self):
        self.okx_tools = CryptoExchangeTools('okx', os.environ['OKX_API_KEY'], os.environ['OKX_SECRET'], os.environ['OKX_PASSWORD'])
        self.binance_tools = CryptoExchangeTools('binance', os.environ['BINANCE_API_KEY'], os.environ['BINANCE_SECRET'])

        self.trade_config = TRADE_CONFIG
        self.fees_config = FEES_CONFIG
        self.system_config = SYSTEM_CONFIG
        self.trade_usdt = self.trade_config['initial_trade_usdt']

        self.is_running = True
        self.is_paused = False
        self.balances = {'okx': Decimal('0'), 'binance': Decimal('0')}
        self.profits = {'total': Decimal('0'), 'today': Decimal('0'), 'realized': Decimal('0')}
        self.trades: List[Dict[str, Any]] = []
        self.active_orders: List[Dict[str, Any]] = []
        self.stats = {
            'start_time': datetime.now(),
            'total_checks': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'last_compound': datetime.now(),
        }
        self.optimal_opportunities: List[Dict[str, Any]] = []
        self.common_pairs: List[tuple] = []
        self.funding_fees: Dict[str, Dict[str, Decimal]] = {'okx': {}, 'binance': {}}
        self.last_funding_update = datetime.min
        self.semaphore = asyncio.Semaphore(self.trade_config['max_concurrent_checks'])
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    async def shutdown(self):
        logger.info("启动关闭流程...")
        self.is_running = False

        await self.okx_tools.exchange.close()
        await self.binance_tools.exchange.close()
        logger.info("交易所连接已关闭")

        if self.runner and self.site:
            await self.site.stop()
            await self.runner.cleanup()
            logger.info("Web服务器已关闭")

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("所有任务已取消")

        await asyncio.sleep(0.5)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_orderbook(self, exchange, symbol: str) -> Optional[Dict]:
        try:
            symbol = symbol.upper() if exchange.id == 'binance' else symbol
            orderbook = await exchange.fetch_order_book(symbol, limit=self.trade_config['orderbook_depth'])

            if exchange.id == 'binance':
                min_notional = Decimal('5.0')
                best_ask = Decimal(str(orderbook['asks'][0][0]))
                best_bid = Decimal(str(orderbook['bids'][0][0]))
                if best_ask * self.trade_config['initial_trade_usdt'] < min_notional:
                    logger.debug(f"名义价值不足: {symbol} (需要至少5U)")
                    return None

            return orderbook
        except ccxt.BadSymbol:
            logger.debug(f"交易对不存在: {exchange.id} {symbol}")
            return None

    async def update_balances(self):
        try:
            okx_balance = await self.okx_tools.exchange.fetch_balance(params={'type': 'swap'})
            binance_balance = await self.binance_tools.exchange.fetch_balance(params={'type': 'future'})
            self.balances['okx'] = Decimal(str(okx_balance['USDT']['free']))
            self.balances['binance'] = Decimal(str(binance_balance['USDT']['free']))
        except Exception as e:
            logger.error(f"余额更新失败: {str(e)}")

    async def fetch_funding_rate(self, exchange, symbol: str) -> Decimal:
        try:
            if symbol in self.funding_fees[exchange.id]:
                return self.funding_fees[exchange.id][symbol]
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
        while self.is_running:
            try:
                current_time = datetime.now()
                if (current_time - self.last_funding_update).total_seconds() >= 3600:
                    tasks = []
                    for okx_sym, binance_sym in self.common_pairs:
                        tasks.append(self._update_fee(self.okx_tools.exchange, okx_sym))
                        tasks.append(self._update_fee(self.binance_tools.exchange, binance_sym))
                    await asyncio.gather(*tasks)
                    self.last_funding_update = current_time
                    logger.info("资金费率已更新")
                else:
                    logger.debug("资金费率缓存有效，跳过更新")
            except Exception as e:
                logger.error(f"资金费率更新失败: {str(e)}")
            await asyncio.sleep(60)

    async def _update_fee(self, exchange, symbol: str):
        fee = await self.fetch_funding_rate(exchange, symbol)
        self.funding_fees[exchange.id][symbol] = fee
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
        for m in self.okx_tools.exchange.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('okx', m['id'])
            if coin:
                okx_coins[coin] = m['id']

        binance_coins = {}
        for m in self.binance_tools.exchange.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('binance', m['id'])
            if coin:
                binance_coins[coin] = m['id']

        common_coins = set(okx_coins) & set(binance_coins)
        self.common_pairs = [
            (okx_coins[coin], binance_coins[coin])
            for coin in common_coins
        ]

        logger.info(f"OKX永续合约数: {len(okx_coins)} 样例: {list(okx_coins.values())[:5]}")
        logger.info(f"Binance永续合约数: {len(binance_coins)} 样例: {list(binance_coins.values())[:5]}")
        logger.info(f"有效共同交易对: {len(self.common_pairs)} 样例: {self.common_pairs[:5]}")

    async def arbitrage_loop(self):
        while self.is_running:
            if self.is_paused:
                await asyncio.sleep(1)
                continue
            
            try:
                opp = await self.find_best_arbitrage_opportunity()
                if opp:
                    logger.info(f"发现机会: {opp['strategy']} 利差: {opp['spread']:.2f}%")
                    await self.execute_arbitrage(opp)
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"主循环异常: {str(e)}")

    async def run_web_server(self):
        from web_server import run_web_server
        await run_web_server(self, self.system_config['webserver_port'])

    def calc_dynamic_spread(self, ex1: str, ex2: str, symbol1: str, symbol2: str) -> Decimal:
        fee_total = self.fees_config[ex1]['taker'] + self.fees_config[ex2]['taker']
        funding_fee = self.funding_fees[ex1].get(symbol1, Decimal('0')) + self.funding_fees[ex2].get(symbol2, Decimal('0'))
        return fee_total + funding_fee + self.trade_config['min_profit_margin']
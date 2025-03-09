import logging
from decimal import Decimal
from typing import Dict, List, Any
from bot_core import ArbitrageBot
from typing import Dict, List, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

class ArbitrageStrategy:
    def __init__(self, bot: ArbitrageBot):
        self.bot = bot

    async def find_best_arbitrage_opportunity(self) -> Optional[Dict]:
        self.bot.stats['total_checks'] += 1
        opportunities = []

        async def check_pair(okx_sym: str, binance_sym: str):
            async with self.bot.semaphore:
                try:
                    okx_book, binance_book = await asyncio.gather(
                        self.bot.get_orderbook(self.bot.okx_tools.exchange, okx_sym),
                        self.bot.get_orderbook(self.bot.binance_tools.exchange, binance_sym)
                    )
                    if not okx_book or not binance_book:
                        return None

                    okx_ask = okx_book['asks'][0][0]
                    binance_bid = binance_book['bids'][0][0]
                    spread1 = (binance_bid - okx_ask) / okx_ask
                    threshold1 = self.bot.calc_dynamic_spread('okx', 'binance', okx_sym, binance_sym)
                    
                    binance_ask = binance_book['asks'][0][0]
                    okx_bid = okx_book['bids'][0][0]
                    spread2 = (okx_bid - binance_ask) / binance_ask
                    threshold2 = self.bot.calc_dynamic_spread('binance', 'okx', binance_sym, okx_sym)

                    best_opp = None
                    if spread1 > threshold1 + self.bot.trade_config['slippage_allowance']:
                        best_opp = {
                            'okx_symbol': okx_sym,
                            'binance_symbol': binance_sym,
                            'strategy': 'OKX买入->Binance卖出',
                            'spread': float(spread1 * 100),
                            'entry_price': float(okx_ask),
                            'exit_price': float(binance_bid)
                        }
                    if spread2 > threshold2 + self.bot.trade_config['slippage_allowance']:
                        current_opp = {
                            'okx_symbol': okx_sym,
                            'binance_symbol': binance_sym,
                            'strategy': 'Binance买入->OKX卖出',
                            'spread': float(spread2 * 100),
                            'entry_price': float(binance_ask),
                            'exit_price': float(okx_bid)
                        }
                        if not best_opp or current_opp['spread'] > best_opp['spread']:
                            best_opp = current_opp
                    return best_opp
                except Exception as e:
                    logger.error(f"检查交易对失败: {okx_sym}-{binance_sym} - {str(e)}")
                    return None

        tasks = [check_pair(okx_sym, binance_sym) for okx_sym, binance_sym in self.bot.common_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_opps = [res for res in results if isinstance(res, dict)]
        self.bot.optimal_opportunities = sorted(valid_opps, key=lambda x: x['spread'], reverse=True)[:30]
        return self.bot.optimal_opportunities[0] if self.bot.optimal_opportunities else None
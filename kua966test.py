import ccxt.async_support as ccxt
import asyncio
import logging
import os
from datetime import datetime, timedelta
import signal
from aiohttp import web
from typing import Dict, Optional, List, Any
import decimal
from decimal import Decimal, getcontext, ROUND_DOWN, InvalidOperation
from tenacity import retry, stop_after_attempt, wait_exponential

getcontext().prec = 8

CONFIG = {
    'initial_capital': Decimal('100'),
    'max_position_ratio': Decimal('0.8'),
    'min_profit_threshold': Decimal('0.0003'),
    'slippage_tolerance': Decimal('0.001'),
    'orderbook_depth': 20,
    'max_retries': 3,
    'balance_refresh': 30,
    'funding_rate_interval': 3600,  # 1小时更新一次
    'webserver_port': 5000,
    'health_check_interval': 60
}

class RollingMemoryHandler(logging.Handler):
    def __init__(self, capacity=1000):
        super().__init__()
        self.capacity = capacity
        self.buffer = []
        self.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

    def emit(self, record):
        self.buffer.append(self.format(record))
        if len(self.buffer) > self.capacity:
            self.buffer.pop(0)

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(f'arbitrage_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
mem_handler = RollingMemoryHandler()
logger = logging.getLogger(__name__)
logger.addHandler(mem_handler)

class ArbitrageBot:
    def __init__(self):
        required_env_vars = ['OKX_API_KEY', 'OKX_SECRET', 'OKX_PASSWORD', 'BINANCE_API_KEY', 'BINANCE_SECRET']
        missing = [var for var in required_env_vars if not os.environ.get(var)]
        if missing:
            raise RuntimeError(f"缺少环境变量: {', '.join(missing)}")

        self.okx = ccxt.okx({
            'apiKey': os.environ['OKX_API_KEY'],
            'secret': os.environ['OKX_SECRET'],
            'password': os.environ['OKX_PASSWORD'],
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
            'timeout': 15000
        })

        self.binance = ccxt.binance({
            'apiKey': os.environ['BINANCE_API_KEY'],
            'secret': os.environ['BINANCE_SECRET'],
            'options': {
                'defaultType': 'future',
                'hedgeMode': False,
                'positionSide': 'BOTH'
            },
            'enableRateLimit': True,
            'timeout': 15000
        })

        # 状态标志
        self.is_running = True
        self.is_shutting_down = False
        self.is_paused = False

        # 配置
        self.config = {
            'initial_trade_usdt': Decimal('20.0'),
            'max_trade_usdt': Decimal('100.0'),
            'min_profit_margin': Decimal('0.0001'),
            'position_risk': Decimal('0.9'),
            'compound_percent': Decimal('0.01'),
            'slippage_allowance': Decimal('0.001'),
            'orderbook_depth': 20,
            'compound_enabled': True
        }
        
        self.trade_usdt = self.config['initial_trade_usdt']
        self.fees = {
            'okx': {'taker': Decimal('0.0005')},
            'binance': {'taker': Decimal('0.0004')}
        }

        self.balances = {'okx': Decimal('0'), 'binance': Decimal('0')}
        self.profits = {'total': Decimal('0'), 'today': Decimal('0'), 'realized': Decimal('0')}
        self.stats = {
            'start_time': datetime.now(),
            'total_checks': 0,
            'successful_trades': 0,
            'failed_trades': 0
        }
        
        self.funding_fees_cache = {}
        self.last_funding_update = None
        self.FUNDING_UPDATE_INTERVAL = 3600
        self.common_pairs = []
        self.semaphore = asyncio.Semaphore(10)
        self.optimal_opportunities = []

    async def _setup_binance_position_mode(self):
        try:
            await self.binance.fapiPrivatePostPositionSideDual({'dualSidePosition': False})
            logger.info("Binance设置单向持仓模式成功")
        except Exception as e:
            if "No need to change position side" in str(e):
                logger.info("Binance已经是单向持仓模式")
            else:
                logger.error(f"设置Binance持仓模式失败: {str(e)}")

    async def shutdown(self):
        """安全关闭所有连接和任务"""
        if self.is_shutting_down:
            return
        
        self.is_shutting_down = True
        self.is_running = False
        logger.info("开始关闭系统...")

        # 等待一小段时间让正在进行的操作完成
        await asyncio.sleep(0.5)

        try:
            # 创建关闭任务
            close_tasks = [
                self.okx.close(),
                self.binance.close()
            ]
            
            # 使用超时机制关闭连接
            await asyncio.wait_for(
                asyncio.gather(*close_tasks, return_exceptions=True),
                timeout=5.0
            )
            logger.info("交易所连接已关闭")
        except asyncio.TimeoutError:
            logger.error("关闭连接超时")
        except Exception as e:
            logger.error(f"关闭交易所连接时发生错误: {str(e)}")

        # 确保所有资源都被释放
        for exchange in [self.okx, self.binance]:
            try:
                if hasattr(exchange, 'session') and exchange.session:
                    await exchange.session.close()
            except Exception:
                pass

    async def get_orderbook(self, exchange, symbol: str) -> Optional[Dict]:
        try:
            symbol = symbol.upper() if exchange.id == 'binance' else symbol
            orderbook = await exchange.fetch_order_book(symbol, limit=self.config['orderbook_depth'])
            if exchange.id == 'binance':
                min_notional = Decimal('5.0')
                best_ask = Decimal(str(orderbook['asks'][0][0]))
                if best_ask * self.config['initial_trade_usdt'] < min_notional:
                    return None
            return orderbook
        except Exception as e:
            logger.error(f"获取订单簿失败 {exchange.id} {symbol}: {str(e)}")
            return None

    async def update_balances(self):
        try:
            okx_balance = await self.okx.fetch_balance(params={'type': 'swap'})
            binance_balance = await self.binance.fetch_balance(params={'type': 'future'})
            self.balances['okx'] = Decimal(str(okx_balance['USDT']['free']))
            self.balances['binance'] = Decimal(str(binance_balance['USDT']['free']))
        except Exception as e:
            logger.error(f"余额更新失败: {str(e)}")

    async def fetch_funding_rate(self, exchange, symbol: str) -> Decimal:
        try:
            if exchange.id == 'okx':
                res = await exchange.public_get_public_funding_rate({'instId': symbol})
                return Decimal(str(res['data'][0]['fundingRate']))
            elif exchange.id == 'binance':
                res = await exchange.fetch_funding_rate(symbol)
                return Decimal(str(res['fundingRate']))
            return Decimal('0')
        except Exception as e:
            logger.error(f"获取资金费率失败: {exchange.id} {symbol} - {str(e)}")
            return Decimal('0')

    async def update_funding_fees(self):
        while self.is_running:
            try:
                current_time = datetime.now()
                if (self.last_funding_update is None or 
                    (current_time - self.last_funding_update).total_seconds() >= self.FUNDING_UPDATE_INTERVAL):
                    tasks = []
                    for okx_sym, binance_sym in self.common_pairs:
                        tasks.append(self._update_fee(self.okx, okx_sym))
                        tasks.append(self._update_fee(self.binance, binance_sym))
                    await asyncio.gather(*tasks)
                    self.last_funding_update = current_time
            except Exception as e:
                logger.error(f"资金费率更新失败: {str(e)}")
            await asyncio.sleep(60)

    async def _update_fee(self, exchange, symbol: str):
        try:
            fee = await self.fetch_funding_rate(exchange, symbol)
            self.funding_fees_cache[f"{exchange.id}_{symbol}"] = {
                'rate': fee,
                'update_time': datetime.now()
            }
        except Exception as e:
            logger.error(f"获取{exchange.id} {symbol}资金费率失败: {str(e)}")

    def get_cached_funding_fee(self, exchange_id: str, symbol: str) -> Decimal:
        cache_key = f"{exchange_id}_{symbol}"
        cache_data = self.funding_fees_cache.get(cache_key, {})
        return cache_data.get('rate', Decimal('0'))

    def calc_dynamic_spread(self, ex1: str, ex2: str, symbol1: str, symbol2: str) -> Decimal:
        fee_total = self.fees[ex1]['taker'] + self.fees[ex2]['taker']
        funding_fee1 = self.get_cached_funding_fee(ex1, symbol1)
        funding_fee2 = self.get_cached_funding_fee(ex2, symbol2)
        funding_fee = funding_fee1 + funding_fee2
        return fee_total + funding_fee + self.config['min_profit_margin']

    async def place_order(self, exchange, symbol: str, side: str, amount: Decimal, price: Decimal) -> Optional[Dict]:
        try:
            market = exchange.market(symbol)
            precise_amount = exchange.amount_to_precision(symbol, float(amount))
            precise_price = exchange.price_to_precision(symbol, float(price))

            params = {'timeInForce': 'GTC'} if exchange.id == 'binance' else {}
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
            logger.info(f"下单成功: {exchange.id} {symbol} {side} {amount:.4f}@{price:.4f}")
            return order_info
        except Exception as e:
            logger.error(f"下单失败: {exchange.id} {str(e)}")
            return None

    async def get_orderbook(self, exchange, symbol: str) -> Optional[Dict]:
        try:
            symbol = symbol.upper() if exchange.id == 'binance' else symbol
            orderbook = await exchange.fetch_order_book(symbol, limit=self.config['orderbook_depth'])
            if exchange.id == 'binance':
                min_notional = Decimal('5.0')
                best_ask = Decimal(str(orderbook['asks'][0][0]))
                if best_ask * self.config['initial_trade_usdt'] < min_notional:
                    return None
            return orderbook
        except Exception as e:
            logger.error(f"获取订单簿失败 {exchange.id} {symbol}: {str(e)}")
            return None

    async def update_balances(self):
        try:
            okx_balance = await self.okx.fetch_balance(params={'type': 'swap'})
            binance_balance = await self.binance.fetch_balance(params={'type': 'future'})
            self.balances['okx'] = Decimal(str(okx_balance['USDT']['free']))
            self.balances['binance'] = Decimal(str(binance_balance['USDT']['free']))
        except Exception as e:
            logger.error(f"余额更新失败: {str(e)}")

    async def fetch_funding_rate(self, exchange, symbol: str) -> Decimal:
        try:
            if exchange.id == 'okx':
                res = await exchange.public_get_public_funding_rate({'instId': symbol})
                return Decimal(str(res['data'][0]['fundingRate']))
            elif exchange.id == 'binance':
                res = await exchange.fetch_funding_rate(symbol)
                return Decimal(str(res['fundingRate']))
            return Decimal('0')
        except Exception as e:
            logger.error(f"获取资金费率失败: {exchange.id} {symbol} - {str(e)}")
            return Decimal('0')

    async def update_funding_fees(self):
        while self.is_running:
            try:
                current_time = datetime.now()
                if (self.last_funding_update is None or 
                    (current_time - self.last_funding_update).total_seconds() >= self.FUNDING_UPDATE_INTERVAL):
                    tasks = []
                    for okx_sym, binance_sym in self.common_pairs:
                        tasks.append(self._update_fee(self.okx, okx_sym))
                        tasks.append(self._update_fee(self.binance, binance_sym))
                    await asyncio.gather(*tasks)
                    self.last_funding_update = current_time
            except Exception as e:
                logger.error(f"资金费率更新失败: {str(e)}")
            await asyncio.sleep(60)

    async def _update_fee(self, exchange, symbol: str):
        try:
            fee = await self.fetch_funding_rate(exchange, symbol)
            self.funding_fees_cache[f"{exchange.id}_{symbol}"] = {
                'rate': fee,
                'update_time': datetime.now()
            }
        except Exception as e:
            logger.error(f"获取{exchange.id} {symbol}资金费率失败: {str(e)}")

    def get_cached_funding_fee(self, exchange_id: str, symbol: str) -> Decimal:
        cache_key = f"{exchange_id}_{symbol}"
        cache_data = self.funding_fees_cache.get(cache_key, {})
        return cache_data.get('rate', Decimal('0'))

    def calc_dynamic_spread(self, ex1: str, ex2: str, symbol1: str, symbol2: str) -> Decimal:
        fee_total = self.fees[ex1]['taker'] + self.fees[ex2]['taker']
        funding_fee1 = self.get_cached_funding_fee(ex1, symbol1)
        funding_fee2 = self.get_cached_funding_fee(ex2, symbol2)
        funding_fee = funding_fee1 + funding_fee2
        return fee_total + funding_fee + self.config['min_profit_margin']

    async def place_order(self, exchange, symbol: str, side: str, amount: Decimal, price: Decimal) -> Optional[Dict]:
        try:
            market = exchange.market(symbol)
            precise_amount = exchange.amount_to_precision(symbol, float(amount))
            precise_price = exchange.price_to_precision(symbol, float(price))

            params = {'timeInForce': 'GTC'} if exchange.id == 'binance' else {}
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
            logger.info(f"下单成功: {exchange.id} {symbol} {side} {amount:.4f}@{price:.4f}")
            return order_info
        except Exception as e:
            logger.error(f"下单失败: {exchange.id} {str(e)}")
            return None

    async def find_best_arbitrage_opportunity(self) -> Optional[Dict]:
        self.stats['total_checks'] += 1
        opportunities = []

        async def check_pair(okx_sym: str, binance_sym: str):
            async with self.semaphore:
                try:
                    logger.debug(f"获取订单簿 OKX: {okx_sym}, Binance: {binance_sym}")
                    okx_book, binance_book = await asyncio.gather(
                        self.get_orderbook(self.okx, okx_sym),
                        self.get_orderbook(self.binance, binance_sym)
                    )
                    if not okx_book or not binance_book:
                        return None

                    okx_ask = Decimal(str(okx_book['asks'][0][0]))
                    binance_bid = Decimal(str(binance_book['bids'][0][0]))
                    spread1 = (binance_bid - okx_ask) / okx_ask
                    threshold1 = self.calc_dynamic_spread('okx', 'binance', okx_sym, binance_sym)
                    
                    binance_ask = Decimal(str(binance_book['asks'][0][0]))
                    okx_bid = Decimal(str(okx_book['bids'][0][0]))
                    spread2 = (okx_bid - binance_ask) / binance_ask
                    threshold2 = self.calc_dynamic_spread('binance', 'okx', binance_sym, okx_sym)

                    best_opp = None
                    if spread1 > threshold1 + self.config['slippage_allowance']:
                        best_opp = {
                            'okx_symbol': okx_sym,
                            'binance_symbol': binance_sym,
                            'strategy': 'OKX买入->Binance卖出',
                            'spread': float(spread1 * 100),
                            'entry_price': float(okx_ask),
                            'exit_price': float(binance_bid)
                        }
                    if spread2 > threshold2 + self.config['slippage_allowance']:
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

        tasks = [check_pair(okx_sym, binance_sym) for okx_sym, binance_sym in self.common_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_opps = [res for res in results if isinstance(res, dict)]
        self.optimal_opportunities = sorted(valid_opps, key=lambda x: x['spread'], reverse=True)[:30]
        return self.optimal_opportunities[0] if self.optimal_opportunities else None

    async def load_common_pairs(self):
        def normalize_symbol(exchange_id: str, symbol: str) -> Optional[str]:
            symbol = symbol.replace('XBT', 'BTC').replace('BCHSV', 'BSV')
            if exchange_id == 'okx':
                parts = symbol.split('-')
                if len(parts) < 2 or parts[-1] != 'SWAP':
                    return None
                return parts[0].upper()
            elif exchange_id == 'binance':
                if '_' in symbol or not symbol.endswith('USDT'):
                    return None
                return symbol[:-4].upper()
            return None

        okx_coins = {}
        binance_coins = {}
        
        for m in self.okx.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('okx', m['id'])
            if coin:
                okx_coins[coin] = m['id']

        for m in self.binance.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('binance', m['id'])
            if coin:
                binance_coins[coin] = m['id']

        common_coins = set(okx_coins) & set(binance_coins)
        self.common_pairs = [(okx_coins[coin], binance_coins[coin]) for coin in common_coins]
        logger.info(f"加载了 {len(self.common_pairs)} 个共同交易对")

    async def arbitrage_loop(self):
        while self.is_running:
            if self.is_shutting_down:  # 添加关闭检查
                break
            if self.is_paused:
                await asyncio.sleep(1)
                continue
            try:
                opp = await self.find_best_arbitrage_opportunity()
                if opp and not self.is_shutting_down:  # 添加关闭检查
                    logger.info(f"发现机会: {opp['strategy']} 利差: {opp['spread']:.2f}%")
                    await self.execute_arbitrage(opp)
                await asyncio.sleep(0.1)
            except Exception as e:
                if not self.is_shutting_down:  # 只在非关闭状态下记录错误
                    logger.error(f"主循环异常: {str(e)}")

    async def shutdown(self):
        """安全关闭所有连接和任务"""
        if self.is_shutting_down:
            return
        
        self.is_shutting_down = True
        self.is_running = False
        logger.info("开始关闭系统...")

        # 等待所有任务完成
        await asyncio.sleep(1)

        try:
            # 取消所有运行中的任务
            tasks = [task for task in asyncio.all_tasks() 
                    if task != asyncio.current_task() and not task.done()]
            for task in tasks:
                task.cancel()
            
            if tasks:
                await asyncio.wait(tasks, timeout=5)

            # 关闭交易所连接
            await asyncio.gather(
                self.okx.close(),
                self.binance.close(),
                return_exceptions=True
            )
            logger.info("交易所连接已关闭")
        except Exception as e:
            logger.error(f"关闭交易所连接时发生错误: {str(e)}")

async def main():
    bot = ArbitrageBot()
    
    async def shutdown_handler():
        logger.info("开始关闭流程...")
        try:
            await bot.shutdown()
            # 等待清理完成
            await asyncio.sleep(2)
            # 确保所有任务都已取消
            remaining_tasks = [task for task in asyncio.all_tasks() 
                             if task != asyncio.current_task() and not task.done()]
            for task in remaining_tasks:
                task.cancel()
            if remaining_tasks:
                await asyncio.wait(remaining_tasks, timeout=5)
        except Exception as e:
            logger.error(f"关闭过程发生错误: {str(e)}")
        finally:
            logger.info("关闭流程完成")

    def signal_handler(signum, frame):
        logger.info("收到终止信号")
        asyncio.create_task(shutdown_handler())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await asyncio.gather(
            bot.okx.load_markets(),
            bot.binance.load_markets()
        )
        await bot._setup_binance_position_mode()
        await bot.load_common_pairs()
        
        if not bot.common_pairs:
            raise RuntimeError("无有效交易对")
        
        await asyncio.gather(
            bot.arbitrage_loop(),
            bot.update_funding_fees()
        )
    except asyncio.CancelledError:
        logger.info("收到取消信号")
    except Exception as e:
        logger.error(f"致命错误: {str(e)}")
    finally:
        await shutdown_handler()
        logger.info("系统关闭完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"程序异常退出: {str(e)}")
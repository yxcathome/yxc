import ccxt.async_support as ccxt
import asyncio
import logging
import os
from datetime import datetime, timedelta
import signal
from aiohttp import web
from typing import Dict, Optional, List, Any
from contextlib import suppress
from decimal import Decimal, getcontext
from tenacity import retry, stop_after_attempt, wait_exponential

# ------------------------- 全局配置 -------------------------
getcontext().prec = 8
CONFIG = {
    'initial_capital': Decimal('100'),
    'max_position_ratio': Decimal('0.8'),
    'min_profit_threshold': Decimal('0.0003'),
    'slippage_tolerance': Decimal('0.001'),
    'orderbook_depth': 20,
    'max_retries': 3,
    'balance_refresh': 30,
    'funding_rate_interval': 4 * 3600,
    'webserver_port': 5000,
    'health_check_interval': 60
}

# ------------------------- 日志系统 -------------------------
class RollingMemoryHandler(logging.Handler):
    def __init__(self, capacity=1000):
        super().__init__()
        self.capacity = capacity
        self.buffer = []
        self.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

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

# ------------------------- 套利机器人核心类 -------------------------
class ArbitrageBot:
    def __init__(self):
        # 环境变量验证
        required_env_vars = ['OKX_API_KEY', 'OKX_SECRET', 'OKX_PASSWORD', 'BINANCE_API_KEY', 'BINANCE_SECRET']
        missing = [var for var in required_env_vars if not os.environ.get(var)]
        if missing:
            logger.error(f"缺少环境变量: {', '.join(missing)}")
            raise RuntimeError("API凭证缺失")

        # 初始化交易所（带连接优化）
        self.okx = ccxt.okx({
            'apiKey': os.environ['OKX_API_KEY'],
            'secret': os.environ['OKX_SECRET'],
            'password': os.environ['OKX_PASSWORD'],
            'options': {'defaultType': 'swap', 'adjustForTimeDifference': True},
            'enableRateLimit': True,
            'timeout': 15000
        })
        self.binance = ccxt.binance({
            'apiKey': os.environ['BINANCE_API_KEY'],
            'secret': os.environ['BINANCE_SECRET'],
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True},
            'enableRateLimit': True,
            'timeout': 15000
        })

        # 交易配置（Decimal类型）
        self.config = {
            'initial_trade_usdt': Decimal('7.0'),  # 初始交易金额7U
            'max_trade_usdt': Decimal('100.0'),   # 最大交易金额100U
            'min_profit_margin': Decimal('0.0001'),  # 最小利润阈值
            'position_risk': Decimal('0.9'),  # 仓位风险控制
            'compound_percent': Decimal('0.01'),  # 复利比例
            'compound_enabled': True,  # 启用复利
            'slippage_allowance': Decimal('0.001'),  # 滑点容忍度
            'orderbook_depth': 20,  # 订单簿深度
            'max_concurrent_checks': 10  # 最大并发检查数
        }
        self.trade_usdt = self.config['initial_trade_usdt']

        # 手续费配置
        self.fees = {
            'okx': {'taker': Decimal('0.0005')},
            'binance': {'taker': Decimal('0.0004')}
        }

        # 状态管理
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
        self.semaphore = asyncio.Semaphore(self.config['max_concurrent_checks'])
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    async def shutdown(self):
        """增强版关闭流程"""
        logger.info("启动关闭流程...")
        self.is_running = False

        # 关闭交易所连接
        if hasattr(self, 'okx'):
            await self.okx.close()
        if hasattr(self, 'binance'):
            await self.binance.close()
        logger.info("交易所连接已关闭")

        # 关闭Web服务器
        if self.runner and self.site:
            await self.site.stop()
            await self.runner.cleanup()
            logger.info("Web服务器已关闭")

        # 取消所有异步任务
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        logger.info("所有任务已取消")

        # 防止Event Loop提前关闭
        await asyncio.sleep(0.5)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_orderbook(self, exchange, symbol: str) -> Optional[Dict]:
        """获取订单簿（兼容Binance名义价值限制）"""
        try:
            # Binance期货需要全大写（如BTCUSDT）
            symbol = symbol.upper() if exchange.id == 'binance' else symbol
            orderbook = await exchange.fetch_order_book(symbol, limit=self.config['orderbook_depth'])

            # 过滤名义价值不足的交易对
            if exchange.id == 'binance':
                min_notional = Decimal('5.0')  # Binance最小名义价值5U
                best_ask = Decimal(str(orderbook['asks'][0][0]))
                best_bid = Decimal(str(orderbook['bids'][0][0]))
                if best_ask * self.config['initial_trade_usdt'] < min_notional:
                    logger.debug(f"名义价值不足: {symbol} (需要至少5U)")
                    return None

            return orderbook
        except ccxt.BadSymbol:  # 显式捕获无效交易对
            logger.debug(f"交易对不存在: {exchange.id} {symbol}")
            return None

    async def update_balances(self):
        """更新账户余额（严格类型转换）"""
        try:
            okx_balance = await self.okx.fetch_balance(params={'type': 'swap'})
            binance_balance = await self.binance.fetch_balance(params={'type': 'future'})
            self.balances['okx'] = Decimal(str(okx_balance['USDT']['free']))
            self.balances['binance'] = Decimal(str(binance_balance['USDT']['free']))
        except Exception as e:
            logger.error(f"余额更新失败: {str(e)}")

    async def fetch_funding_rate(self, exchange, symbol: str) -> Decimal:
        """获取资金费率（交易所兼容）"""
        try:
            if exchange.id == 'okx':
                res = await exchange.public_get_public_funding_rate({'instId': symbol})
                return Decimal(res['data'][0]['fundingRate'])
            elif exchange.id == 'binance':
                res = await exchange.fetch_funding_rate(symbol)
                return Decimal(res['fundingRate'])
            return Decimal('0')
        except Exception as e:
            logger.error(f"获取资金费率失败: {exchange.id} {symbol} - {str(e)}")
            return Decimal('0')

    async def update_funding_fees(self):
        """资金费率定时更新"""
        while self.is_running:
            try:
                tasks = []
                for okx_sym, binance_sym in self.common_pairs:
                    tasks.append(self._update_fee(self.okx, okx_sym))
                    tasks.append(self._update_fee(self.binance, binance_sym))
                await asyncio.gather(*tasks)
                self.last_funding_update = datetime.now()
            except Exception as e:
                logger.error(f"资金费率更新失败: {str(e)}")
            await asyncio.sleep(4 * 3600)

    async def _update_fee(self, exchange, symbol: str):
        """更新单个交易对资金费率"""
        fee = await self.fetch_funding_rate(exchange, symbol)
        self.funding_fees[exchange.id][symbol] = fee
        logger.info(f"更新费率 {exchange.id} {symbol}: {fee:.4%}")

    async def place_order(self, exchange, symbol: str, side: str, amount: Decimal, price: Decimal) -> Optional[Dict]:
        """下单（严格精度处理）"""
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
            self.active_orders.append(order_info)
            logger.info(f"下单成功: {exchange.id} {symbol} {side} {amount:.4f}@{price:.4f}")
            return order_info
        except Exception as e:
            logger.error(f"下单失败: {str(e)}")
            return None

    def calc_dynamic_spread(self, ex1: str, ex2: str, symbol1: str, symbol2: str) -> Decimal:
        """动态计算价差阈值"""
        fee_total = self.fees[ex1]['taker'] + self.fees[ex2]['taker']
        funding_fee = self.funding_fees[ex1].get(symbol1, Decimal('0')) + self.funding_fees[ex2].get(symbol2, Decimal('0'))
        return fee_total + funding_fee + self.config['min_profit_margin']

    async def execute_arbitrage(self, opp: Dict) -> bool:
        """执行套利交易（完全Decimal化版本）"""
        try:
            # ================== 初始化交易方向 ==================
            if opp['strategy'] == 'OKX买入->Binance卖出':
                buy_ex, sell_ex = self.okx, self.binance
                buy_sym, sell_sym = opp['okx_symbol'], opp['binance_symbol']
            else:
                buy_ex, sell_ex = self.binance, self.okx
                buy_sym, sell_sym = opp['binance_symbol'], opp['okx_symbol']

            # ================== 获取订单簿（强制类型转换） ==================
            buy_book_task = self.get_orderbook(buy_ex, buy_sym)
            sell_book_task = self.get_orderbook(sell_ex, sell_sym)
            buy_book, sell_book = await asyncio.gather(buy_book_task, sell_book_task)

            if not buy_book or not sell_book:
                return False

            # 显式转换所有数值为Decimal（防御式编程）
            def to_decimal(value, _type: str):
                """安全转换函数"""
                if isinstance(value, Decimal):
                    return value
                try:
                    return Decimal(str(value)) if _type == 'price' else Decimal(str(value)).quantize(Decimal('1e-8'))
                except Exception as e:
                    logger.error(f"数值转换失败: {value} | {str(e)}")
                    raise ValueError("Invalid numeric type")

            # 处理买方向订单簿
            buy_ask_price = to_decimal(buy_book['asks'][0][0], 'price')
            buy_ask_qty = to_decimal(buy_book['asks'][0][1], 'qty')

            # 处理卖方向订单簿
            sell_bid_price = to_decimal(sell_book['bids'][0][0], 'price')
            sell_bid_qty = to_decimal(sell_book['bids'][0][1], 'qty')

            # ================== 计算利差（全Decimal运算） ==================
            spread = (sell_bid_price - buy_ask_price) / buy_ask_price
            threshold = self.calc_dynamic_spread(
                buy_ex.id, sell_ex.id, 
                buy_sym, sell_sym
            )  # 确保此方法返回Decimal

            # 利差检查（增加容差缓冲）
            required_spread = threshold + self.config['slippage_allowance']
            if spread <= required_spread:
                logger.info(f"利差不足: {spread:.4%} < 要求: {required_spread:.4%}")
                return False

            # ================== 计算交易量（严格类型控制） ==================
            # 获取当前可用余额
            await self.update_balances()
            balance = self.balances[buy_ex.id]

            # 计算最大可交易量（四要素取最小）
            amount_candidates = [
                self.trade_usdt / buy_ask_price,  # 初始资金限制
                buy_ask_qty * Decimal('0.8'),      # 买盘深度限制
                sell_bid_qty * Decimal('0.8'),     # 卖盘深度限制
                (balance * self.config['position_risk']) / buy_ask_price  # 风险控制
            ]
            raw_amount = min(amount_candidates)

            # 精度处理（按交易所要求）
            market = buy_ex.market(buy_sym)
            precise_amount = buy_ex.amount_to_precision(
                buy_sym, 
                float(raw_amount)  # CCXT要求传入float
            )
            final_amount = Decimal(str(precise_amount))  # 转回Decimal保持类型统一

            if final_amount < Decimal(str(market['limits']['amount']['min'])):
                logger.info(f"交易量过小: {final_amount} < {market['limits']['amount']['min']}")
                return False

            # ================== 执行交易 ==================
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

            # ================== 利润计算（Decimal精确计算） ==================
            gross_profit = (sell_bid_price - buy_ask_price) * final_amount
            fee_cost = (
                (buy_ask_price * final_amount * self.fees[buy_ex.id]['taker']) +
                (sell_bid_price * final_amount * self.fees[sell_ex.id]['taker'])
            )
            net_profit = gross_profit - fee_cost

            # 更新状态
            self.profits['total'] += net_profit
            self.profits['realized'] += net_profit
            self.profits['today'] += net_profit
            self.stats['successful_trades'] += 1

            # 复利逻辑（全Decimal运算）
            if net_profit > Decimal('0') and self.config['compound_enabled']:
                self.trade_usdt = min(
                    self.trade_usdt * (Decimal('1') + self.config['compound_percent']),
                    self.config['max_trade_usdt']
                )
                logger.info(f"复利升级: 新额度 {self.trade_usdt:.2f} USDT")
            else:
                self.trade_usdt = self.config['initial_trade_usdt']
                logger.info("重置交易额度")

            logger.info(
                f"套利成功 | 利润: {net_profit:.4f} USDT | "
                f"数量: {final_amount:.6f} | "
                f"买价: {buy_ask_price:.2f} | 卖价: {sell_bid_price:.2f}"
            )
            return True
        except Exception as e:
            logger.error(f"执行失败: {str(e)}", exc_info=True)
            self.stats['failed_trades'] += 1
            return False

    async def load_common_pairs(self):
        """加载共同交易对（深度优化版本）"""
        def normalize_symbol(exchange_id: str, symbol: str) -> Optional[str]:
            """标准化基础货币名称"""
            # 统一特殊符号
            symbol = symbol.replace('XBT', 'BTC').replace('BCHSV', 'BSV')
            
            # OKX永续合约格式: BTC-USDT-SWAP → BTC
            if exchange_id == 'okx':
                parts = symbol.split('-')
                if len(parts) < 2 or parts[-1] != 'SWAP':
                    return None  # 非永续合约
                return parts[0].upper()
            
            # Binance永续合约格式: BTCUSDT → BTC
            elif exchange_id == 'binance':
                if '_' in symbol:  # 过滤交割合约 (如BTCUSDT_250627)
                    return None
                if not symbol.endswith('USDT'):
                    return None
                return symbol[:-4].upper()  # 移除USDT后缀
            
            return None

        # 构建标准化映射
        okx_coins = {}
        for m in self.okx.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('okx', m['id'])
            if coin:
                okx_coins[coin] = m['id']

        binance_coins = {}
        for m in self.binance.markets.values():
            if m['type'] != 'swap' or m['quote'] != 'USDT' or not m['active']:
                continue
            coin = normalize_symbol('binance', m['id'])
            if coin:
                binance_coins[coin] = m['id']

        # 匹配共同币种
        common_coins = set(okx_coins) & set(binance_coins)
        self.common_pairs = [
            (okx_coins[coin], binance_coins[coin])
            for coin in common_coins
        ]

        # 输出详细日志
        logger.info(f"OKX永续合约数: {len(okx_coins)} 样例: {list(okx_coins.values())[:5]}")
        logger.info(f"Binance永续合约数: {len(binance_coins)} 样例: {list(binance_coins.values())[:5]}")
        logger.info(f"有效共同交易对: {len(self.common_pairs)} 样例: {self.common_pairs[:5]}")

    
    async def find_best_arbitrage_opportunity(self) -> Optional[Dict]:
        """寻找最佳套利机会"""
        self.stats['total_checks'] += 1
        opportunities = []

        async def check_pair(okx_sym: str, binance_sym: str):
            async with self.semaphore:
                try:
                    okx_book, binance_book = await asyncio.gather(
                        self.get_orderbook(self.okx, okx_sym),
                        self.get_orderbook(self.binance, binance_sym)
                    )
                    if not okx_book or not binance_book:
                        return None

                    # 策略1: OKX -> Binance
                    okx_ask = okx_book['asks'][0][0]
                    binance_bid = binance_book['bids'][0][0]
                    spread1 = (binance_bid - okx_ask) / okx_ask
                    threshold1 = self.calc_dynamic_spread('okx', 'binance', okx_sym, binance_sym)
                    
                    # 策略2: Binance -> OKX 
                    binance_ask = binance_book['asks'][0][0]
                    okx_bid = okx_book['bids'][0][0]
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
        
        # 过滤有效机会
        valid_opps = [res for res in results if isinstance(res, dict)]
        self.optimal_opportunities = sorted(valid_opps, key=lambda x: x['spread'], reverse=True)[:30]
        return self.optimal_opportunities[0] if self.optimal_opportunities else None

    async def arbitrage_loop(self):
        """主套利循环"""
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

    # ------------------------- WEB接口（保持原始结构）-------------------------
    async def run_web_server(self):
        """启动Web服务（完整原始接口）"""
        routes = web.RouteTableDef()

        @routes.get('/')
        async def index(request):
            html = """
            <html><head><title>套利监控</title><style>
                body {font-family: Arial; padding: 20px}
                table {border-collapse: collapse; width: 100%}
                th, td {border: 1px solid #ddd; padding: 8px; text-align: right}
                th {background-color: #f2f2f2}
            </style></head>
            <body>
                <h1>套利监控面板</h1>
                <p>接口列表：</p>
                <ul>
                    <li>/api/status - 系统状态</li>
                    <li>/api/logs - 最新日志</li>
                    <li>/api/optimals - 套利机会</li>
                    <li>/api/config - 配置管理</li>
                </ul>
            </body></html>
            """
            return web.Response(text=html, content_type='text/html')

        @routes.get('/api/status')
        async def get_status(request):
            await self.update_balances()
            total = self.balances['okx'] + self.balances['binance']
            profit_rate = (self.profits['total'] / total * 100) if total > 0 else 0
            
            return web.json_response({
                'status': {
                    'running': self.is_running,
                    'paused': self.is_paused,
                    'uptime': str(datetime.now() - self.stats['start_time']),
                    'total_trades': self.stats['successful_trades']
                },
                'balances': {
                    'okx': float(self.balances['okx']),
                    'binance': float(self.balances['binance'])
                },
                'profits': {
                    'total': float(self.profits['total']),
                    'today': float(self.profits['today']),
                    'rate': float(profit_rate)
                },
                'trading': {
                    'current_amount': float(self.trade_usdt),
                    'max_amount': float(self.config['max_trade_usdt'])
                },
                'opportunities': self.optimal_opportunities[:10]
            })

        @routes.get('/api/logs')
        async def get_logs(request):
            return web.json_response({'logs': mem_handler.buffer[-100:]})

        @routes.get('/api/optimals')
        async def get_optimals(request):
            return web.json_response({'opportunities': self.optimal_opportunities[:30]})

        @routes.post('/api/control')
        async def control(request):
            data = await request.json()
            cmd = data.get('cmd', '').lower()
            
            if cmd == 'pause':
                self.is_paused = True
                logger.info("策略暂停")
            elif cmd == 'resume':
                self.is_paused = False
                logger.info("策略恢复")
            elif cmd == 'stop':
                await self.shutdown()
            else:
                return web.json_response({'status': 'error', 'message': '无效指令'})
            
            return web.json_response({'status': 'success', 'cmd': cmd})

        app = web.Application()
        app.add_routes(routes)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', CONFIG['webserver_port'])
        await self.site.start()
        logger.info("Web服务已启动: http://0.0.0.0:5000")

async def main():
    bot = ArbitrageBot()

    def signal_handler(signum, frame):
        logger.info("收到终止信号")
        asyncio.create_task(bot.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 初始化交易所
        await asyncio.gather(
            bot.okx.load_markets(),
            bot.binance.load_markets()
        )
        await bot.load_common_pairs()
        if not bot.common_pairs:
            raise RuntimeError("无有效交易对")
        
        # 启动核心任务
        await asyncio.gather(
            bot.arbitrage_loop(),
            bot.run_web_server(),
            bot.update_funding_fees()
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"致命错误: {str(e)}")
    finally:
        await asyncio.sleep(0.1)
        logger.info("系统关闭完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" not in str(e):
            raise
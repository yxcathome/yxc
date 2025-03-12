import ccxt.async_support as ccxt
import asyncio
from decimal import Decimal
from typing import Dict, Optional, List
import json
import hmac
import hashlib
import time
from datetime import datetime
import websockets
from exchanges.base_exchange import BaseExchange
from utils.logger import setup_logger

class BinanceExchange(BaseExchange):
    def __init__(self):
        super().__init__('binance')
        self.ccxt_client = ccxt.binance({
            'apiKey': self.config['api_key'],
            'secret': self.config['secret_key'],
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
                'recvWindow': 60000
            }
        })
        self.ws_url = 'wss://fstream.binance.com/ws'
        self.ws_private_url = 'wss://fstream.binance.com/ws'
        self.listen_key = None
        self.listen_key_timer = None

    async def connect(self) -> bool:
        """连接交易所"""
        try:
            await self.load_markets()
            self.listen_key = await self._get_listen_key()
            asyncio.create_task(self._maintain_ws_connection())
            asyncio.create_task(self._maintain_private_ws_connection())
            asyncio.create_task(self._keep_listen_key_alive())
            self.active = True
            self.logger.info("Binance交易所连接成功")
            return True
        except Exception as e:
            self.logger.error(f"Binance交易所连接失败: {e}")
            return False

    async def load_markets(self) -> Dict:
        """加载市场数据"""
        try:
            self.markets = await self.ccxt_client.load_markets()
            return self.markets
        except Exception as e:
            self.logger.error(f"加载市场数据失败: {e}")
            raise

    async def create_order(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None) -> Dict:
        """创建订单"""
        try:
            params = {
                'marginMode': 'cross',  # 全仓模式
                'reduceOnly': False
            }
            
            # 对于市价单，计算实际下单金额
            if order_type == 'market':
                ticker = await self.fetch_ticker(symbol)
                if not ticker:
                    raise ValueError("无法获取市场价格")
                # 使用当前价格的1.005倍作为市价单的价格限制
                price = Decimal(str(ticker['last'])) * Decimal('1.005')

            order = await self.ccxt_client.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=float(amount),
                price=float(price) if price else None,
                params=params
            )
            
            self.logger.info(f"创建订单成功: {order}")
            return order
        except Exception as e:
            self.logger.error(f"创建订单失败: {e}")
            raise

    async def fetch_position(self, symbol: str) -> Dict:
        """获取持仓信息"""
        try:
            positions = await self.ccxt_client.fetch_positions([symbol])
            if positions:
                position = positions[0]
                return {
                    'symbol': position['symbol'],
                    'size': Decimal(str(position['contracts'])),
                    'side': 'long' if position['contracts'] > 0 else 'short',
                    'entry_price': Decimal(str(position['entryPrice'])),
                    'leverage': position['leverage'],
                    'unrealized_pnl': Decimal(str(position['unrealizedPnl'])),
                    'margin_mode': position['marginMode']
                }
            return None
        except Exception as e:
            self.logger.error(f"获取持仓信息失败: {e}")
            raise

    async def _get_listen_key(self) -> str:
        """获取WebSocket监听密钥"""
        try:
            response = await self.ccxt_client.fapiPrivatePostListenKey()
            return response['listenKey']
        except Exception as e:
            self.logger.error(f"获取监听密钥失败: {e}")
            raise

    async def _keep_listen_key_alive(self):
        """保持监听密钥有效"""
        while True:
            try:
                await asyncio.sleep(1800)  # 30分钟
                if self.listen_key:
                    await self.ccxt_client.fapiPrivatePutListenKey({'listenKey': self.listen_key})
                    self.logger.debug("监听密钥续期成功")
            except Exception as e:
                self.logger.error(f"监听密钥续期失败: {e}")

    async def _maintain_ws_connection(self):
        """维护WebSocket公共连接"""
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    # 订阅行情数据
                    subscribe_message = {
                        "method": "SUBSCRIBE",
                        "params": [
                            "btcusdt@depth20@100ms",  # 订单簿
                            "btcusdt@aggTrade"        # 成交信息
                        ],
                        "id": 1
                    }
                    await ws.send(json.dumps(subscribe_message))
                    
                    while True:
                        message = await ws.recv()
                        await self._handle_ws_message(json.loads(message))
                        
            except Exception as e:
                self.logger.error(f"WebSocket连接断开: {e}")
                await asyncio.sleep(5)

    async def _maintain_private_ws_connection(self):
        """维护WebSocket私有连接"""
        while True:
            try:
                url = f"{self.ws_private_url}/{self.listen_key}"
                async with websockets.connect(url) as ws:
                    while True:
                        message = await ws.recv()
                        await self._handle_private_ws_message(json.loads(message))
            except Exception as e:
                self.logger.error(f"私有WebSocket连接断开: {e}")
                await asyncio.sleep(5)

    async def _handle_ws_message(self, message: Dict):
        """处理WebSocket公共消息"""
        try:
            if 'e' in message:
                if message['e'] == 'depthUpdate':
                    symbol = message['s']
                    await self.update_orderbook(symbol, {
                        'bids': message['b'],
                        'asks': message['a']
                    })
                elif message['e'] == 'aggTrade':
                    # 处理成交信息
                    symbol = message['s']
                    price = Decimal(str(message['p']))
                    quantity = Decimal(str(message['q']))
                    self.last_update[symbol] = {
                        'price': price,
                        'quantity': quantity,
                        'timestamp': datetime.fromtimestamp(message['T'] / 1000)
                    }
        except Exception as e:
            self.logger.error(f"处理WebSocket消息失败: {e}")

    async def _handle_private_ws_message(self, message: Dict):
        """处理WebSocket私有消息"""
        try:
            if 'e' in message:
                if message['e'] == 'ORDER_TRADE_UPDATE':
                    # 处理订单更新
                    order_info = message['o']
                    symbol = order_info['s']
                    order_id = order_info['i']
                    status = order_info['X']
                    
                    self.logger.info(f"订单更新: {symbol} {order_id} {status}")
                    
                elif message['e'] == 'ACCOUNT_UPDATE':
                    # 处理账户更新
                    positions = message['a']['P']
                    for position in positions:
                        symbol = position['s']
                        self.positions[symbol] = {
                            'amount': Decimal(str(position['pa'])),
                            'entry_price': Decimal(str(position['ep'])),
                            'unrealized_pnl': Decimal(str(position['up']))
                        }
        except Exception as e:
            self.logger.error(f"处理私有WebSocket消息失败: {e}")

    async def close(self):
        """关闭连接"""
        try:
            if self._ws:
                await self._ws.close()
            if self.listen_key:
                await self.ccxt_client.fapiPrivateDeleteListenKey({'listenKey': self.listen_key})
            await self.ccxt_client.close()
        except Exception as e:
            self.logger.error(f"关闭连接失败: {e}")
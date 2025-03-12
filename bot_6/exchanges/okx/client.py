import ccxt.async_support as ccxt
import asyncio
from decimal import Decimal
from typing import Dict, Optional
import json
import hmac
import base64
import time
from datetime import datetime
from urllib.parse import urlencode
import websockets
from exchanges.base_exchange import BaseExchange

class OKXExchange(BaseExchange):
    def __init__(self):
        super().__init__('okx')
        self.ccxt_client = ccxt.okx({
            'apiKey': self.config['api_key'],
            'secret': self.config['secret_key'],
            'password': self.config['password'],
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True
            }
        })
        self.ws_url = 'wss://ws.okx.com:8443/ws/v5/public'
        self.ws_private_url = 'wss://ws.okx.com:8443/ws/v5/private'
        
    async def connect(self) -> bool:
        """连接交易所"""
        try:
            await self.load_markets()
            # 启动WebSocket连接
            asyncio.create_task(self._maintain_ws_connection())
            asyncio.create_task(self._maintain_private_ws_connection())
            self.active = True
            self.logger.info("OKX交易所连接成功")
            return True
        except Exception as e:
            self.logger.error(f"OKX交易所连接失败: {e}")
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
                'tdMode': 'cross',  # 全仓模式
            }
            
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

    async def _maintain_ws_connection(self):
        """维护WebSocket连接"""
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    # 订阅行情数据
                    subscribe_message = {
                        "op": "subscribe",
                        "args": [
                            {
                                "channel": "books",
                                "instId": "BTC-USDT-SWAP"
                            }
                        ]
                    }
                    await ws.send(json.dumps(subscribe_message))
                    
                    while True:
                        message = await ws.recv()
                        await self._handle_ws_message(json.loads(message))
                        
            except Exception as e:
                self.logger.error(f"WebSocket连接断开: {e}")
                await asyncio.sleep(5)

    async def _handle_ws_message(self, message: Dict):
        """处理WebSocket消息"""
        try:
            if 'event' in message:
                if message['event'] == 'subscribe':
                    self.logger.info(f"订阅成功: {message}")
                elif message['event'] == 'error':
                    self.logger.error(f"WebSocket错误: {message}")
            elif 'data' in message:
                # 处理订单簿数据
                if message.get('arg', {}).get('channel') == 'books':
                    symbol = message['arg']['instId']
                    await self.update_orderbook(symbol, {
                        'bids': message['data'][0]['bids'],
                        'asks': message['data'][0]['asks']
                    })
        except Exception as e:
            self.logger.error(f"处理WebSocket消息失败: {e}")

    def _generate_signature(self, timestamp: str, method: str, 
                          request_path: str, body: str = '') -> str:
        """生成签名"""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            bytes(self.config['secret_key'], encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        d = mac.digest()
        return base64.b64encode(d).decode()

    async def close(self):
        """关闭连接"""
        if self._ws:
            await self._ws.close()
        await self.ccxt_client.close()
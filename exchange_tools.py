import ccxt.async_support as ccxt
import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 缓存文件路径
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

class CryptoExchangeTools:
    def __init__(self, exchange_name: str, api_key: str, secret: str, password: Optional[str] = None):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.secret = secret
        self.password = password
        self.exchange = self._initialize_exchange()

    def _initialize_exchange(self):
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.secret,
            'options': {'defaultType': 'swap', 'adjustForTimeDifference': True},
            'enableRateLimit': True,
            'timeout': 15000
        }
        if self.password:
            exchange_config['password'] = self.password

        if self.exchange_name == 'okx':
            return ccxt.okx(exchange_config)
        elif self.exchange_name == 'binance':
            return ccxt.binance(exchange_config)
        else:
            raise ValueError(f"不支持的交易所: {self.exchange_name}")

    async def get_contract_pairs(self) -> List[str]:
        cache_file = os.path.join(CACHE_DIR, f"{self.exchange_name}_contract_pairs.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return json.load(f)

        try:
            await self.exchange.load_markets()
            contract_pairs = [symbol for symbol, market in self.exchange.markets.items() if market['type'] == 'swap' and market['quote'] == 'USDT']
            with open(cache_file, "w") as f:
                json.dump(contract_pairs, f)
            return contract_pairs
        except Exception as e:
            logger.error(f"获取{self.exchange_name}合约交易对失败: {str(e)}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        await asyncio.sleep(0.1)  # 每次请求间隔 0.1 秒
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            if not ticker or 'last' not in ticker or 'percentage' not in ticker:
                logger.warning(f"获取{self.exchange.id} {symbol} ticker 数据不完整")
                return None

            last_price = float(ticker['last']) if ticker['last'] is not None else 0.0
            price_change_percent = float(ticker['percentage']) if ticker['percentage'] is not None else 0.0

            return {
                'symbol': symbol,
                'last_price': last_price,
                'price_change_percent': price_change_percent
            }
        except Exception as e:
            logger.error(f"获取{self.exchange.id} {symbol} ticker 失败: {str(e)}")
            return None

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        def normalize_symbol(symbol):
            return symbol.replace("/", "_").replace(":", "_")

        normalized_symbol = normalize_symbol(symbol)  # 规范化合约符号
        cache_file = os.path.join(CACHE_DIR, f"{self.exchange_name}_funding_rate_{normalized_symbol}.json")

        # 如果缓存文件存在，直接读取
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                return json.load(f)

        try:
            if self.exchange.id == 'okx':
                instId = symbol.replace("/", "-").split(':')[0] + "-SWAP"
                res = await self.exchange.public_get_public_funding_rate({'instId': instId})
                funding_rate = float(res['data'][0]['fundingRate'])
            elif self.exchange.id == 'binance':
                res = await self.exchange.fetch_funding_rate(symbol)
                funding_rate = float(res['fundingRate'])
            else:
                funding_rate = 0.0

            # 保存到缓存文件
            with open(cache_file, "w") as f:
                json.dump(funding_rate, f)
            return funding_rate
        except Exception as e:
            logger.error(f"获取资金费率失败: {self.exchange.id} {symbol} - {str(e)}")
            return None
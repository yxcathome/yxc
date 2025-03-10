from enum import Enum

class StrategyMode(Enum):
    CONSERVATIVE = 'conservative'
    NORMAL = 'normal'
    AGGRESSIVE = 'aggressive'

class ExchangeType(Enum):
    OKX = 'okx'
    BINANCE = 'binance'

TRADE_FEES = {
    'okx': {'maker': 0.0002, 'taker': 0.0005},
    'binance': {'maker': 0.0002, 'taker': 0.0004}
}

MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
HEARTBEAT_INTERVAL = 30
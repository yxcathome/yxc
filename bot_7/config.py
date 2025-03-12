from typing import Dict, List
import os
from dataclasses import dataclass
from enum import Enum

class MarketState(Enum):
    RANGING = "ranging"        # 震荡
    TRENDING = "trending"      # 趋势
    VOLATILE = "volatile"      # 剧烈波动
    SIDEWAYS = "sideways"      # 横盘整理

@dataclass
class ExchangeConfig:
    api_key: str
    api_secret: str
    min_order_value: float    # 最小下单金额(USDT)
    min_contract_qty: float   # 最小合约数量
    maker_fee: float         # Maker手续费率
    taker_fee: float         # Taker手续费率

class Config:
    # 交易所配置
    EXCHANGES: Dict[str, ExchangeConfig] = {
        "binance": ExchangeConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_SECRET_KEY", ""),
            min_order_value=5.0,
            min_contract_qty=0.001,
            maker_fee=0.0002,
            taker_fee=0.0004
        ),
        "okx": ExchangeConfig(
            api_key=os.getenv("OKX_API_KEY", ""),
            api_secret=os.getenv("OKX_SECRET_KEY", ""),
            min_order_value=1.0,
            min_contract_qty=1.0,
            maker_fee=0.0002,
            taker_fee=0.0005
        )
    }

    # 交易参数
    TRADING_PAIRS: List[str] = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    TIMEFRAMES: List[str] = ["1m", "5m", "15m", "1h", "4h"]
    BASE_TIMEFRAME: str = "5m"
    
    # 策略参数
    POSITION_SIZE_PCT: float = 0.1  # 单次开仓占总资金比例
    MAX_POSITIONS: int = 3          # 最大同时持仓数
    
    # 风控参数
    MAX_DRAWDOWN_PCT: float = 0.1   # 最大回撤限制
    STOP_LOSS_PCT: float = 0.05     # 止损比例
    TAKE_PROFIT_PCT: float = 0.15   # 止盈比例
    
    # 市场状态判断参数
    VOLATILITY_THRESHOLD: float = 0.02  # 波动率阈值
    TREND_STRENGTH_THRESHOLD: float = 0.7  # 趋势强度阈值
    
    # 均值回归策略参数
    MEAN_REVERSION_PERIOD: int = 20
    MEAN_REVERSION_STD: float = 2.0
    
    # 趋势策略参数
    FAST_MA_PERIOD: int = 10
    SLOW_MA_PERIOD: int = 20
    
    # 突破策略参数
    BREAKOUT_PERIOD: int = 20
    BREAKOUT_THRESHOLD: float = 2.0
    
    # 套利策略参数
    MIN_ARBITRAGE_SPREAD: float = 0.002  # 最小套利价差
    
    # 重试参数
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0  # 秒
    
    # 行情更新间隔
    MARKET_UPDATE_INTERVAL: float = 1.0  # 秒
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "trading_bot.log"
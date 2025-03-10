from decimal import Decimal
from typing import Dict
import logging
from datetime import datetime
import time
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.position_timestamps = {}
        self.trade_records = []
        self.daily_pnl = Decimal('0')
        self.last_reset = datetime.now()
        self.max_drawdown = Decimal('0')
        self.peak_equity = Decimal('0')
        
    async def can_trade(self, symbol: str, signal: Dict) -> bool:
        """综合风控检查"""
        try:
            current_time = datetime.now()
            
            # 重置每日统计
            if (current_time - self.last_reset).days >= 1:
                await self._reset_daily_stats()

            # 检查交易次数限制
            if len(self.trade_records) >= self.config['risk_control']['max_daily_trades']:
                logger.info("达到每日最大交易次数限制")
                return False

            # 检查亏损限制
            if self.daily_pnl <= -self.bot.start_equity['okx'] * self.config['risk_control']['max_daily_loss']:
                logger.info("达到每日最大亏损限制")
                return False

            # 检查最大回撤限制
            current_equity = self.bot.equity['okx']
            if current_equity > self.peak_equity:
                self.peak_equity = current_equity
            current_drawdown = (self.peak_equity - current_equity) / self.peak_equity
            if current_drawdown > self.config['risk_control']['max_drawdown']:
                logger.info(f"达到最大回撤限制: {current_drawdown:.2%}")
                return False

            # 检查持仓间隔
            if symbol in self.position_timestamps:
                position_age = time.time() - self.position_timestamps[symbol]
                if position_age < self.config['risk_control']['position_timeout']:
                    logger.info(f"{symbol} 持仓时间过短")
                    return False

            # 检查总仓位限制
            total_position = await self._calculate_total_position()
            max_position = self.bot.equity['okx'] * self.config['risk_control']['max_position_size']
            if total_position >= max_position:
                logger.info("达到最大仓位限制")
                return False

            # 检查价格波动
            if await self._check_price_volatility(symbol):
                return False

            # 检查流动性
            if not await self._check_liquidity(symbol):
                return False

            return True

        except Exception as e:
            logger.error(f"风控检查异常: {e}")
            return False

    async def _reset_daily_stats(self):
        """重置每日统计数据"""
        self.daily_pnl = Decimal('0')
        self.trade_records = []
        self.last_reset = datetime.now()
        logger.info("每日统计数据已重置")

    async def _calculate_total_position(self) -> Decimal:
        """计算当前总仓位"""
        try:
            positions = await self.bot.okx.fetch_positions() or []
            return sum(Decimal(str(pos['notional'])) for pos in positions if pos['notional'])
        except Exception as e:
            logger.error(f"计算总仓位异常: {e}")
            return Decimal('0')

    async def _check_price_volatility(self, symbol: str) -> bool:
        """检查价格波动"""
        try:
            ohlcv = await self.bot.okx.fetch_ohlcv(symbol, '1h', limit=2)
            if ohlcv and len(ohlcv) >= 2:
                price_change = abs(ohlcv[1][4] - ohlcv[0][4]) / ohlcv[0][4]
                if price_change > self.config['risk_control']['max_price_change_1h']:
                    logger.info(f"{symbol} 价格波动过大: {price_change:.2%}")
                    return True
            return False
        except Exception as e:
            logger.error(f"检查价格波动异常: {e}")
            return True

    async def _check_liquidity(self, symbol: str) -> bool:
        """检查流动性"""
        try:
            orderbook = await self.bot.okx.fetch_order_book(symbol)
            min_liquidity = self.config['risk_control']['min_liquidity']
            
            bid_liquidity = sum(Decimal(str(amount)) for _, amount in orderbook['bids'][:5])
            ask_liquidity = sum(Decimal(str(amount)) for _, amount in orderbook['asks'][:5])
            
            if bid_liquidity < min_liquidity or ask_liquidity < min_liquidity:
                logger.info(f"{symbol} 流动性不足")
                return False
            return True
        except Exception as e:
            logger.error(f"检查流动性异常: {e}")
            return False

    def record_trade(self, symbol: str, profit: Decimal):
        """记录交易"""
        self.trade_records.append({
            'time': datetime.now(),
            'symbol': symbol,
            'profit': profit
        })
        self.daily_pnl += profit
        
        # 更新最大回撤
        if profit < 0:
            current_equity = self.bot.equity['okx']
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            self.max_drawdown = max(self.max_drawdown, drawdown)

    def update_position_timestamp(self, symbol: str):
        """更新持仓时间戳"""
        self.position_timestamps[symbol] = time.time()
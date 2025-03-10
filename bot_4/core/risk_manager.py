import logging
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.max_daily_loss = Decimal(str(config['risk_control']['max_daily_loss']))
        self.max_position_size = Decimal(str(config['risk_control']['max_position_size']))
        self.daily_loss_reset_time = datetime.now().replace(hour=0, minute=0, second=0)

    async def can_trade(self, symbol: str, amount: Decimal) -> bool:
        # 每日UTC零点重置亏损统计
        if datetime.now() > self.daily_loss_reset_time.replace(hour=23, minute=59):
            self.daily_loss_reset_time = datetime.now().replace(hour=0, minute=0, second=0)
            self.bot.start_equity = self.bot.equity.copy()

        current_equity = sum(self.bot.equity.values())
        initial_equity = sum(self.bot.start_equity.values())
        
        # 1. 每日最大亏损限制
        daily_loss = (initial_equity - current_equity) / initial_equity
        if daily_loss > self.max_daily_loss:
            logger.warning(f"触发每日亏损限制：{daily_loss:.2%}")
            return False

        # 2. 单标的最大持仓限制
        position = await self.bot.exchanges['okx'].fetch_positions([symbol])
        if position and Decimal(position[0]['notional']) / current_equity > self.max_position_size:
            logger.warning(f"{symbol} 持仓超过限额")
            return False

        # 3. 系统运行状态检查
        if self.bot.is_paused or self.bot.is_shutting_down:
            return False

        return True

    async def force_close_positions(self):
        """强制平仓逻辑"""
        for exchange_id in ['okx', 'binance']:
            positions = await self.bot.exchanges[exchange_id].fetch_positions()
            for pos in positions:
                if pos['unrealizedPnl'] < -Decimal('0.02'):  # 单笔亏损超过2%时强平
                    await self.bot.exchanges[exchange_id].create_order(
                        pos['symbol'], 'market', 'sell' if pos['side'] == 'long' else 'buy', pos['contracts']
                    )
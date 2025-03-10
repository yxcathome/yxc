from decimal import Decimal
from typing import Dict, List, Optional
import logging
from .base import BaseStrategy
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class GridStrategy(BaseStrategy):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.name = "grid"
        self.is_active = config['enabled_strategies']['grid']
        self.grids = {}  # 存储每个交易对的网格
        self.positions = {}  # 存储持仓信息

    async def analyze(self, symbol: str) -> Optional[Dict]:
        try:
            if symbol not in self.grids:
                await self._init_grid(symbol)

            current_price = await self._get_current_price(symbol)
            if not current_price:
                return None

            grid = self.grids[symbol]
            
            # 检查是否触发网格交易
            for level in grid['levels']:
                if current_price >= level['lower'] and current_price < level['upper']:
                    if current_price <= level['buy_price']:
                        return {
                            'type': 'grid',
                            'action': 'buy',
                            'symbol': symbol,
                            'price': float(level['buy_price']),
                            'level': level['index']
                        }
                    elif current_price >= level['sell_price']:
                        return {
                            'type': 'grid',
                            'action': 'sell',
                            'symbol': symbol,
                            'price': float(level['sell_price']),
                            'level': level['index']
                        }

        except Exception as e:
            logger.error(f"网格分析异常: {e}")
        return None

    async def execute(self, signal: Dict) -> bool:
        try:
            if not await self.validate_signal(signal):
                return False

            symbol = signal['symbol']
            action = signal['action']
            price = Decimal(str(signal['price']))
            
            # 计算交易数量
            amount = self.bot.calculate_trade_amount('okx', price)
            
            # 执行交易
            order = await self.bot.okx.create_order(
                symbol,
                'limit',
                action,
                float(amount),
                float(price)
            )

            if order:
                level = signal['level']
                if symbol not in self.positions:
                    self.positions[symbol] = []
                
                position_info = {
                    'level': level,
                    'action': action,
                    'amount': amount,
                    'price': price,
                    'order_id': order['id']
                }
                
                self.positions[symbol].append(position_info)
                logger.info(f"网格交易执行成功: {symbol} {action} at {price}")
                return True

        except Exception as e:
            logger.error(f"网格执行异常: {e}")
        return False

    async def _init_grid(self, symbol: str) -> None:
        """初始化网格"""
        try:
            # 获取当前价格范围
            ticker = await self.bot.okx.fetch_ticker(symbol)
            current_price = Decimal(str(ticker['last']))
            
            # 设置网格参数
            grid_config = self.config['grid']
            grid_numbers = grid_config['grid_numbers']
            price_range = grid_config['price_range']
            
            # 计算网格区间
            upper_price = current_price * (1 + price_range)
            lower_price = current_price * (1 - price_range)
            grid_interval = (upper_price - lower_price) / (grid_numbers - 1)
            
            # 生成网格水平
            levels = []
            for i in range(grid_numbers):
                level_price = lower_price + grid_interval * i
                level = {
                    'index': i,
                    'lower': level_price,
                    'upper': level_price + grid_interval,
                    'buy_price': level_price,
                    'sell_price': level_price + grid_interval * grid_config['profit_ratio']
                }
                levels.append(level)
            
            self.grids[symbol] = {
                'levels': levels,
                'last_update': datetime.now()
            }
            
            logger.info(f"网格初始化完成: {symbol}, 网格数: {grid_numbers}")

        except Exception as e:
            logger.error(f"网格初始化异常: {e}")

    async def _get_current_price(self, symbol: str) -> Optional[Decimal]:
        """获取当前价格"""
        try:
            ticker = await self.bot.okx.fetch_ticker(symbol)
            return Decimal(str(ticker['last']))
        except Exception as e:
            logger.error(f"获取价格异常: {e}")
            return None

    async def update_grids(self):
        """定期更新网格"""
        while True:
            try:
                for symbol in list(self.grids.keys()):
                    if (datetime.now() - self.grids[symbol]['last_update']).hours >= 4:
                        await self._init_grid(symbol)
                
                await asyncio.sleep(3600)  # 每小时检查一次
                
            except Exception as e:
                logger.error(f"更新网格异常: {e}")
                await asyncio.sleep(60)
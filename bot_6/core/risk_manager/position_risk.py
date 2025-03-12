from decimal import Decimal
from typing import Dict, Optional, List
import asyncio
from datetime import datetime, timedelta
from utils.logger import setup_logger
from config.risk_config import POSITION_RISK_CONFIG

class PositionRiskManager:
    def __init__(self, bot):
        self.bot = bot
        self.logger = setup_logger("position_risk")
        self.config = POSITION_RISK_CONFIG
        
        # 仓位风控状态
        self.position_states = {}
        
        # 风控限制
        self.max_positions_per_symbol = 2  # 每个交易对最大持仓数
        self.min_order_interval = 5     # 最小下单间隔（秒）
        
    async def check_position(self, position_id: str) -> bool:
        """检查仓位风控"""
        try:
            position = self.bot.position_tracker.positions.get(position_id)
            if not position:
                return False
                
            # 检查基本参数
            if not await self._check_basic_params(position):
                return False
                
            # 检查持仓时间
            if not await self._check_holding_time(position):
                return False
                
            # 检查仓位盈亏
            if not await self._check_position_pnl(position):
                return False
                
            # 检查风险指标
            if not await self._check_risk_metrics(position):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查仓位风控失败: {e}")
            return False
            
    async def can_open_position(self, symbol: str, size: Decimal) -> bool:
        """检查是否可以开仓"""
        try:
            # 检查当前持仓数量
            symbol_positions = [
                pos for pos in self.bot.position_tracker.positions.values()
                if pos['symbol'] == symbol
            ]
            if len(symbol_positions) >= self.max_positions_per_symbol:
                return False
                
            # 检查仓位大小限制
            if size < self.config['min_position_size']:
                return False
            if size > self.config['max_position_size']:
                return False
                
            # 检查最近下单时间
            last_order_time = await self._get_last_order_time(symbol)
            if last_order_time:
                time_diff = (datetime.utcnow() - last_order_time).total_seconds()
                if time_diff < self.min_order_interval:
                    return False
                    
            # 检查杠杆限制
            leverage = await self._calculate_effective_leverage(symbol, size)
            if leverage > self.config['max_leverage']:
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查开仓条件失败: {e}")
            return False
            
    async def update_position_state(self, position_id: str, state: Dict):
        """更新仓位状态"""
        try:
            if position_id not in self.position_states:
                self.position_states[position_id] = {}
                
            self.position_states[position_id].update(state)
            
            # 检查是否需要调整止损
            if await self._should_update_stop_loss(position_id):
                await self._update_stop_loss(position_id)
                
        except Exception as e:
            self.logger.error(f"更新仓位状态失败: {e}")
            
    async def _check_basic_params(self, position: Dict) -> bool:
        """检查基本参数"""
        try:
            # 检查仓位大小
            if position['size'] < self.config['min_position_size']:
                return False
            if position['size'] > self.config['max_position_size']:
                return False
                
            # 检查杠杆倍数
            leverage = await self._calculate_effective_leverage(
                position['symbol'],
                position['size']
            )
            if leverage > self.config['max_leverage']:
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查基本参数失败: {e}")
            return False
            
    async def _check_holding_time(self, position: Dict) -> bool:
        """检查持仓时间"""
        try:
            hold_time = (datetime.utcnow() - position['entry_time']).total_seconds()
            
            # 检查是否超过最大持仓时间
            if hold_time > self.config['max_holding_time']:
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查持仓时间失败: {e}")
            return False
            
    async def _check_position_pnl(self, position: Dict) -> bool:
        """检查仓位盈亏"""
        try:
            unrealized_pnl = position.get('unrealized_pnl', Decimal('0'))
            entry_value = await self._calculate_position_value(position)
            
            if entry_value > 0:
                roi = unrealized_pnl / entry_value
                
                # 检查止损
                if roi < -self.config['stop_loss']['initial']:
                    return False
                    
                # 检查移动止损
                if 'trailing_stop' in position:
                    if unrealized_pnl < position['trailing_stop']:
                        return False
                        
                # 检查止盈
                if roi > self.config['take_profit']['target']:
                    # 部分止盈
                    if roi > self.config['take_profit']['partial']:
                        await self._take_partial_profit(position)
                        
            return True
            
        except Exception as e:
            self.logger.error(f"检查仓位盈亏失败: {e}")
            return False
            
    async def _check_risk_metrics(self, position: Dict) -> bool:
        """检查风险指标"""
        try:
            metrics = position.get('risk_metrics', {})
            
            # 检查回撤
            if metrics.get('drawdown', Decimal('0')) > Decimal('0.1'):  # 10%回撤
                return False
                
            # 检查波动率
            if metrics.get('volatility', Decimal('0')) > Decimal('0.05'):  # 5%波动率
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查风险指标失败: {e}")
            return False
            
    async def _calculate_effective_leverage(self, symbol: str, size: Decimal) -> Decimal:
        """计算有效杠杆"""
        try:
            # 获取账户余额
            total_balance = await self.bot.global_risk._get_total_balance()
            if not total_balance:
                return Decimal('0')
                
            # 计算仓位价值
            position_value = size
            for exchange_name, exchange in self.bot.exchanges.items():
                ticker = await exchange.fetch_ticker(symbol)
                if ticker:
                    price = Decimal(str(ticker['last']))
                    position_value = size * price
                    break
                    
            # 计算杠杆倍数
            if position_value > 0:
                return position_value / total_balance
                
            return Decimal('0')
            
        except Exception as e:
            self.logger.error(f"计算有效杠杆失败: {e}")
            return Decimal('0')
            
    async def _calculate_position_value(self, position: Dict) -> Decimal:
        """计算仓位价值"""
        try:
            total_value = Decimal('0')
            
            for exchange_name, order in position['orders'].items():
                price = Decimal(str(order['price']))
                size = Decimal(str(order['filled']))
                value = price * size
                total_value += value
                
            return total_value
            
        except Exception as e:
            self.logger.error(f"计算仓位价值失败: {e}")
            return Decimal('0')
            
    async def _get_last_order_time(self, symbol: str) -> Optional[datetime]:
        """获取最近下单时间"""
        try:
            last_order = None
            for order_info in self.bot.position_tracker.active_orders.values():
                if order_info['order']['symbol'] == symbol:
                    if not last_order or order_info['created_at'] > last_order:
                        last_order = order_info['created_at']
                        
            return last_order
            
        except Exception as e:
            self.logger.error(f"获取最近下单时间失败: {e}")
            return None
            
    async def _should_update_stop_loss(self, position_id: str) -> bool:
        """检查是否需要更新止损"""
        try:
            position = self.bot.position_tracker.positions.get(position_id)
            if not position:
                return False
                
            unrealized_pnl = position.get('unrealized_pnl', Decimal('0'))
            entry_value = await self._calculate_position_value(position)
            
            if entry_value > 0:
                roi = unrealized_pnl / entry_value
                
                # 盈利超过1%时更新止损
                return roi > Decimal('0.01')
                
            return False
            
        except Exception as e:
            self.logger.error(f"检查是否需要更新止损失败: {e}")
            return False
            
    async def _update_stop_loss(self, position_id: str):
        """更新止损价格"""
        try:
            position = self.bot.position_tracker.positions.get(position_id)
            if not position:
                return
                
            unrealized_pnl = position.get('unrealized_pnl', Decimal('0'))
            
            # 设置移动止损
            if unrealized_pnl > 0:
                position['trailing_stop'] = unrealized_pnl * (1 - self.config['stop_loss']['trailing'])
                self.logger.info(f"更新移动止损: {position_id} -> {position['trailing_stop']}")
                
        except Exception as e:
            self.logger.error(f"更新止损价格失败: {e}")
            
    async def _take_partial_profit(self, position: Dict):
        """部分止盈"""
        try:
            # 平仓一半仓位
            close_size = position['size'] / 2
            
            for exchange_name, order in position['orders'].items():
                exchange = self.bot.exchanges[exchange_name]
                
                close_order = await exchange.create_order(
                    symbol=position['symbol'],
                    order_type='market',
                    side='sell' if position['direction'] == 'buy' else 'buy',
                    amount=close_size
                )
                
                if close_order:
                    self.logger.info(f"部分止盈成功: {position['id']} -> {close_size}")
                    
        except Exception as e:
            self.logger.error(f"部分止盈失败: {e}")
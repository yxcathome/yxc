from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
from utils.logger import setup_logger

class GlobalRiskManager:
    def __init__(self, exchange_manager):
        self.exchange_manager = exchange_manager
        self.logger = setup_logger("risk_manager")
        
        # 全局风控参数
        self.max_positions = 4  # 最大同时持仓数
        self.max_drawdown = Decimal('0.1')  # 最大回撤 10%
        self.daily_loss_limit = Decimal('0.05')  # 日亏损限制 5%
        self.position_size_limit = Decimal('0.3')  # 单个仓位资金比例限制 30%
        
        # 状态追踪
        self.positions = {}  # 当前持仓
        self.daily_pnl = Decimal('0')  # 当日盈亏
        self.initial_balance = None  # 初始余额
        self.peak_balance = None  # 峰值余额
        self.last_reset = datetime.utcnow()  # 上次重置时间
        
    async def initialize(self):
        """初始化风控系统"""
        try:
            # 获取初始余额
            total_balance = Decimal('0')
            for exchange in self.exchange_manager.exchanges.values():
                balance = await exchange.fetch_balance()
                if balance and 'total' in balance:
                    total_balance += Decimal(str(balance['total'].get('USDT', 0)))
                    
            self.initial_balance = total_balance
            self.peak_balance = total_balance
            
            # 启动监控任务
            asyncio.create_task(self._monitor_daily_reset())
            asyncio.create_task(self._monitor_positions())
            
            self.logger.info(f"风控系统初始化完成，初始余额: {self.initial_balance} USDT")
            return True
            
        except Exception as e:
            self.logger.error(f"风控系统初始化失败: {e}")
            return False
            
    async def can_open_position(self, strategy_name: str, symbol: str, 
                              signal: Dict) -> bool:
        """检查是否可以开新仓位"""
        try:
            # 检查持仓数量
            if len(self.positions) >= self.max_positions:
                self.logger.warning("达到最大持仓数量限制")
                return False
                
            # 检查日亏损限制
            if self.daily_pnl <= -self.daily_loss_limit * self.initial_balance:
                self.logger.warning("达到日亏损限制")
                return False
                
            # 检查回撤限制
            current_balance = await self._get_total_balance()
            if current_balance:
                drawdown = (self.peak_balance - current_balance) / self.peak_balance
                if drawdown > self.max_drawdown:
                    self.logger.warning(f"达到最大回撤限制: {drawdown}")
                    return False
                    
            # 检查币种敞口
            exposure = await self._calculate_symbol_exposure(symbol)
            if exposure > self.position_size_limit:
                self.logger.warning(f"币种 {symbol} 敞口过大: {exposure}")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查开仓条件失败: {e}")
            return False
            
    async def register_position(self, strategy_name: str, symbol: str, 
                              position_info: Dict) -> bool:
        """注册新持仓"""
        try:
            position_id = f"{strategy_name}_{symbol}_{datetime.utcnow().timestamp()}"
            self.positions[position_id] = {
                'strategy': strategy_name,
                'symbol': symbol,
                'entry_time': datetime.utcnow(),
                'info': position_info,
                'realized_pnl': Decimal('0')
            }
            
            self.logger.info(f"注册新持仓: {position_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"注册持仓失败: {e}")
            return False
            
    async def update_position_pnl(self, position_id: str, pnl: Decimal):
        """更新持仓盈亏"""
        try:
            if position_id in self.positions:
                self.positions[position_id]['realized_pnl'] = pnl
                self.daily_pnl += pnl
                
                # 更新峰值余额
                current_balance = await self._get_total_balance()
                if current_balance and current_balance > self.peak_balance:
                    self.peak_balance = current_balance
                    
                self.logger.info(f"更新持仓盈亏: {position_id}, PNL: {pnl}")
                
        except Exception as e:
            self.logger.error(f"更新持仓盈亏失败: {e}")
            
    async def _monitor_daily_reset(self):
        """监控日重置"""
        while True:
            try:
                current_time = datetime.utcnow()
                if current_time.date() > self.last_reset.date():
                    # 重置日统计
                    self.daily_pnl = Decimal('0')
                    self.last_reset = current_time
                    self.logger.info("执行日统计重置")
                    
                await asyncio.sleep(60)  # 每分钟检查
                
            except Exception as e:
                self.logger.error(f"日重置监控异常: {e}")
                await asyncio.sleep(5)
                
    async def _monitor_positions(self):
        """监控持仓状态"""
        while True:
            try:
                current_time = datetime.utcnow()
                for position_id, position in list(self.positions.items()):
                    # 更新未实现盈亏
                    unrealized_pnl = await self._calculate_unrealized_pnl(position)
                    if unrealized_pnl:
                        position['unrealized_pnl'] = unrealized_pnl
                        
                    # 检查止损条件
                    if unrealized_pnl and unrealized_pnl < -self.position_size_limit * self.initial_balance:
                        self.logger.warning(f"触发止损: {position_id}")
                        # 发送止损信号
                        await self._trigger_stop_loss(position_id)
                        
                await asyncio.sleep(5)  # 每5秒检查一次
                
            except Exception as e:
                self.logger.error(f"持仓监控异常: {e}")
                await asyncio.sleep(5)
                
    async def _get_total_balance(self) -> Optional[Decimal]:
        """获取总余额"""
        try:
            total_balance = Decimal('0')
            for exchange in self.exchange_manager.exchanges.values():
                balance = await exchange.fetch_balance()
                if balance and 'total' in balance:
                    total_balance += Decimal(str(balance['total'].get('USDT', 0)))
            return total_balance
            
        except Exception as e:
            self.logger.error(f"获取总余额失败: {e}")
            return None
            
    async def _calculate_symbol_exposure(self, symbol: str) -> Decimal:
        """计算币种敞口"""
        try:
            exposure = Decimal('0')
            total_balance = await self._get_total_balance()
            if not total_balance:
                return Decimal('0')
                
            for position in self.positions.values():
                if position['symbol'] == symbol:
                    # 计算持仓价值
                    position_value = Decimal('0')
                    for exchange_name, order in position['info']['orders'].items():
                        amount = Decimal(str(order['amount']))
                        price = Decimal(str(order['price']))
                        position_value += amount * price
                        
                    exposure += position_value / total_balance
                    
            return exposure
            
        except Exception as e:
            self.logger.error(f"计算币种敞口失败: {e}")
            return Decimal('0')
            
    async def _calculate_unrealized_pnl(self, position: Dict) -> Optional[Decimal]:
        """计算未实现盈亏"""
        try:
            total_pnl = Decimal('0')
            for exchange_name, order in position['info']['orders'].items():
                exchange = self.exchange_manager.exchanges[exchange_name]
                current_price = await exchange.get_best_price(position['symbol'])
                if not current_price:
                    continue
                    
                entry_price = Decimal(str(order['price']))
                amount = Decimal(str(order['amount']))
                
                if order['side'] == 'buy':
                    pnl = (current_price['bid'] - entry_price) * amount
                else:
                    pnl = (entry_price - current_price['ask']) * amount
                    
                total_pnl += pnl
                
            return total_pnl
            
        except Exception as e:
            self.logger.error(f"计算未实现盈亏失败: {e}")
            return None
            
    async def _trigger_stop_loss(self, position_id: str):
        """触发止损"""
        try:
            position = self.positions[position_id]
            # 创建市价平仓订单
            close_orders = {}
            for exchange_name, order in position['info']['orders'].items():
                exchange = self.exchange_manager.exchanges[exchange_name]
                side = 'sell' if order['side'] == 'buy' else 'buy'
                
                close_order = await exchange.create_order(
                    symbol=position['symbol'],
                    order_type='market',
                    side=side,
                    amount=order['amount']
                )
                close_orders[exchange_name] = close_order
                
            # 更新持仓状态
            realized_pnl = await self._calculate_realized_pnl(position, close_orders)
            if realized_pnl is not None:
                await self.update_position_pnl(position_id, realized_pnl)
                
            del self.positions[position_id]
            self.logger.info(f"止损平仓完成: {position_id}, PNL: {realized_pnl}")
            
        except Exception as e:
            self.logger.error(f"触发止损失败: {e}")
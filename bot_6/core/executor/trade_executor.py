from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime
import asyncio
from utils.logger import setup_logger
from .order_manager import OrderManager

class TradeExecutor:
    def __init__(self, exchange_manager, risk_manager):
        self.exchange_manager = exchange_manager
        self.risk_manager = risk_manager
        self.order_manager = OrderManager(exchange_manager)
        self.logger = setup_logger("trade_executor")
        
        # 执行配置
        self.max_slippage = Decimal('0.002')  # 最大滑点 0.2%
        self.order_chunk_size = Decimal('0.3')  # 单次下单比例 30%
        self.min_order_interval = 1  # 最小下单间隔(秒)
        
        # 执行状态
        self.executing_trades = {}
        self.last_order_time = {}
        
    async def execute_trade(self, strategy_name: str, signal: Dict) -> bool:
        """执行交易"""
        try:
            # 生成交易ID
            trade_id = f"{strategy_name}_{signal['symbol']}_{datetime.utcnow().timestamp()}"
            
            # 检查风控
            if not await self.risk_manager.can_open_position(strategy_name, signal['symbol'], signal):
                return False
                
            # 计算下单大小
            position_size = await self._calculate_order_size(signal)
            if not position_size:
                return False
                
            # 执行分批下单
            success = await self._execute_chunked_orders(trade_id, signal, position_size)
            if success:
                # 注册持仓
                position_info = self.executing_trades[trade_id]
                await self.risk_manager.register_position(
                    strategy_name,
                    signal['symbol'],
                    position_info
                )
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"执行交易失败: {e}")
            return False
            
    async def close_position(self, position_id: str) -> bool:
        """平仓"""
        try:
            position = await self.risk_manager.get_position(position_id)
            if not position:
                return False
                
            # 创建平仓订单
            close_orders = {}
            for exchange_name, order in position['info']['orders'].items():
                # 计算平仓方向
                side = 'sell' if order['side'] == 'buy' else 'buy'
                
                # 创建市价平仓订单
                order_params = {
                    'symbol': position['symbol'],
                    'type': 'market',
                    'side': side,
                    'amount': order['amount']
                }
                
                result = await self.order_manager.place_order(exchange_name, order_params)
                if result:
                    close_orders[exchange_name] = result
                else:
                    # 平仓失败，需要取消已成功的订单
                    for done_order_id in close_orders.values():
                        await self.order_manager.cancel_order(done_order_id)
                    return False
                    
            # 更新持仓状态
            realized_pnl = await self._calculate_realized_pnl(position, close_orders)
            if realized_pnl is not None:
                await self.risk_manager.update_position_pnl(position_id, realized_pnl)
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"平仓失败: {e}")
            return False
            
    async def _calculate_order_size(self, signal: Dict) -> Optional[Decimal]:
        """计算下单大小"""
        try:
            # 获取可用余额
            available_balance = await self.risk_manager.get_available_balance()
            if not available_balance:
                return None
                
            # 基于信号强度计算仓位
            position_size = available_balance * Decimal('0.1')  # 基础10%仓位
            
            # 根据信号强度调整
            if 'strength' in signal:
                strength = Decimal(str(signal['strength']))
                if strength < Decimal('0.5'):
                    position_size *= Decimal('0.5')
                elif strength > Decimal('1.5'):
                    position_size *= Decimal('1.5')
                    
            return position_size
            
        except Exception as e:
            self.logger.error(f"计算下单大小失败: {e}")
            return None
            
    async def _execute_chunked_orders(self, trade_id: str, signal: Dict,
                                    total_size: Decimal) -> bool:
        """分批执行订单"""
        try:
            self.executing_trades[trade_id] = {
                'orders': {},
                'status': 'executing',
                'start_time': datetime.utcnow()
            }
            
            # 计算每批数量
            chunk_size = total_size * self.order_chunk_size
            remaining_size = total_size
            
            while remaining_size > 0:
                for exchange_name in signal['exchanges']:
                    # 检查下单间隔
                    if not await self._check_order_interval(exchange_name):
                        await asyncio.sleep(0.1)
                        continue
                        
                    # 获取当前价格
                    current_price = await self._get_valid_price(
                        exchange_name,
                        signal['symbol'],
                        signal['side']
                    )
                    if not current_price:
                        continue
                        
                    # 创建订单
                    order_params = {
                        'symbol': signal['symbol'],
                        'type': 'limit',
                        'side': signal['side'],
                        'amount': min(chunk_size, remaining_size),
                        'price': current_price
                    }
                    
                    order = await self.order_manager.place_order(exchange_name, order_params)
                    if order:
                        self.executing_trades[trade_id]['orders'][exchange_name] = order
                        self.last_order_time[exchange_name] = datetime.utcnow()
                        remaining_size -= Decimal(str(order['executed_amount']))
                        
                        if remaining_size <= 0:
                            break
                            
                await asyncio.sleep(0.1)
                
            # 检查执行结果
            total_executed = sum(
                Decimal(str(order['executed_amount']))
                for order in self.executing_trades[trade_id]['orders'].values()
            )
            
            if total_executed >= total_size * Decimal('0.95'):  # 允许5%的误差
                self.executing_trades[trade_id]['status'] = 'completed'
                return True
                
            # 如果执行不完整，取消所有订单
            for order_id in self.executing_trades[trade_id]['orders'].values():
                await self.order_manager.cancel_order(order_id)
                
            del self.executing_trades[trade_id]
            return False
            
        except Exception as e:
            self.logger.error(f"分批执行订单失败: {e}")
            return False
            
    async def _check_order_interval(self, exchange_name: str) -> bool:
        """检查下单间隔"""
        if exchange_name in self.last_order_time:
            elapsed = (datetime.utcnow() - self.last_order_time[exchange_name]).total_seconds()
            return elapsed >= self.min_order_interval
        return True
    async def _get_valid_price(self, exchange_name: str, symbol: str, 
                             side: str) -> Optional[Decimal]:
        """获取有效价格"""
        try:
            exchange = self.exchange_manager.exchanges[exchange_name]
            price_info = await exchange.get_best_price(symbol)
            if not price_info:
                return None
                
            # 根据方向选择买卖价
            base_price = price_info['ask'] if side == 'buy' else price_info['bid']
            
            # 检查深度
            orderbook = await exchange.fetch_order_book(symbol)
            if not orderbook:
                return None
                
            # 计算滑点
            spread = (price_info['ask'] - price_info['bid']) / price_info['bid']
            if spread > self.max_slippage:
                self.logger.warning(f"价差过大: {spread}")
                return None
                
            # 返回调整后的价格
            if side == 'buy':
                return base_price * (1 + self.max_slippage / 2)
            else:
                return base_price * (1 - self.max_slippage / 2)
                
        except Exception as e:
            self.logger.error(f"获取有效价格失败: {e}")
            return None
            
    async def _calculate_realized_pnl(self, position: Dict, 
                                    close_orders: Dict) -> Optional[Decimal]:
        """计算已实现盈亏"""
        try:
            total_pnl = Decimal('0')
            
            for exchange_name, order in position['info']['orders'].items():
                if exchange_name not in close_orders:
                    continue
                    
                close_order = close_orders[exchange_name]
                
                entry_price = Decimal(str(order['price']))
                exit_price = Decimal(str(close_order['executed_price']))
                amount = Decimal(str(order['amount']))
                
                if order['side'] == 'buy':
                    pnl = (exit_price - entry_price) * amount
                else:
                    pnl = (entry_price - exit_price) * amount
                    
                total_pnl += pnl
                
            return total_pnl
            
        except Exception as e:
            self.logger.error(f"计算已实现盈亏失败: {e}")
            return None
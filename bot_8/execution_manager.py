import threading
import queue
from typing import Dict, List, Optional
from datetime import datetime, timezone
import time
from decimal import Decimal
from dataclasses import dataclass
import asyncio

from logger import Logger
from config import Config

@dataclass
class OrderRequest:
    symbol: str
    side: str
    order_type: str
    amount: float
    price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    trailing_stop: Optional[Dict]
    strategy: str
    timestamp: datetime

class ExecutionManager:
    def __init__(self, exchange_id: str):
        self.logger = Logger("ExecutionManager")
        self.exchange_id = exchange_id
        self.exchange = self._initialize_exchange()
        
        # 订单队列和执行状态
        self.order_queue = queue.PriorityQueue()
        self.active_orders = {}
        self.pending_orders = {}
        
        # 执行统计
        self.execution_stats = {
            'total_orders': 0,
            'successful_orders': 0,
            'failed_orders': 0,
            'avg_execution_time': 0,
            'avg_slippage': 0,
            'execution_times': []
        }
        
        # 限流控制
        self.rate_limiter = self._initialize_rate_limiter()
        
        # 启动执行线程
        self._start_execution_threads()
        
    def submit_order(self, order_request: OrderRequest) -> str:
        """提交订单请求"""
        try:
            # 验证订单参数
            if not self._validate_order_request(order_request):
                raise ValueError("Invalid order request")
                
            # 生成订单ID
            order_id = self._generate_order_id(order_request)
            
            # 获取优先级
            priority = self._calculate_order_priority(order_request)
            
            # 添加到订单队列
            self.order_queue.put((priority, order_id, order_request))
            self.pending_orders[order_id] = order_request
            
            self.logger.info(f"Order submitted: {order_id} - {order_request}")
            
            return order_id
            
        except Exception as e:
            self.logger.error(f"Error submitting order: {str(e)}")
            raise
            
    async def execute_order(self, order_id: str, order_request: OrderRequest):
        """执行订单"""
        try:
            start_time = time.time()
            
            # 检查市场条件
            if not await self._check_market_conditions(order_request):
                raise ValueError("Market conditions not suitable for execution")
                
            # 获取最新价格
            current_price = await self._get_current_price(order_request.symbol)
            
            # 检查滑点
            if not self._check_slippage(order_request, current_price):
                raise ValueError("Price slippage exceeds threshold")
                
            # 执行主订单
            main_order = await self._execute_main_order(order_request)
            
            # 设置止损止盈
            if main_order['status'] == 'filled':
                await self._setup_risk_orders(main_order, order_request)
                
            # 更新统计
            execution_time = time.time() - start_time
            self._update_execution_stats(execution_time, main_order)
            
            return main_order
            
        except Exception as e:
            self.logger.error(f"Error executing order {order_id}: {str(e)}")
            self._handle_execution_failure(order_id, str(e))
            raise
            
    async def _execute_main_order(self, order_request: OrderRequest) -> Dict:
        """执行主订单"""
        try:
            # 规范化订单参数
            amount = self._normalize_amount(order_request.symbol, order_request.amount)
            
            order_params = {
                'symbol': order_request.symbol,
                'type': order_request.order_type,
                'side': order_request.side,
                'amount': amount
            }
            
            if order_request.price:
                order_params['price'] = self._normalize_price(
                    order_request.symbol,
                    order_request.price
                )
                
            # 执行订单
            order = await self.exchange.create_order(**order_params)
            
            # 等待订单完成
            filled_order = await self._wait_for_order_completion(order['id'])
            
            return filled_order
            
        except Exception as e:
            self.logger.error(f"Error executing main order: {str(e)}")
            raise
            
    async def _setup_risk_orders(self, main_order: Dict, order_request: OrderRequest):
        """设置风险管理订单"""
        try:
            tasks = []
            
            # 设置止损单
            if order_request.stop_loss:
                tasks.append(self._create_stop_loss_order(main_order, order_request))
                
            # 设置止盈单
            if order_request.take_profit:
                tasks.append(self._create_take_profit_order(main_order, order_request))
                
            # 设置追踪止损
            if order_request.trailing_stop:
                tasks.append(self._create_trailing_stop_order(main_order, order_request))
                
            # 并行执行所有风险订单
            await asyncio.gather(*tasks)
            
        except Exception as e:
            self.logger.error(f"Error setting up risk orders: {str(e)}")
            
    async def _create_stop_loss_order(self, main_order: Dict, order_request: OrderRequest):
        """创建止损订单"""
        try:
            stop_params = {
                'symbol': order_request.symbol,
                'type': 'stop',
                'side': 'sell' if order_request.side == 'buy' else 'buy',
                'amount': main_order['filled'],
                'price': order_request.stop_loss,
                'params': {
                    'stopPrice': order_request.stop_loss,
                    'reduceOnly': True
                }
            }
            
            stop_order = await self.exchange.create_order(**stop_params)
            return stop_order
            
        except Exception as e:
            self.logger.error(f"Error creating stop loss order: {str(e)}")
            
    async def _create_trailing_stop_order(self, main_order: Dict, order_request: OrderRequest):
        """创建追踪止损订单"""
        try:
            trail_params = {
                'symbol': order_request.symbol,
                'type': 'trailing_stop',
                'side': 'sell' if order_request.side == 'buy' else 'buy',
                'amount': main_order['filled'],
                'params': {
                    'callbackRate': order_request.trailing_stop['distance'],
                    'activationPrice': order_request.trailing_stop['activation'],
                    'reduceOnly': True
                }
            }
            
            trail_order = await self.exchange.create_order(**trail_params)
            return trail_order
            
        except Exception as e:
            self.logger.error(f"Error creating trailing stop order: {str(e)}")
            
    def _update_execution_stats(self, execution_time: float, order: Dict):
        """更新执行统计"""
        try:
            self.execution_stats['total_orders'] += 1
            
            if order['status'] == 'filled':
                self.execution_stats['successful_orders'] += 1
            else:
                self.execution_stats['failed_orders'] += 1
                
            # 更新平均执行时间
            self.execution_stats['execution_times'].append(execution_time)
            self.execution_stats['avg_execution_time'] = (
                sum(self.execution_stats['execution_times']) /
                len(self.execution_stats['execution_times'])
            )
            
            # 计算滑点
            if 'price' in order and order['average']:
                slippage = abs(order['average'] - order['price']) / order['price']
                self.execution_stats['avg_slippage'] = (
                    self.execution_stats['avg_slippage'] * 0.95 +
                    slippage * 0.05
                )
                
        except Exception as e:
            self.logger.error(f"Error updating execution stats: {str(e)}")
            
    def _calculate_order_priority(self, order_request: OrderRequest) -> int:
        """计算订单优先级"""
        try:
            base_priority = 100
            
            # 市场订单优先级更高
            if order_request.order_type == 'market':
                base_priority -= 20
                
            # 止损单最高优先级
            if order_request.stop_loss:
                base_priority -= 40
                
            # 基于订单大小调整优先级
            order_value = order_request.amount * order_request.price
            if order_value > Config.EXECUTION_PARAMS['large_order_threshold']:
                base_priority += 10
                
            return base_priority
            
        except Exception as e:
            self.logger.error(f"Error calculating order priority: {str(e)}")
            return 100
            
    def get_execution_stats(self) -> Dict:
        """获取执行统计信息"""
        return self.execution_stats

    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]
                return True
                
            if order_id in self.active_orders:
                self.exchange.cancel_order(order_id)
                del self.active_orders[order_id]
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"Error canceling order {order_id}: {str(e)}")
            return False
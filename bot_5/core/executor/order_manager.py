from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime
import asyncio
from utils.logger import setup_logger
import uuid

class OrderManager:
    def __init__(self, exchange_manager):
        self.exchange_manager = exchange_manager
        self.logger = setup_logger("order_manager")
        
        # 订单存储
        self.active_orders = {}  # 活跃订单
        self.order_history = {}  # 订单历史
        self.order_updates = {}  # 订单更新队列
        
        # 订单配置
        self.max_retries = 3     # 最大重试次数
        self.retry_delay = 1     # 重试延迟(秒)
        self.order_timeout = 30  # 订单超时时间(秒)
        
        # 初始化时间戳
        self.start_time = datetime.utcnow()
        
    async def place_order(self, exchange_name: str, order_params: Dict) -> Optional[Dict]:
        """下单"""
        try:
            # 生成订单ID
            order_id = str(uuid.uuid4())
            
            # 验证订单参数
            if not self._validate_order_params(order_params):
                raise ValueError("无效的订单参数")
                
            # 添加到活跃订单
            self.active_orders[order_id] = {
                'exchange': exchange_name,
                'params': order_params,
                'status': 'pending',
                'created_at': datetime.utcnow(),
                'retries': 0,
                'fills': []
            }
            
            # 执行下单
            order = await self._execute_order(order_id)
            if order:
                self.logger.info(f"下单成功: {order_id}")
                return order
                
            return None
            
        except Exception as e:
            self.logger.error(f"下单失败: {e}")
            return None
            
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            if order_id not in self.active_orders:
                self.logger.warning(f"订单不存在: {order_id}")
                return False
                
            order = self.active_orders[order_id]
            exchange = self.exchange_manager.exchanges[order['exchange']]
            
            # 执行取消
            success = await exchange.cancel_order(
                order['exchange_order_id'],
                order['params']['symbol']
            )
            
            if success:
                order['status'] = 'canceled'
                self._move_to_history(order_id)
                self.logger.info(f"订单取消成功: {order_id}")
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"取消订单失败: {e}")
            return False
            
    async def get_order_status(self, order_id: str) -> Optional[Dict]:
        """获取订单状态"""
        try:
            if order_id in self.active_orders:
                return self.active_orders[order_id]
            elif order_id in self.order_history:
                return self.order_history[order_id]
                
            return None
            
        except Exception as e:
            self.logger.error(f"获取订单状态失败: {e}")
            return None
            
    async def _execute_order(self, order_id: str) -> Optional[Dict]:
        """执行订单"""
        try:
            order = self.active_orders[order_id]
            exchange = self.exchange_manager.exchanges[order['exchange']]
            
            # 执行下单
            result = await exchange.create_order(
                symbol=order['params']['symbol'],
                order_type=order['params']['type'],
                side=order['params']['side'],
                amount=float(order['params']['amount']),
                price=float(order['params']['price']) if 'price' in order['params'] else None
            )
            
            if result:
                order['exchange_order_id'] = result['id']
                order['status'] = result['status']
                order['executed_price'] = Decimal(str(result.get('price', '0')))
                order['executed_amount'] = Decimal(str(result.get('filled', '0')))
                order['remaining'] = Decimal(str(result.get('remaining', '0')))
                order['last_update'] = datetime.utcnow()
                
                # 如果订单已完成，移至历史记录
                if result['status'] in ['closed', 'canceled', 'expired']:
                    self._move_to_history(order_id)
                    
                return order
                
            return None
            
        except Exception as e:
            self.logger.error(f"执行订单失败: {e}")
            order['retries'] += 1
            
            if order['retries'] < self.max_retries:
                await asyncio.sleep(self.retry_delay)
                return await self._execute_order(order_id)
                
            order['status'] = 'failed'
            self._move_to_history(order_id)
            return None
            
    def _validate_order_params(self, params: Dict) -> bool:
        """验证订单参数"""
        required_fields = ['symbol', 'type', 'side', 'amount']
        if not all(field in params for field in required_fields):
            return False
            
        if params['type'] == 'limit' and 'price' not in params:
            return False
            
        if params['side'] not in ['buy', 'sell']:
            return False
            
        return True
        
    def _move_to_history(self, order_id: str):
        """移动订单到历史记录"""
        if order_id in self.active_orders:
            self.order_history[order_id] = self.active_orders.pop(order_id)
            self.order_history[order_id]['closed_at'] = datetime.utcnow()
            
    async def update_order_status(self, order_id: str):
        """更新订单状态"""
        try:
            if order_id not in self.active_orders:
                return
                
            order = self.active_orders[order_id]
            exchange = self.exchange_manager.exchanges[order['exchange']]
            
            result = await exchange.fetch_order(
                order['exchange_order_id'],
                order['params']['symbol']
            )
            
            if result:
                order['status'] = result['status']
                order['executed_price'] = Decimal(str(result.get('price', '0')))
                order['executed_amount'] = Decimal(str(result.get('filled', '0')))
                order['remaining'] = Decimal(str(result.get('remaining', '0')))
                order['last_update'] = datetime.utcnow()
                
                # 更新成交记录
                if 'trades' in result and result['trades']:
                    for trade in result['trades']:
                        if trade['id'] not in [t['id'] for t in order['fills']]:
                            order['fills'].append({
                                'id': trade['id'],
                                'price': Decimal(str(trade['price'])),
                                'amount': Decimal(str(trade['amount'])),
                                'timestamp': datetime.fromtimestamp(trade['timestamp']/1000)
                            })
                            
                # 检查是否完成
                if result['status'] in ['closed', 'canceled', 'expired']:
                    self._move_to_history(order_id)
                    
        except Exception as e:
            self.logger.error(f"更新订单状态失败: {e}")
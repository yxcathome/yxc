import time
import json
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from collections import deque
import numpy as np
from config import Config
from logger import Logger

class OrderManager:
    def __init__(self, exchange_id: str):
        self.logger = Logger("OrderManager")
        self.exchange_id = exchange_id
        self.exchange = self._initialize_exchange()
        
        # 订单管理
        self.active_orders = {}
        self.order_history = deque(maxlen=1000)  # 保留最近1000个订单
        self.pending_orders = {}
        self.order_updates = {}
        
        # 性能统计
        self.execution_stats = {
            'slippage': [],
            'execution_time': [],
            'fill_rates': [],
            'rejection_reasons': {}
        }
        
        # 限流控制
        self.rate_limiter = self._initialize_rate_limiter()
        
        # 启动订单监控线程
        self._start_order_monitor()
        
    def _initialize_exchange(self):
        """初始化交易所接口"""
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            exchange = exchange_class({
                'apiKey': Config.EXCHANGES[self.exchange_id]['apiKey'],
                'secret': Config.EXCHANGES[self.exchange_id]['secret'],
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'recvWindow': 60000
                }
            })
            exchange.load_markets()
            return exchange
        except Exception as e:
            self.logger.error(f"Failed to initialize exchange: {str(e)}")
            raise

    def place_order(self, symbol: str, 
                   order_type: str,
                   side: str, 
                   amount: float,
                   price: Optional[float] = None,
                   params: Dict = None) -> Dict:
        """
        下单主函数
        """
        try:
            # 规范化订单参数
            amount = self._normalize_amount(symbol, amount)
            if price:
                price = self._normalize_price(symbol, price)
            
            # 检查限流
            if not self.rate_limiter.check_rate_limit('place_order'):
                raise Exception("Rate limit exceeded")
            
            # 记录下单时间
            order_start_time = time.time()
            
            # 构建订单参数
            order_params = self._build_order_params(symbol, side, params)
            
            # 执行下单
            if order_type == 'market':
                order = self.exchange.create_market_order(
                    symbol, side, amount, None, order_params
                )
            else:
                order = self.exchange.create_limit_order(
                    symbol, side, amount, price, order_params
                )
            
            # 记录订单
            self._record_order(order, order_start_time)
            
            # 启动订单监控
            self._monitor_order(order['id'], symbol)
            
            return order
            
        except Exception as e:
            self.logger.error(f"Error placing order: {str(e)}")
            self._record_order_failure(symbol, side, amount, str(e))
            raise

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        取消订单
        """
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            self._update_order_status(order_id, 'canceled')
            self.logger.info(f"Order {order_id} canceled successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {str(e)}")
            return False

    def _normalize_amount(self, symbol: str, amount: float) -> float:
        """
        规范化交易数量
        """
        try:
            market = self.exchange.market(symbol)
            precision = market['precision']['amount']
            
            # 转换为Decimal进行精确计算
            amount_d = Decimal(str(amount))
            normalized = amount_d.quantize(
                Decimal('1e-' + str(precision)),
                rounding=ROUND_DOWN
            )
            
            # 确保大于最小交易量
            min_amount = Decimal(str(market['limits']['amount']['min']))
            normalized = max(normalized, min_amount)
            
            return float(normalized)
            
        except Exception as e:
            self.logger.error(f"Error normalizing amount: {str(e)}")
            raise

    def _normalize_price(self, symbol: str, price: float) -> float:
        """
        规范化价格
        """
        try:
            market = self.exchange.market(symbol)
            precision = market['precision']['price']
            
            price_d = Decimal(str(price))
            normalized = price_d.quantize(
                Decimal('1e-' + str(precision)),
                rounding=ROUND_DOWN
            )
            
            return float(normalized)
            
        except Exception as e:
            self.logger.error(f"Error normalizing price: {str(e)}")
            raise

    def _build_order_params(self, symbol: str, 
                          side: str, 
                          custom_params: Dict = None) -> Dict:
        """
        构建订单参数
        """
        params = {
            'timeInForce': 'GTC',  # Good Till Cancel
            'postOnly': False,     # 允许成为Taker
            'reduceOnly': False    # 不仅用于减仓
        }
        
        # 添加自定义参数
        if custom_params:
            params.update(custom_params)
            
        return params

    def _record_order(self, order: Dict, start_time: float):
        """
        记录订单信息
        """
        order_info = {
            'order': order,
            'timestamp': datetime.utcnow().isoformat(),
            'execution_time': time.time() - start_time,
            'status_updates': []
        }
        
        self.order_history.append(order_info)
        self.active_orders[order['id']] = order_info
        
        # 更新执行统计
        self.execution_stats['execution_time'].append(order_info['execution_time'])

    def _monitor_order(self, order_id: str, symbol: str):
        """
        监控订单状态
        """
        def monitor():
            try:
                max_retries = 10
                retry_count = 0
                
                while retry_count < max_retries:
                    order = self.exchange.fetch_order(order_id, symbol)
                    
                    if order['status'] in ['closed', 'filled']:
                        self._process_filled_order(order)
                        break
                    elif order['status'] in ['canceled', 'expired', 'rejected']:
                        self._process_failed_order(order)
                        break
                        
                    time.sleep(Config.ORDER_QUERY_INTERVAL)
                    retry_count += 1
                    
            except Exception as e:
                self.logger.error(f"Error monitoring order {order_id}: {str(e)}")
                
        threading.Thread(target=monitor, daemon=True).start()

    def _process_filled_order(self, order: Dict):
        """
        处理已成交订单
        """
        try:
            # 计算滑点
            if order['type'] == 'limit':
                slippage = (order['average'] - order['price']) / order['price']
                self.execution_stats['slippage'].append(slippage)
            
            # 计算成交率
            fill_rate = order['filled'] / order['amount']
            self.execution_stats['fill_rates'].append(fill_rate)
            
            # 更新订单状态
            self._update_order_status(order['id'], 'filled')
            
            # 记录成交详情
            self.logger.info(
                f"Order {order['id']} filled: "
                f"Price={order['average']}, "
                f"Amount={order['filled']}, "
                f"Slippage={slippage if 'slippage' in locals() else 'N/A'}"
            )
            
        except Exception as e:
            self.logger.error(f"Error processing filled order: {str(e)}")

    def _process_failed_order(self, order: Dict):
        """
        处理失败订单
        """
        try:
            reason = order.get('info', {}).get('reason', 'unknown')
            
            # 统计失败原因
            if reason not in self.execution_stats['rejection_reasons']:
                self.execution_stats['rejection_reasons'][reason] = 0
            self.execution_stats['rejection_reasons'][reason] += 1
            
            self.logger.warning(
                f"Order {order['id']} failed: "
                f"Status={order['status']}, "
                f"Reason={reason}"
            )
            
        except Exception as e:
            self.logger.error(f"Error processing failed order: {str(e)}")

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """
        获取订单状态
        """
        return self.active_orders.get(order_id)

    def get_execution_stats(self) -> Dict:
        """
        获取执行统计
        """
        return {
            'avg_slippage': np.mean(self.execution_stats['slippage']) if self.execution_stats['slippage'] else 0,
            'avg_execution_time': np.mean(self.execution_stats['execution_time']),
            'avg_fill_rate': np.mean(self.execution_stats['fill_rates']),
            'rejection_reasons': dict(self.execution_stats['rejection_reasons'])
        }

    def _initialize_rate_limiter(self):
        """
        初始化限流控制器
        """
        return {
            'place_order': {
                'max_requests': 10,
                'time_window': 1,  # 秒
                'requests': deque(),
            }
        }

    def check_rate_limit(self, action: str) -> bool:
        """
        检查是否超过限流
        """
        limiter = self.rate_limiter.get(action)
        if not limiter:
            return True
            
        current_time = time.time()
        
        # 清理过期请求
        while (limiter['requests'] and 
               current_time - limiter['requests'][0] > limiter['time_window']):
            limiter['requests'].popleft()
            
        # 检查是否可以发送新请求
        if len(limiter['requests']) < limiter['max_requests']:
            limiter['requests'].append(current_time)
            return True
            
        return False

    def _start_order_monitor(self):
        """
        启动订单监控线程
        """
        def monitor_orders():
            while True:
                try:
                    self._check_active_orders()
                    time.sleep(Config.ORDER_QUERY_INTERVAL)
                except Exception as e:
                    self.logger.error(f"Error in order monitor: {str(e)}")
                    
        threading.Thread(target=monitor_orders, daemon=True).start()

    def _check_active_orders(self):
        """
        检查活动订单状态
        """
        for order_id in list(self.active_orders.keys()):
            order_info = self.active_orders[order_id]
            
            try:
                order = self.exchange.fetch_order(
                    order_id,
                    order_info['order']['symbol']
                )
                
                if order['status'] != order_info['order']['status']:
                    self._update_order_status(order_id, order['status'])
                    
            except Exception as e:
                self.logger.error(f"Error checking order {order_id}: {str(e)}")

from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from decimal import Decimal
import asyncio
from datetime import datetime
import logging
from utils.logger import setup_logger

class BaseStrategy(ABC):
    def __init__(self, name: str, exchange_manager, risk_manager):
        self.name = name
        self.exchange_manager = exchange_manager
        self.risk_manager = risk_manager
        self.logger = setup_logger(f"strategy.{name}")
        self.active = False
        self.config = {}
        self.positions = {}
        self.signals = {}
        self.performance_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': Decimal('0'),
            'max_drawdown': Decimal('0'),
            'sharpe_ratio': Decimal('0')
        }

    @abstractmethod
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        pass

    @abstractmethod
    async def calculate_position_size(self, symbol: str, signal: Dict) -> Optional[Decimal]:
        """计算仓位大小"""
        pass

    async def execute_signal(self, symbol: str, signal: Dict) -> bool:
        """执行交易信号"""
        try:
            # 1. 风控检查
            if not await self.risk_manager.can_open_position(self.name, symbol, signal):
                return False

            # 2. 计算仓位大小
            position_size = await self.calculate_position_size(symbol, signal)
            if not position_size:
                return False

            # 3. 生成订单参数
            order_params = await self._prepare_orders(symbol, signal, position_size)
            if not order_params:
                return False

            # 4. 同步下单
            orders = await self._execute_orders(symbol, order_params)
            if not orders:
                return False

            # 5. 更新仓位信息
            await self._update_position(symbol, orders, signal)

            return True

        except Exception as e:
            self.logger.error(f"执行信号失败: {e}")
            return False

    async def _prepare_orders(self, symbol: str, signal: Dict, 
                            position_size: Decimal) -> Optional[Dict]:
        """准备订单参数"""
        try:
            side = signal['side']
            order_type = signal.get('order_type', 'market')

            # 获取当前价格
            prices = {}
            for exchange in self.exchange_manager.exchanges.values():
                price_info = await exchange.get_best_price(symbol)
                if not price_info:
                    continue
                prices[exchange.name] = price_info['ask'] if side == 'buy' else price_info['bid']

            if len(prices) < len(self.exchange_manager.exchanges):
                self.logger.error("无法获取完整的价格信息")
                return None

            # 检查价格偏差
            if not self._validate_prices(prices):
                self.logger.error("交易所间价格偏差过大")
                return None

            # 生成订单参数
            orders = {}
            for exchange_name, price in prices.items():
                orders[exchange_name] = {
                    'symbol': symbol,
                    'side': side,
                    'type': order_type,
                    'amount': position_size,
                    'price': price if order_type == 'limit' else None
                }

            return orders

        except Exception as e:
            self.logger.error(f"准备订单参数失败: {e}")
            return None

    async def _execute_orders(self, symbol: str, order_params: Dict) -> Optional[Dict]:
        """执行订单"""
        orders = {}
        try:
            # 创建订单任务
            tasks = []
            for exchange_name, params in order_params.items():
                exchange = self.exchange_manager.exchanges[exchange_name]
                task = asyncio.create_task(
                    exchange.create_order(
                        symbol=params['symbol'],
                        order_type=params['type'],
                        side=params['side'],
                        amount=params['amount'],
                        price=params['price']
                    )
                )
                tasks.append((exchange_name, task))

            # 等待所有订单完成
            for exchange_name, task in tasks:
                try:
                    order = await asyncio.wait_for(task, timeout=5.0)
                    orders[exchange_name] = order
                except asyncio.TimeoutError:
                    self.logger.error(f"{exchange_name} 下单超时")
                    await self._cancel_orders(orders)
                    return None
                except Exception as e:
                    self.logger.error(f"{exchange_name} 下单失败: {e}")
                    await self._cancel_orders(orders)
                    return None

            return orders

        except Exception as e:
            self.logger.error(f"执行订单失败: {e}")
            await self._cancel_orders(orders)
            return None

    async def _cancel_orders(self, orders: Dict):
        """取消订单"""
        for exchange_name, order in orders.items():
            try:
                exchange = self.exchange_manager.exchanges[exchange_name]
                await exchange.cancel_order(order['id'], order['symbol'])
            except Exception as e:
                self.logger.error(f"取消订单失败 {exchange_name}: {e}")

    async def _update_position(self, symbol: str, orders: Dict, signal: Dict):
        """更新仓位信息"""
        try:
            position_info = {
                'symbol': symbol,
                'side': signal['side'],
                'entry_time': datetime.utcnow(),
                'orders': orders,
                'signal': signal
            }

            self.positions[symbol] = position_info
            await self.risk_manager.register_position(self.name, symbol, position_info)

        except Exception as e:
            self.logger.error(f"更新仓位信息失败: {e}")

    def _validate_prices(self, prices: Dict[str, Decimal]) -> bool:
        """验证价格是否合理"""
        if not prices:
            return False

        price_list = list(prices.values())
        avg_price = sum(price_list) / len(price_list)
        
        # 检查价格偏差是否在允许范围内 (0.1%)
        for price in price_list:
            deviation = abs(price - avg_price) / avg_price
            if deviation > Decimal('0.001'):
                return False
                
        return True

    async def update_metrics(self, trade_result: Dict):
        """更新策略性能指标"""
        try:
            self.performance_metrics['total_trades'] += 1
            pnl = trade_result['realized_pnl']
            
            if pnl > 0:
                self.performance_metrics['winning_trades'] += 1
            else:
                self.performance_metrics['losing_trades'] += 1
                
            self.performance_metrics['total_profit'] += pnl
            
            # 更新最大回撤
            if pnl < 0:
                current_drawdown = abs(pnl)
                self.performance_metrics['max_drawdown'] = max(
                    self.performance_metrics['max_drawdown'],
                    current_drawdown
                )
                
            # 计算夏普比率
            await self._calculate_sharpe_ratio()
            
        except Exception as e:
            self.logger.error(f"更新性能指标失败: {e}")

    async def _calculate_sharpe_ratio(self):
        """计算夏普比率"""
        try:
            if self.performance_metrics['total_trades'] < 2:
                return
                
            # 获取过去的交易记录
            trades = await self._get_historical_trades()
            if not trades:
                return
                
            # 计算收益率序列
            returns = [trade['return_rate'] for trade in trades]
            avg_return = sum(returns) / len(returns)
            
            # 计算标准差
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = Decimal(str(variance)).sqrt()
            
            # 计算夏普比率 (假设无风险利率为3%)
            risk_free_rate = Decimal('0.03')
            if std_dev > 0:
                self.performance_metrics['sharpe_ratio'] = \
                    (avg_return - risk_free_rate) / std_dev
                    
        except Exception as e:
            self.logger.error(f"计算夏普比率失败: {e}")
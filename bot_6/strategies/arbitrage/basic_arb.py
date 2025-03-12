from decimal import Decimal
from typing import Dict, Optional
import asyncio
from datetime import datetime
from strategies.base_strategy import BaseStrategy

class BasicArbitrageStrategy(BaseStrategy):
    def __init__(self, exchange_manager, risk_manager):
        super().__init__("basic_arbitrage", exchange_manager, risk_manager)
        self.min_spread = Decimal('0.001')  # 最小价差 0.1%
        self.max_position_hold_time = 300   # 最大持仓时间 5分钟
        self.position_check_interval = 1     # 持仓检查间隔 1秒
        
    async def start(self):
        """启动策略"""
        self.active = True
        asyncio.create_task(self._position_monitor())
        self.logger.info("基础套利策略启动")
        
    async def stop(self):
        """停止策略"""
        self.active = False
        self.logger.info("基础套利策略停止")
        
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 获取两个交易所的订单簿
            orderbooks = {}
            for exchange in self.exchange_manager.exchanges.values():
                price_info = await exchange.get_best_price(symbol)
                if not price_info:
                    return None
                orderbooks[exchange.name] = price_info
                
            # 计算套利机会
            signal = await self._calculate_arbitrage(symbol, orderbooks)
            if signal:
                self.logger.info(f"发现套利机会: {signal}")
            return signal
            
        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            return None
            
    async def calculate_position_size(self, symbol: str, signal: Dict) -> Optional[Decimal]:
        """计算仓位大小"""
        try:
            # 获取当前可用资金
            available_balance = await self.risk_manager.get_available_balance()
            if not available_balance:
                return None
                
            # 计算基于价差的仓位大小
            spread = signal['spread']
            base_size = available_balance * Decimal('0.1')  # 使用10%可用资金
            
            # 根据价差调整仓位
            if spread < Decimal('0.002'):  # 0.2%价差
                position_size = base_size * Decimal('0.5')
            elif spread < Decimal('0.003'):  # 0.3%价差
                position_size = base_size * Decimal('0.8')
            else:
                position_size = base_size
                
            # 确保符合最小交易金额
            min_notional = Decimal('5')  # 最小5U
            if position_size < min_notional:
                return None
                
            return position_size
            
        except Exception as e:
            self.logger.error(f"计算仓位大小失败: {e}")
            return None
            
    async def _calculate_arbitrage(self, symbol: str, orderbooks: Dict) -> Optional[Dict]:
        """计算套利机会"""
        try:
            best_buy = None
            best_sell = None
            buy_exchange = None
            sell_exchange = None
            
            # 找出最佳买卖价格
            for exchange_name, prices in orderbooks.items():
                if not best_buy or prices['bid'] > best_buy:
                    best_buy = prices['bid']
                    buy_exchange = exchange_name
                if not best_sell or prices['ask'] < best_sell:
                    best_sell = prices['ask']
                    sell_exchange = exchange_name
                    
            # 计算价差
            if best_buy and best_sell and buy_exchange != sell_exchange:
                spread = (best_buy - best_sell) / best_sell
                
                # 检查是否满足最小价差要求
                if spread > self.min_spread:
                    return {
                        'symbol': symbol,
                        'type': 'arbitrage',
                        'spread': spread,
                        'buy': {
                            'exchange': sell_exchange,
                            'price': best_sell
                        },
                        'sell': {
                            'exchange': buy_exchange,
                            'price': best_buy
                        },
                        'timestamp': datetime.utcnow()
                    }
                    
            return None
            
        except Exception as e:
            self.logger.error(f"计算套利机会失败: {e}")
            return None
            
    async def _position_monitor(self):
        """监控持仓状态"""
        while self.active:
            try:
                for symbol, position in list(self.positions.items()):
                    # 检查持仓时间
                    hold_time = (datetime.utcnow() - position['entry_time']).total_seconds()
                    if hold_time > self.max_position_hold_time:
                        await self._close_position(symbol, position, 'timeout')
                        continue
                        
                    # 检查盈利目标
                    pnl = await self._calculate_unrealized_pnl(symbol, position)
                    if pnl is not None:
                        if pnl > 0:  # 有盈利就平仓
                            await self._close_position(symbol, position, 'take_profit')
                            
                await asyncio.sleep(self.position_check_interval)
                
            except Exception as e:
                self.logger.error(f"持仓监控异常: {e}")
                await asyncio.sleep(1)
                
    async def _calculate_unrealized_pnl(self, symbol: str, position: Dict) -> Optional[Decimal]:
        """计算未实现盈亏"""
        try:
            current_prices = {}
            for exchange in self.exchange_manager.exchanges.values():
                price_info = await exchange.get_best_price(symbol)
                if not price_info:
                    return None
                current_prices[exchange.name] = price_info
                
            buy_price = position['orders'][position['signal']['buy']['exchange']]['price']
            sell_price = position['orders'][position['signal']['sell']['exchange']]['price']
            
            current_buy = current_prices[position['signal']['buy']['exchange']]['bid']
            current_sell = current_prices[position['signal']['sell']['exchange']]['ask']
            
            position_size = Decimal(str(position['orders'][position['signal']['buy']['exchange']]['amount']))
            
            # 计算盈亏
            entry_spread = sell_price - buy_price
            current_spread = current_sell - current_buy
            
            pnl = (entry_spread - current_spread) * position_size
            return pnl
            
        except Exception as e:
            self.logger.error(f"计算未实现盈亏失败: {e}")
            return None
            
    async def _close_position(self, symbol: str, position: Dict, reason: str):
        """平仓"""
        try:
            close_orders = {}
            for exchange_name, order in position['orders'].items():
                side = 'sell' if order['side'] == 'buy' else 'buy'
                try:
                    close_order = await self.exchange_manager.exchanges[exchange_name].create_order(
                        symbol=symbol,
                        order_type='market',
                        side=side,
                        amount=order['amount']
                    )
                    close_orders[exchange_name] = close_order
                except Exception as e:
                    self.logger.error(f"平仓失败 {exchange_name}: {e}")
                    return
                    
            # 更新仓位状态
            del self.positions[symbol]
            
            # 计算并记录交易结果
            pnl = await self._calculate_realized_pnl(position, close_orders)
            if pnl is not None:
                await self.update_metrics({
                    'symbol': symbol,
                    'realized_pnl': pnl,
                    'reason': reason,
                    'hold_time': (datetime.utcnow() - position['entry_time']).total_seconds()
                })
                
        except Exception as e:
            self.logger.error(f"平仓操作失败: {e}")
            
    async def _calculate_realized_pnl(self, position: Dict, close_orders: Dict) -> Optional[Decimal]:
        """计算实现盈亏"""
        try:
            position_size = Decimal(str(position['orders'][position['signal']['buy']['exchange']]['amount']))
            
            # 计算开仓价差
            entry_buy = Decimal(str(position['orders'][position['signal']['buy']['exchange']]['price']))
            entry_sell = Decimal(str(position['orders'][position['signal']['sell']['exchange']]['price']))
            entry_spread = entry_sell - entry_buy
            
            # 计算平仓价差
            close_buy = Decimal(str(close_orders[position['signal']['sell']['exchange']]['price']))
            close_sell = Decimal(str(close_orders[position['signal']['buy']['exchange']]['price']))
            close_spread = close_sell - close_buy
            
            # 计算总盈亏
            pnl = (entry_spread - close_spread) * position_size
            return pnl
            
        except Exception as e:
            self.logger.error(f"计算实现盈亏失败: {e}")
            return None
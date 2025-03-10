from decimal import Decimal
from typing import Dict, Optional
import asyncio
from datetime import datetime
from strategies.base_strategy import BaseStrategy
import numpy as np

class FlashArbitrageStrategy(BaseStrategy):
    def __init__(self, exchange_manager, risk_manager):
        super().__init__("flash_arbitrage", exchange_manager, risk_manager)
        self.price_windows = {}  # 价格历史窗口
        self.window_size = 100   # 价格窗口大小
        self.std_threshold = Decimal('2.5')  # 标准差阈值
        self.min_spike_pct = Decimal('0.003')  # 最小价格突变比例 0.3%
        self.max_hold_time = 30  # 最大持仓时间（秒）
        
    async def start(self):
        """启动策略"""
        self.active = True
        asyncio.create_task(self._price_monitor())
        self.logger.info("闪电套利策略启动")
        
    async def generate_signal(self, symbol: str, data: Dict) -> Optional[Dict]:
        """生成交易信号"""
        try:
            # 获取所有交易所的最新价格
            current_prices = {}
            for exchange in self.exchange_manager.exchanges.values():
                price_info = await exchange.get_best_price(symbol)
                if not price_info:
                    continue
                current_prices[exchange.name] = {
                    'bid': price_info['bid'],
                    'ask': price_info['ask'],
                    'mid': (price_info['bid'] + price_info['ask']) / 2
                }
                
            if len(current_prices) < 2:
                return None
                
            # 检测价格异常
            signal = await self._detect_price_anomaly(symbol, current_prices)
            return signal
            
        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            return None
            
    async def calculate_position_size(self, symbol: str, signal: Dict) -> Optional[Decimal]:
        """计算仓位大小"""
        try:
            available_balance = await self.risk_manager.get_available_balance()
            if not available_balance:
                return None
                
            # 基于价格偏离程度计算仓位
            deviation = signal['deviation']
            base_size = available_balance * Decimal('0.15')  # 使用15%可用资金
            
            # 根据偏离度调整仓位
            if deviation < self.std_threshold * Decimal('1.2'):
                position_size = base_size * Decimal('0.5')
            elif deviation < self.std_threshold * Decimal('1.5'):
                position_size = base_size * Decimal('0.8')
            else:
                position_size = base_size
                
            # 确保符合最小交易金额
            min_notional = Decimal('5')
            return max(position_size, min_notional)
            
        except Exception as e:
            self.logger.error(f"计算仓位大小失败: {e}")
            return None
            
    async def _price_monitor(self):
        """监控价格变化"""
        while self.active:
            try:
                for exchange in self.exchange_manager.exchanges.values():
                    for symbol in exchange.markets:
                        price_info = await exchange.get_best_price(symbol)
                        if not price_info:
                            continue
                            
                        # 更新价格窗口
                        if symbol not in self.price_windows:
                            self.price_windows[symbol] = {
                                exchange.name: {
                                    'prices': [],
                                    'timestamps': []
                                }
                            }
                        elif exchange.name not in self.price_windows[symbol]:
                            self.price_windows[symbol][exchange.name] = {
                                'prices': [],
                                'timestamps': []
                            }
                            
                        window = self.price_windows[symbol][exchange.name]
                        mid_price = (price_info['bid'] + price_info['ask']) / 2
                        
                        window['prices'].append(float(mid_price))
                        window['timestamps'].append(datetime.utcnow())
                        
                        # 保持窗口大小
                        if len(window['prices']) > self.window_size:
                            window['prices'].pop(0)
                            window['timestamps'].pop(0)
                            
                await asyncio.sleep(0.1)  # 100ms更新频率
                
            except Exception as e:
                self.logger.error(f"价格监控异常: {e}")
                await asyncio.sleep(1)
                
    async def _detect_price_anomaly(self, symbol: str, current_prices: Dict) -> Optional[Dict]:
        """检测价格异常"""
        try:
            if symbol not in self.price_windows:
                return None
                
            anomalies = {}
            base_stats = {}
            
            # 计算每个交易所的价格统计信息
            for exchange_name, price_data in current_prices.items():
                if exchange_name not in self.price_windows[symbol]:
                    continue
                    
                window = self.price_windows[symbol][exchange_name]
                if len(window['prices']) < self.window_size:
                    continue
                    
                # 计算统计指标
                prices = np.array(window['prices'])
                mean = np.mean(prices)
                std = np.std(prices)
                current_mid = float(price_data['mid'])
                
                # 计算z-score
                z_score = (current_mid - mean) / std if std > 0 else 0
                
                base_stats[exchange_name] = {
                    'mean': Decimal(str(mean)),
                    'std': Decimal(str(std)),
                    'current': Decimal(str(current_mid)),
                    'z_score': Decimal(str(z_score))
                }
                
                # 检测异常
                if abs(z_score) > float(self.std_threshold):
                    price_change = abs(current_mid - mean) / mean
                    if price_change > float(self.min_spike_pct):
                        anomalies[exchange_name] = {
                            'direction': 'high' if z_score > 0 else 'low',
                            'deviation': Decimal(str(abs(z_score))),
                            'price_change': Decimal(str(price_change))
                        }
                        
            # 如果发现异常，生成交易信号
            if anomalies:
                # 找出最异常的交易所
                max_deviation = max(
                    (ex_data['deviation'], ex_name) 
                    for ex_name, ex_data in anomalies.items()
                )
                anomaly_exchange = max_deviation[1]
                anomaly_data = anomalies[anomaly_exchange]
                
                # 找出最正常的交易所作为对手方
                normal_exchange = None
                min_deviation = float('inf')
                for ex_name, stats in base_stats.items():
                    if ex_name != anomaly_exchange and abs(float(stats['z_score'])) < min_deviation:
                        min_deviation = abs(float(stats['z_score']))
                        normal_exchange = ex_name
                        
                if normal_exchange:
                    return {
                        'symbol': symbol,
                        'type': 'flash_arbitrage',
                        'timestamp': datetime.utcnow(),
                        'deviation': anomaly_data['deviation'],
                        'price_change': anomaly_data['price_change'],
                        'buy': {
                            'exchange': anomaly_exchange if anomaly_data['direction'] == 'low' else normal_exchange,
                            'price': current_prices[anomaly_exchange if anomaly_data['direction'] == 'low' else normal_exchange]['ask']
                        },
                        'sell': {
                            'exchange': normal_exchange if anomaly_data['direction'] == 'low' else anomaly_exchange,
                            'price': current_prices[normal_exchange if anomaly_data['direction'] == 'low' else anomaly_exchange]['bid']
                        }
                    }
                    
            return None
            
        except Exception as e:
            self.logger.error(f"检测价格异常失败: {e}")
            return None
            
    async def _close_position(self, symbol: str, position: Dict, reason: str):
        """平仓"""
        try:
            close_orders = {}
            for exchange_name, order in position['orders'].items():
                side = 'sell' if order['side'] == 'buy' else 'buy'
                close_order = await self.exchange_manager.exchanges[exchange_name].create_order(
                    symbol=symbol,
                    order_type='market',
                    side=side,
                    amount=order['amount']
                )
                close_orders[exchange_name] = close_order
                
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
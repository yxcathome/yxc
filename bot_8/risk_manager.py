import numpy as np
import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import json
import threading
from decimal import Decimal
from config import Config
from logger import Logger

class RiskManager:
    def __init__(self, exchange_id: str):
        self.logger = Logger("RiskManager")
        self.exchange_id = exchange_id
        self.exchange = self.market_data.exchange
        self.risk_metrics = {}
        self.position_limits = {}
        self.daily_stats = self._init_daily_stats()
        self.risk_lock = threading.Lock()
        
        # 加载风控配置
        self.load_risk_config()
        
        # 初始化风控检查定时器
        self._start_risk_check_timer()
        
    def _init_daily_stats(self) -> Dict:
        """初始化每日统计数据"""
        return {
            'total_pnl': 0,
            'max_drawdown': 0,
            'peak_balance': 0,
            'trades_count': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'last_reset': datetime.utcnow(),
            'positions': {},
            'risk_events': []
        }

    def load_risk_config(self):
        """加载风控配置"""
        self.risk_config = {
            'position_limits': {
                'max_single_position': 0.1,  # 单个仓位最大比例
                'max_total_positions': 0.3,   # 总仓位最大比例
                'max_positions_count': 5      # 最大同时持仓数
            },
            'loss_limits': {
                'max_single_loss': 0.02,      # 单笔最大亏损
                'max_daily_loss': 0.05,       # 每日最大亏损
                'max_drawdown': 0.15          # 最大回撤
            },
            'volatility_limits': {
                'max_volatility': 0.05,       # 最大可接受波动率
                'min_liquidity': 100000       # 最小流动性要求
            },
            'exposure_limits': {
                'max_leverage': 3,            # 最大杠杆
                'max_concentration': 0.3      # 最大集中度
            }
        }

    def check_position_risk(self, symbol: str, 
                          side: str, 
                          amount: float, 
                          price: float) -> bool:
        """
        检查开仓风险
        """
        with self.risk_lock:
            try:
                # 获取账户信息
                account = self.exchange.fetch_balance()
                total_equity = float(account['total']['USDT'])
                used_equity = float(account['used']['USDT'])
                
                # 计算持仓价值
                position_value = amount * price
                
                # 检查单个持仓限制
                if position_value / total_equity > self.risk_config['position_limits']['max_single_position']:
                    self.logger.warning(f"Position size exceeds single position limit for {symbol}")
                    return False
                
                # 检查总持仓限制
                total_positions_value = used_equity + position_value
                if total_positions_value / total_equity > self.risk_config['position_limits']['max_total_positions']:
                    self.logger.warning("Total positions value exceeds limit")
                    return False
                
                # 检查持仓数量限制
                if len(self.daily_stats['positions']) >= self.risk_config['position_limits']['max_positions_count']:
                    self.logger.warning("Maximum positions count reached")
                    return False
                
                # 检查波动率限制
                volatility = self._calculate_volatility(symbol)
                if volatility > self.risk_config['volatility_limits']['max_volatility']:
                    self.logger.warning(f"Volatility too high for {symbol}: {volatility:.4f}")
                    return False
                
                # 检查流动性
                liquidity = self._check_liquidity(symbol)
                if liquidity < self.risk_config['volatility_limits']['min_liquidity']:
                    self.logger.warning(f"Insufficient liquidity for {symbol}: {liquidity:.2f}")
                    return False
                
                return True
                
            except Exception as e:
                self.logger.error(f"Error in position risk check: {str(e)}")
                return False

    def update_position_status(self, symbol: str, 
                             pnl: float, 
                             position_data: Dict):
        """
        更新持仓状态和风险指标
        """
        with self.risk_lock:
            try:
                current_time = datetime.utcnow()
                
                # 更新每日统计
                self.daily_stats['total_pnl'] += pnl
                self.daily_stats['trades_count'] += 1
                if pnl > 0:
                    self.daily_stats['winning_trades'] += 1
                else:
                    self.daily_stats['losing_trades'] += 1
                
                # 更新最大回撤
                current_balance = self._get_account_balance()
                if current_balance > self.daily_stats['peak_balance']:
                    self.daily_stats['peak_balance'] = current_balance
                current_drawdown = (self.daily_stats['peak_balance'] - current_balance) / self.daily_stats['peak_balance']
                self.daily_stats['max_drawdown'] = max(self.daily_stats['max_drawdown'], current_drawdown)
                
                # 检查风险限制
                self._check_risk_limits(pnl, current_drawdown)
                
                # 更新持仓信息
                self.daily_stats['positions'][symbol] = position_data
                
            except Exception as e:
                self.logger.error(f"Error updating position status: {str(e)}")

    def _check_risk_limits(self, pnl: float, 
                          current_drawdown: float) -> bool:
        """
        检查是否触发风险限制
        """
        risk_triggered = False
        
        # 检查单笔亏损限制
        if abs(pnl) > self.risk_config['loss_limits']['max_single_loss']:
            self._record_risk_event('single_loss_limit', pnl)
            risk_triggered = True
        
        # 检查每日亏损限制
        if self.daily_stats['total_pnl'] < -self.risk_config['loss_limits']['max_daily_loss']:
            self._record_risk_event('daily_loss_limit', self.daily_stats['total_pnl'])
            risk_triggered = True
        
        # 检查最大回撤限制
        if current_drawdown > self.risk_config['loss_limits']['max_drawdown']:
            self._record_risk_event('max_drawdown_limit', current_drawdown)
            risk_triggered = True
        
        if risk_triggered:
            self._execute_risk_mitigation()
        
        return not risk_triggered

    def _calculate_volatility(self, symbol: str) -> float:
        """
        计算波动率
        """
        try:
            df = self.market_data.update_market_data(symbol, Config.BASE_TIMEFRAME)
            returns = df['close'].pct_change()
            return returns.std() * np.sqrt(365 * 24)
        except Exception as e:
            self.logger.error(f"Error calculating volatility: {str(e)}")
            return float('inf')

    def _check_liquidity(self, symbol: str) -> float:
        """
        检查市场流动性
        """
        try:
            orderbook = self.exchange.fetch_order_book(symbol)
            bid_liquidity = sum(bid[1] for bid in orderbook['bids'][:5])
            ask_liquidity = sum(ask[1] for ask in orderbook['asks'][:5])
            return min(bid_liquidity, ask_liquidity)
        except Exception as e:
            self.logger.error(f"Error checking liquidity: {str(e)}")
            return 0

    def _record_risk_event(self, event_type: str, value: float):
        """
        记录风险事件
        """
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'type': event_type,
            'value': value
        }
        self.daily_stats['risk_events'].append(event)
        self.logger.warning(f"Risk event recorded: {event}")

    def _execute_risk_mitigation(self):
        """
        执行风险缓解措施
        """
        try:
            # 关闭所有持仓
            for symbol in list(self.daily_stats['positions'].keys()):
                self.close_position(symbol, 'Risk limit triggered')
            
            # 暂停交易
            self.trading_enabled = False
            
            # 发送警报
            self._send_risk_alert()
            
        except Exception as e:
            self.logger.error(f"Error in risk mitigation: {str(e)}")

    def _send_risk_alert(self):
        """
        发送风险警报
        """
        alert = {
            'timestamp': datetime.utcnow().isoformat(),
            'daily_stats': self.daily_stats,
            'risk_events': self.daily_stats['risk_events']
        }
        self.logger.critical(f"Risk alert: {json.dumps(alert, indent=2)}")

    def _start_risk_check_timer(self):
        """
        启动定期风险检查定时器
        """
        def risk_check():
            while True:
                try:
                    self._periodic_risk_check()
                    time.sleep(60)  # 每分钟检查一次
                except Exception as e:
                    self.logger.error(f"Error in periodic risk check: {str(e)}")
                
        threading.Thread(target=risk_check, daemon=True).start()

    def _periodic_risk_check(self):
        """
        定期风险检查
        """
        current_time = datetime.utcnow()
        
        # 检查是否需要重置每日统计
        if current_time - self.daily_stats['last_reset'] > timedelta(days=1):
            self._reset_daily_stats()
        
        # 检查所有持仓的风险状态
        for symbol, position in self.daily_stats['positions'].items():
            self._check_position_risk_status(symbol, position)

    def _reset_daily_stats(self):
        """
        重置每日统计数据
        """
        self.daily_stats = self._init_daily_stats()
        self.logger.info("Daily stats reset")

    def export_risk_report(self) -> Dict:
        """
        导出风险报告
        """
        return {
            'daily_stats': self.daily_stats,
            'risk_config': self.risk_config,
            'current_positions': len(self.daily_stats['positions']),
            'risk_events': self.daily_stats['risk_events'],
            'win_rate': (self.daily_stats['winning_trades'] / 
                        max(self.daily_stats['trades_count'], 1))
        }
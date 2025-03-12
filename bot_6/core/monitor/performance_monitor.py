from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
import numpy as np
import pandas as pd
from utils.logger import setup_logger

class PerformanceMonitor:
    def __init__(self, risk_manager):
        self.risk_manager = risk_manager
        self.logger = setup_logger("performance_monitor")
        
        # 性能指标
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': Decimal('0'),
            'max_drawdown': Decimal('0'),
            'win_rate': Decimal('0'),
            'profit_factor': Decimal('0'),
            'sharpe_ratio': Decimal('0'),
            'sortino_ratio': Decimal('0'),
            'calmar_ratio': Decimal('0')
        }
        
        # 历史数据
        self.trade_history = []
        self.daily_returns = []
        self.equity_curve = []
        
        # 监控配置
        self.update_interval = 300  # 5分钟更新一次
        self.history_window = 90   # 保存90天的历史数据
        
    async def start(self):
        """启动监控"""
        asyncio.create_task(self._monitor_loop())
        self.logger.info("性能监控启动")
        
    async def update_trade(self, trade_info: Dict):
        """更新交易记录"""
        try:
            self.trade_history.append({
                'timestamp': datetime.utcnow(),
                'symbol': trade_info['symbol'],
                'strategy': trade_info['strategy'],
                'side': trade_info['side'],
                'entry_price': trade_info['entry_price'],
                'exit_price': trade_info['exit_price'],
                'amount': trade_info['amount'],
                'pnl': trade_info['pnl'],
                'duration': trade_info['duration']
            })
            
            # 更新基础指标
            self.metrics['total_trades'] += 1
            if trade_info['pnl'] > 0:
                self.metrics['winning_trades'] += 1
            else:
                self.metrics['losing_trades'] += 1
                
            self.metrics['total_pnl'] += trade_info['pnl']
            
            # 更新胜率
            self.metrics['win_rate'] = Decimal(str(
                self.metrics['winning_trades'] / self.metrics['total_trades']
            ))
            
            # 触发指标计算
            await self._calculate_metrics()
            
        except Exception as e:
            self.logger.error(f"更新交易记录失败: {e}")
            
    async def get_performance_report(self) -> Dict:
        """获取性能报告"""
        try:
            report = {
                'metrics': self.metrics.copy(),
                'recent_trades': self.trade_history[-10:],
                'daily_stats': await self._get_daily_stats(),
                'strategy_stats': await self._get_strategy_stats(),
                'risk_metrics': await self._get_risk_metrics()
            }
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成性能报告失败: {e}")
            return {}
            
    async def _monitor_loop(self):
        """监控循环"""
        while True:
            try:
                # 更新指标
                await self._calculate_metrics()
                
                # 清理过期数据
                await self._clean_old_data()
                
                # 记录权益曲线
                balance = await self.risk_manager._get_total_balance()
                if balance:
                    self.equity_curve.append({
                        'timestamp': datetime.utcnow(),
                        'balance': balance
                    })
                    
                # 检查异常情况
                await self._check_anomalies()
                
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(60)
                
    async def _calculate_metrics(self):
        """计算性能指标"""
        try:
            if not self.trade_history:
                return
                
            # 计算收益率序列
            returns = []
            for trade in self.trade_history:
                returns.append(float(trade['pnl']))
                
            returns = np.array(returns)
            
            # 计算盈亏因子
            winning_trades = returns[returns > 0]
            losing_trades = returns[returns < 0]
            
            if len(losing_trades) > 0 and abs(sum(losing_trades)) > 0:
                profit_factor = sum(winning_trades) / abs(sum(losing_trades))
                self.metrics['profit_factor'] = Decimal(str(profit_factor))
                
            # 计算夏普比率
            if len(returns) > 1:
                risk_free_rate = 0.03  # 假设无风险利率3%
                returns_mean = np.mean(returns)
                returns_std = np.std(returns)
                
                if returns_std > 0:
                    sharpe = (returns_mean - risk_free_rate) / returns_std
                    self.metrics['sharpe_ratio'] = Decimal(str(sharpe))
                    
            # 计算索提诺比率
            if len(returns) > 1:
                negative_returns = returns[returns < 0]
                if len(negative_returns) > 0:
                    downside_std = np.std(negative_returns)
                    if downside_std > 0:
                        sortino = (returns_mean - risk_free_rate) / downside_std
                        self.metrics['sortino_ratio'] = Decimal(str(sortino))
                        
            # 计算最大回撤
            if self.equity_curve:
                balances = [float(point['balance']) for point in self.equity_curve]
                max_drawdown = 0
                peak = balances[0]
                
                for balance in balances:
                    if balance > peak:
                        peak = balance
                    drawdown = (peak - balance) / peak
                    max_drawdown = max(max_drawdown, drawdown)
                    
                self.metrics['max_drawdown'] = Decimal(str(max_drawdown))
                
                # 计算卡玛比率
                if max_drawdown > 0:
                    returns_annual = returns_mean * 252  # 假设252个交易日
                    calmar = returns_annual / max_drawdown
                    self.metrics['calmar_ratio'] = Decimal(str(calmar))
                    
        except Exception as e:
            self.logger.error(f"计算性能指标失败: {e}")
            
    async def _clean_old_data(self):
        """清理过期数据"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.history_window)
            
            # 清理交易历史
            self.trade_history = [
                trade for trade in self.trade_history
                if trade['timestamp'] > cutoff_date
            ]
            
            # 清理权益曲线
            self.equity_curve = [
                point for point in self.equity_curve
                if point['timestamp'] > cutoff_date
            ]
            
        except Exception as e:
            self.logger.error(f"清理过期数据失败: {e}")
            
    async def _check_anomalies(self):
        """检查异常情况"""
        try:
            # 检查连续亏损
            recent_trades = self.trade_history[-5:]
            losing_streak = sum(1 for trade in recent_trades if trade['pnl'] < 0)
            
            if losing_streak >= 5:
                self.logger.warning(f"检测到连续亏损: {losing_streak}笔")
                
            # 检查盈利能力下降
            if len(self.trade_history) > 20:
                recent_win_rate = sum(
                    1 for trade in self.trade_history[-10:]
                    if trade['pnl'] > 0
                ) / 10
                
                overall_win_rate = float(self.metrics['win_rate'])
                
                if recent_win_rate < overall_win_rate * 0.7:
                    self.logger.warning(
                        f"盈利能力显著下降: 近期胜率{recent_win_rate:.2%} vs "
                        f"整体胜率{overall_win_rate:.2%}"
                    )
                    
            # 检查回撤
            if float(self.metrics['max_drawdown']) > 0.15:  # 15%回撤警告
                self.logger.warning(f"大幅回撤警告: {self.metrics['max_drawdown']:.2%}")
                
        except Exception as e:
            self.logger.error(f"检查异常情况失败: {e}")
from decimal import Decimal
from typing import Dict, Optional, List
import asyncio
from datetime import datetime, timedelta
from utils.logger import setup_logger
from config.risk_config import STRATEGY_RISK_CONFIG

class StrategyRiskManager:
    def __init__(self, bot):
        self.bot = bot
        self.logger = setup_logger("strategy_risk")
        self.config = STRATEGY_RISK_CONFIG
        
        # 策略状态跟踪
        self.strategy_states = {}
        self.strategy_metrics = {}
        
        # 风控限制
        self.max_daily_trades = 100  # 每个策略每日最大交易次数
        self.max_concurrent_signals = 3  # 每个策略最大并发信号数
        
    async def initialize(self):
        """初始化策略风控"""
        try:
            # 加载策略历史数据
            await self._load_strategy_history()
            
            # 启动监控任务
            asyncio.create_task(self._monitor_strategies())
            
            self.logger.info("策略风控管理器初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"策略风控管理器初始化失败: {e}")
            return False
            
    async def check_strategy_signal(self, strategy_id: str, signal: Dict) -> bool:
        """检查策略信号"""
        try:
            # 检查策略状态
            if not await self._check_strategy_state(strategy_id):
                return False
                
            # 根据策略类型检查信号
            strategy_type = strategy_id.split('.')[0]
            if strategy_type in self.config:
                if not await self._check_signal_rules(strategy_type, signal):
                    return False
                    
            # 检查并发信号数
            if not await self._check_concurrent_signals(strategy_id):
                return False
                
            # 检查日交易次数
            if not await self._check_daily_trades(strategy_id):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查策略信号失败: {e}")
            return False
            
    async def update_strategy_metrics(self, strategy_id: str, metrics: Dict):
        """更新策略指标"""
        try:
            if strategy_id not in self.strategy_metrics:
                self.strategy_metrics[strategy_id] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'total_pnl': Decimal('0'),
                    'max_drawdown': Decimal('0'),
                    'daily_trades': 0,
                    'last_trade_time': None
                }
                
            self.strategy_metrics[strategy_id].update(metrics)
            await self._calculate_strategy_performance(strategy_id)
            
        except Exception as e:
            self.logger.error(f"更新策略指标失败: {e}")
            
    async def _load_strategy_history(self):
        """加载策略历史数据"""
        try:
            for strategy in self.bot.strategy_coordinator.strategies.values():
                history = await self.bot.database.load_strategy_history(strategy.id)
                if history:
                    self.strategy_metrics[strategy.id] = history
                    
        except Exception as e:
            self.logger.error(f"加载策略历史数据失败: {e}")
            
    async def _monitor_strategies(self):
        """监控策略状态"""
        while True:
            try:
                current_time = datetime.utcnow()
                
                # 检查每个策略的状态
                for strategy_id, metrics in self.strategy_metrics.items():
                    # 检查日重置
                    if 'last_reset' in metrics:
                        last_reset = metrics['last_reset']
                        if current_time.date() > last_reset.date():
                            await self._reset_daily_metrics(strategy_id)
                            
                    # 检查性能指标
                    await self._check_strategy_performance(strategy_id)
                    
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                self.logger.error(f"监控策略状态异常: {e}")
                await asyncio.sleep(5)
                
    async def _check_strategy_state(self, strategy_id: str) -> bool:
        """检查策略状态"""
        try:
            metrics = self.strategy_metrics.get(strategy_id, {})
            
            # 检查策略是否被禁用
            if metrics.get('disabled', False):
                return False
                
            # 检查最大回撤
            if metrics.get('max_drawdown', Decimal('0')) > Decimal('0.2'):  # 20%最大回撤
                return False
                
            # 检查胜率
            total_trades = metrics.get('total_trades', 0)
            if total_trades > 20:  # 至少20笔交易
                win_rate = metrics.get('winning_trades', 0) / total_trades
                if win_rate < Decimal('0.4'):  # 胜率低于40%
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"检查策略状态失败: {e}")
            return False
            
    async def _check_signal_rules(self, strategy_type: str, signal: Dict) -> bool:
        """检查信号规则"""
        try:
            rules = self.config[strategy_type]
            
            if strategy_type == 'arbitrage':
                # 检查价差
                if signal.get('spread', Decimal('0')) < rules['min_spread']:
                    return False
                # 检查成交量
                if signal.get('volume', Decimal('0')) < rules['min_volume']:
                    return False
                    
            elif strategy_type == 'trend':
                # 检查趋势强度
                if signal.get('trend_strength', Decimal('0')) < rules['min_trend_strength']:
                    return False
                # 检查确认数
                if signal.get('confirmations', 0) < rules['confirmation_required']:
                    return False
                    
            elif strategy_type == 'mean_reversion':
                # 检查偏离度
                if signal.get('deviation', Decimal('0')) > rules['max_deviation']:
                    return False
                # 检查回归概率
                if signal.get('reversion_prob', Decimal('0')) < rules['min_reversion_prob']:
                    return False
                    
            elif strategy_type == 'grid':
                # 检查网格间距
                if signal.get('grid_spacing', Decimal('0')) < rules['grid_spacing']:
                    return False
                # 检查成交量
                if signal.get('volume', Decimal('0')) < rules['volume_filter']:
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"检查信号规则失败: {e}")
            return False
            
    async def _check_concurrent_signals(self, strategy_id: str) -> bool:
        """检查并发信号数"""
        try:
            active_signals = len([
                pos for pos in self.bot.position_tracker.positions.values()
                if pos['strategy_id'] == strategy_id
            ])
            
            return active_signals < self.max_concurrent_signals
            
        except Exception as e:
            self.logger.error(f"检查并发信号失败: {e}")
            return False
            
    async def _check_daily_trades(self, strategy_id: str) -> bool:
        """检查日交易次数"""
        try:
            metrics = self.strategy_metrics.get(strategy_id, {})
            daily_trades = metrics.get('daily_trades', 0)
            
            return daily_trades < self.max_daily_trades
            
        except Exception as e:
            self.logger.error(f"检查日交易次数失败: {e}")
            return False
            
    async def _calculate_strategy_performance(self, strategy_id: str):
        """计算策略性能"""
        try:
            metrics = self.strategy_metrics[strategy_id]
            total_trades = metrics['total_trades']
            
            if total_trades > 0:
                # 计算胜率
                win_rate = metrics['winning_trades'] / total_trades
                metrics['win_rate'] = win_rate
                
                # 计算平均收益
                avg_pnl = metrics['total_pnl'] / total_trades
                metrics['avg_pnl'] = avg_pnl
                
                # 计算夏普比率
                if 'returns' in metrics and len(metrics['returns']) > 0:
                    returns = metrics['returns']
                    avg_return = sum(returns) / len(returns)
                    std_dev = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                    if std_dev > 0:
                        sharpe = (avg_return - Decimal('0.03')) / std_dev  # 假设无风险利率3%
                        metrics['sharpe_ratio'] = sharpe
                        
        except Exception as e:
            self.logger.error(f"计算策略性能失败: {e}")
            
    async def _reset_daily_metrics(self, strategy_id: str):
        """重置每日指标"""
        try:
            metrics = self.strategy_metrics[strategy_id]
            metrics['daily_trades'] = 0
            metrics['last_reset'] = datetime.utcnow()
            
        except Exception as e:
            self.logger.error(f"重置每日指标失败: {e}")
            
    async def _check_strategy_performance(self, strategy_id: str):
        """检查策略性能"""
        try:
            metrics = self.strategy_metrics[strategy_id]
            
            # 检查是否需要禁用策略
            if metrics.get('total_trades', 0) > 50:  # 至少50笔交易
                # 检查胜率
                if metrics.get('win_rate', 0) < Decimal('0.4'):
                    await self._disable_strategy(strategy_id, '胜率过低')
                    return
                    
                # 检查夏普比率
                if metrics.get('sharpe_ratio', 0) < Decimal('-1'):
                    await self._disable_strategy(strategy_id, '夏普比率过低')
                    return
                    
                # 检查最大回撤
                if metrics.get('max_drawdown', 0) > Decimal('0.2'):
                    await self._disable_strategy(strategy_id, '回撤过大')
                    return
                    
        except Exception as e:
            self.logger.error(f"检查策略性能失败: {e}")
            
    async def _disable_strategy(self, strategy_id: str, reason: str):
        """禁用策略"""
        try:
            self.strategy_metrics[strategy_id]['disabled'] = True
            self.strategy_metrics[strategy_id]['disable_reason'] = reason
            self.strategy_metrics[strategy_id]['disable_time'] = datetime.utcnow()
            
            # 关闭所有持仓
            positions = [
                pos_id for pos_id, pos in self.bot.position_tracker.positions.items()
                if pos['strategy_id'] == strategy_id
            ]
            
            for position_id in positions:
                await self.bot.position_tracker.close_position(position_id, 'strategy_disabled')
                
            self.logger.warning(f"策略 {strategy_id} 已禁用，原因: {reason}")
            
        except Exception as e:
            self.logger.error(f"禁用策略失败: {e}")
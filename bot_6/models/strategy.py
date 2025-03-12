from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal
import uuid
import json

class Strategy:
    def __init__(self, id: Optional[str] = None, **kwargs):
        self.id = id or str(uuid.uuid4())
        self.name = kwargs.get('name', '')
        self.type = kwargs.get('type', '')
        self.config = kwargs.get('config', {})
        self.status = kwargs.get('status', 'stopped')
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.updated_at = kwargs.get('updated_at', datetime.utcnow())
        
        # 运行时数据
        self.positions = {}  # position_id -> Position
        self.performance = {
            'total_pnl': Decimal('0'),
            'day_pnl': Decimal('0'),
            'win_rate': Decimal('0'),
            'sharpe_ratio': Decimal('0')
        }
        
    async def start(self):
        """启动策略"""
        if self.status != 'active':
            self.status = 'active'
            self.updated_at = datetime.utcnow()
            # TODO: 实现具体的策略启动逻辑
            
    async def pause(self):
        """暂停策略"""
        if self.status == 'active':
            self.status = 'paused'
            self.updated_at = datetime.utcnow()
            # TODO: 实现具体的策略暂停逻辑
            
    async def stop(self):
        """停止策略"""
        if self.status != 'stopped':
            self.status = 'stopped'
            self.updated_at = datetime.utcnow()
            # TODO: 实现具体的策略停止逻辑
            
    async def update_performance(self):
        """更新策略表现指标"""
        try:
            total_pnl = Decimal('0')
            day_pnl = Decimal('0')
            wins = 0
            total_trades = 0
            returns = []
            
            # 统计所有持仓的表现
            for position in self.positions.values():
                total_pnl += position.unrealized_pnl + position.realized_pnl
                
                # 计算当日盈亏
                if position.created_at.date() == datetime.utcnow().date():
                    day_pnl += position.unrealized_pnl + position.realized_pnl
                    
                # 统计胜率
                if position.status == 'closed':
                    total_trades += 1
                    if position.realized_pnl > 0:
                        wins += 1
                        
                # 收集收益率数据用于计算夏普比率
                if position.roi is not None:
                    returns.append(float(position.roi))
                    
            # 计算胜率
            self.performance['win_rate'] = Decimal(str(wins / total_trades if total_trades > 0 else 0))
            
            # 计算夏普比率
            if returns:
                import numpy as np
                returns_array = np.array(returns)
                excess_returns = returns_array - 0.02/365  # 假设无风险利率为2%
                sharpe_ratio = np.sqrt(365) * np.mean(excess_returns) / np.std(excess_returns) if len(returns) > 1 else 0
                self.performance['sharpe_ratio'] = Decimal(str(sharpe_ratio))
                
            self.performance['total_pnl'] = total_pnl
            self.performance['day_pnl'] = day_pnl
            
        except Exception as e:
            raise Exception(f"更新策略表现失败: {e}")
            
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'config': self.config,
            'status': self.status,
            'totalPnL': float(self.performance['total_pnl']),
            'dayPnL': float(self.performance['day_pnl']),
            'winRate': float(self.performance['win_rate']),
            'sharpeRatio': float(self.performance['sharpe_ratio']),
            'createdAt': self.created_at.isoformat(),
            'updatedAt': self.updated_at.isoformat()
        }

class StrategyFactory:
    """策略工厂类"""
    @staticmethod
    async def create_strategy(strategy_type: str, config: Dict) -> Strategy:
        """创建策略实例"""
        try:
            if strategy_type == 'grid':
                from strategies.grid.range_grid import RangeGridStrategy
                return RangeGridStrategy(**config)
            elif strategy_type == 'momentum':
                from strategies.trend.momentum import MomentumStrategy
                return MomentumStrategy(**config)
            elif strategy_type == 'funding_arb':
                from strategies.arbitrage.funding_arb import FundingArbitrageStrategy
                return FundingArbitrageStrategy(**config)
            else:
                raise ValueError(f"未知的策略类型: {strategy_type}")
                
        except Exception as e:
            raise Exception(f"创建策略失败: {e}")
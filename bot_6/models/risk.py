from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal
import uuid

class RiskMetrics:
    def __init__(self):
        self.overall_score = Decimal('0')
        self.risk_level = 'low'
        self.metrics = {
            'position': {
                'leverage': Decimal('0'),
                'concentration': Decimal('0'),
                'volatility': Decimal('0')
            },
            'capital': {
                'margin_usage': Decimal('0'),
                'daily_loss': Decimal('0'),
                'drawdown': Decimal('0'),
                'available_margin': Decimal('0')
            }
        }
        self.thresholds = {
            'leverage': {
                'medium': Decimal('3'),
                'high': Decimal('5')
            },
            'concentration': {
                'medium': Decimal('0.2'),
                'high': Decimal('0.3')
            },
            'volatility': {
                'medium': Decimal('0.02'),
                'high': Decimal('0.05')
            },
            'margin_usage': {
                'medium': Decimal('0.7'),
                'high': Decimal('0.85')
            },
            'daily_loss': {
                'medium': Decimal('0.05'),
                'high': Decimal('0.1')
            },
            'drawdown': {
                'medium': Decimal('0.1'),
                'high': Decimal('0.2')
            }
        }
        
    async def calculate_metrics(self, positions: List[Dict], account_value: Decimal):
        """计算风控指标"""
        try:
            # 计算杠杆率
            total_exposure = sum(
                Decimal(str(pos['amount'])) * Decimal(str(pos['current_price']))
                for pos in positions
            )
            self.metrics['position']['leverage'] = total_exposure / account_value if account_value > 0 else Decimal('0')
            
            # 计算持仓集中度
            if positions:
                max_position_value = max(
                    Decimal(str(pos['amount'])) * Decimal(str(pos['current_price']))
                    for pos in positions
                )
                self.metrics['position']['concentration'] = max_position_value / total_exposure if total_exposure > 0 else Decimal('0')
                
            # 计算波动率
            from statistics import stdev
            if len(positions) >= 2:
                returns = [
                    float((Decimal(str(pos['current_price'])) - Decimal(str(pos['entry_price']))) / Decimal(str(pos['entry_price'])))
                    for pos in positions
                ]
                self.metrics['position']['volatility'] = Decimal(str(stdev(returns)))
                
            # 计算保证金使用率
            margin_used = sum(
                Decimal(str(pos['amount'])) * Decimal(str(pos['entry_price'])) / self.metrics['position']['leverage']
                for pos in positions
            )
            self.metrics['capital']['margin_usage'] = margin_used / account_value if account_value > 0 else Decimal('0')
            self.metrics['capital']['available_margin'] = account_value - margin_used
            
            # 计算日损失
            daily_pnl = sum(
                Decimal(str(pos['unrealized_pnl'])) + Decimal(str(pos['realized_pnl']))
                for pos in positions
                if datetime.fromisoformat(pos['created_at']).date() == datetime.utcnow().date()
            )
            self.metrics['capital']['daily_loss'] = abs(daily_pnl) / account_value if account_value > 0 and daily_pnl < 0 else Decimal('0')
            
            # 计算回撤
            self.metrics['capital']['drawdown'] = await self._calculate_drawdown(account_value)
            
            # 计算整体风险分数和等级
            await self._calculate_risk_level()
            
        except Exception as e:
            raise Exception(f"计算风控指标失败: {e}")
            
    async def _calculate_drawdown(self, current_value: Decimal) -> Decimal:
        """计算回撤"""
        try:
            # 从数据库获取历史最高值
            from models.database import Database
            db = Database()
            async with db.pg_pool.acquire() as conn:
                max_value = await conn.fetchval("""
                    SELECT MAX(value)
                    FROM account_history
                    WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                """)
                
            if max_value:
                max_value = Decimal(str(max_value))
                return (max_value - current_value) / max_value if max_value > 0 else Decimal('0')
            return Decimal('0')
            
        except Exception as e:
            raise Exception(f"计算回撤失败: {e}")
            
    async def _calculate_risk_level(self):
        """计算整体风险等级"""
        try:
            risk_scores = []
            
            # 评估各项指标的风险等级
            for metric_type, metrics in self.metrics.items():
                for name, value in metrics.items():
                    if name in self.thresholds:
                        if value >= self.thresholds[name]['high']:
                            risk_scores.append(1.0)
                        elif value >= self.thresholds[name]['medium']:
                            risk_scores.append(0.5)
                        else:
                            risk_scores.append(0.0)
                            
            # 计算整体风险分数
            if risk_scores:
                self.overall_score = Decimal(str(sum(risk_scores) / len(risk_scores)))
                
                # 确定风险等级
                if self.overall_score >= Decimal('0.7'):
                    self.risk_level = 'high'
                elif self.overall_score >= Decimal('0.3'):
                    self.risk_level = 'medium'
                else:
                    self.risk_level = 'low'
                    
        except Exception as e:
            raise Exception(f"计算风险等级失败: {e}")
            
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'overall': {
                'score': float(self.overall_score),
                'level': self.risk_level,
                'updateTime': datetime.utcnow().isoformat()
            },
            'position': {
                key: float(value)
                for key, value in self.metrics['position'].items()
            },
            'capital': {
                key: float(value)
                for key, value in self.metrics['capital'].items()
            }
        }

class RiskAlert:
    def __init__(self, id: Optional[str] = None, **kwargs):
        self.id = id or str(uuid.uuid4())
        self.level = kwargs.get('level', 'medium')
        self.title = kwargs.get('title', '')
        self.message = kwargs.get('message', '')
        self.status = kwargs.get('status', 'active')
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.handled_at = kwargs.get('handled_at')
        
    async def handle(self):
        """处理警报"""
        self.status = 'handled'
        self.handled_at = datetime.utcnow()
        
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'level': self.level,
            'title': self.title,
            'message': self.message,
            'status': self.status,
            'createdAt': self.created_at.isoformat(),
            'handledAt': self.handled_at.isoformat() if self.handled_at else None
        }
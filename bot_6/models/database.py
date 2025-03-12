from typing import Dict, List, Optional
import aioredis
import asyncpg
from datetime import datetime
from decimal import Decimal
import json

class Database:
    def __init__(self):
        self.pg_pool = None  # PostgreSQL连接池
        self.redis = None    # Redis连接
        self.settings = None # 数据库设置
        
    async def connect(self):
        """初始化数据库连接"""
        try:
            # 加载配置
            self.settings = await self.load_settings()
            
            # 连接PostgreSQL
            self.pg_pool = await asyncpg.create_pool(
                host=self.settings['database']['host'],
                port=self.settings['database']['port'],
                user=self.settings['database']['username'],
                password=self.settings['database']['password'],
                database=self.settings['database']['name']
            )
            
            # 连接Redis
            self.redis = await aioredis.create_redis_pool(
                f"redis://{self.settings['redis']['host']}:{self.settings['redis']['port']}"
            )
            
            # 初始化表结构
            await self._init_tables()
            
        except Exception as e:
            raise Exception(f"数据库连接失败: {e}")
            
    async def disconnect(self):
        """关闭数据库连接"""
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()
            
    async def _init_tables(self):
        """初始化数据库表结构"""
        async with self.pg_pool.acquire() as conn:
            # 创建策略表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    config JSONB NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            
            # 创建持仓表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id VARCHAR(36) PRIMARY KEY,
                    strategy_id VARCHAR(36) REFERENCES strategies(id),
                    symbol VARCHAR(20) NOT NULL,
                    direction VARCHAR(10) NOT NULL,
                    amount DECIMAL NOT NULL,
                    entry_price DECIMAL NOT NULL,
                    current_price DECIMAL NOT NULL,
                    unrealized_pnl DECIMAL NOT NULL,
                    realized_pnl DECIMAL NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            
            # 创建交易记录表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id VARCHAR(36) PRIMARY KEY,
                    position_id VARCHAR(36) REFERENCES positions(id),
                    exchange VARCHAR(50) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    price DECIMAL NOT NULL,
                    amount DECIMAL NOT NULL,
                    fee DECIMAL NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            
            # 创建风控指标表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS risk_metrics (
                    id SERIAL PRIMARY KEY,
                    overall_score DECIMAL NOT NULL,
                    risk_level VARCHAR(20) NOT NULL,
                    leverage DECIMAL NOT NULL,
                    concentration DECIMAL NOT NULL,
                    volatility DECIMAL NOT NULL,
                    margin_usage DECIMAL NOT NULL,
                    daily_loss DECIMAL NOT NULL,
                    drawdown DECIMAL NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            
            # 创建风控警报表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS risk_alerts (
                    id VARCHAR(36) PRIMARY KEY,
                    level VARCHAR(20) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    handled_at TIMESTAMP
                )
            """)
            
    async def get_account_stats(self) -> Dict:
        """获取账户统计数据"""
        try:
            async with self.pg_pool.acquire() as conn:
                # 获取总资产
                total_value = await conn.fetchval("""
                    SELECT SUM(amount * current_price)
                    FROM positions
                    WHERE status = 'open'
                """)
                
                # 获取当日盈亏
                day_pnl = await conn.fetchval("""
                    SELECT SUM(unrealized_pnl + realized_pnl)
                    FROM positions
                    WHERE DATE(created_at) = CURRENT_DATE
                """)
                
                # 获取持仓数量
                total_positions = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM positions
                    WHERE status = 'open'
                """)
                
                # 获取可用保证金
                available_margin = await conn.fetchval("""
                    SELECT value::decimal
                    FROM settings
                    WHERE key = 'available_margin'
                """)
                
                # 计算风险水平
                risk_metrics = await self.get_risk_metrics()
                
                return {
                    'totalValue': float(total_value or 0),
                    'dayPnL': float(day_pnl or 0),
                    'dayChange': float((day_pnl or 0) / (total_value or 1)),
                    'totalPositions': total_positions,
                    'availableMargin': float(available_margin or 0),
                    'riskLevel': risk_metrics['overall']['level'],
                    'leverage': float(risk_metrics['position']['leverage'])
                }
                
        except Exception as e:
            raise Exception(f"获取账户统计失败: {e}")
            
    async def get_position_stats(self) -> Dict:
        """获取持仓统计数据"""
        try:
            async with self.pg_pool.acquire() as conn:
                # 获取持仓总值
                total_value = await conn.fetchval("""
                    SELECT SUM(amount * current_price)
                    FROM positions
                    WHERE status = 'open'
                """)
                
                # 获取未实现盈亏
                unrealized_pnl = await conn.fetchval("""
                    SELECT SUM(unrealized_pnl)
                    FROM positions
                    WHERE status = 'open'
                """)
                
                # 计算回报率
                if total_value:
                    roi = unrealized_pnl / total_value
                else:
                    roi = Decimal('0')
                    
                # 获取风险指标
                risk_metrics = await self.get_risk_metrics()
                
                return {
                    'totalValue': float(total_value or 0),
                    'positionCount': await conn.fetchval(
                        "SELECT COUNT(*) FROM positions WHERE status = 'open'"
                    ),
                    'unrealizedPnL': float(unrealized_pnl or 0),
                    'unrealizedPnLPercent': float(roi),
                    'marginUsage': float(risk_metrics['capital']['marginUsage']),
                    'availableMargin': float(risk_metrics['capital']['availableMargin']),
                    'riskLevel': risk_metrics['overall']['level'],
                    'leverage': float(risk_metrics['position']['leverage'])
                }
                
        except Exception as e:
            raise Exception(f"获取持仓统计失败: {e}")
            
    async def get_equity_history(self, days: int = 30) -> List[Dict]:
        """获取权益历史数据"""
        try:
            async with self.pg_pool.acquire() as conn:
                records = await conn.fetch("""
                    SELECT date_trunc('day', created_at) as date,
                           SUM(realized_pnl) as daily_pnl,
                           AVG(amount * current_price) as equity
                    FROM positions
                    WHERE created_at >= CURRENT_DATE - $1
                    GROUP BY date_trunc('day', created_at)
                    ORDER BY date
                """, days)
                
                return [
                    {
                        'date': record['date'].isoformat(),
                        'pnl': float(record['daily_pnl']),
                        'equity': float(record['equity'])
                    }
                    for record in records
                ]
                
        except Exception as e:
            raise Exception(f"获取权益历史失败: {e}")
            
    async def get_strategy_pnl(self) -> List[Dict]:
        """获取策略盈亏分布"""
        try:
            async with self.pg_pool.acquire() as conn:
                records = await conn.fetch("""
                    SELECT s.name,
                           SUM(p.unrealized_pnl + p.realized_pnl) as total_pnl
                    FROM strategies s
                    LEFT JOIN positions p ON p.strategy_id = s.id
                    GROUP BY s.id, s.name
                    ORDER BY total_pnl DESC
                """)
                
                return [
                    {
                        'name': record['name'],
                        'pnl': float(record['total_pnl'] or 0)
                    }
                    for record in records
                ]
                
        except Exception as e:
            raise Exception(f"获取策略盈亏失败: {e}")
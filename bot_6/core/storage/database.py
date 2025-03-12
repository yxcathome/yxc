from typing import Dict, List, Optional, Any
import asyncio
import aiosqlite
import json
from datetime import datetime
import pandas as pd
from utils.logger import setup_logger

class DatabaseManager:
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        self.logger = setup_logger("database")
        self._conn = None
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """初始化数据库"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 创建交易记录表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        trade_id TEXT PRIMARY KEY,
                        strategy TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        entry_time TIMESTAMP NOT NULL,
                        exit_time TIMESTAMP,
                        side TEXT NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL,
                        amount REAL NOT NULL,
                        pnl REAL,
                        status TEXT NOT NULL,
                        metadata TEXT
                    )
                """)
                
                # 创建订单记录表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY,
                        trade_id TEXT,
                        exchange TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        order_type TEXT NOT NULL,
                        side TEXT NOT NULL,
                        amount REAL NOT NULL,
                        price REAL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
                    )
                """)
                
                # 创建性能指标表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        timestamp TIMESTAMP PRIMARY KEY,
                        strategy TEXT NOT NULL,
                        total_trades INTEGER NOT NULL,
                        winning_trades INTEGER NOT NULL,
                        total_pnl REAL NOT NULL,
                        win_rate REAL NOT NULL,
                        sharpe_ratio REAL,
                        max_drawdown REAL,
                        metadata TEXT
                    )
                """)
                
                # 创建权益曲线表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS equity_curve (
                        timestamp TIMESTAMP NOT NULL,
                        strategy TEXT NOT NULL,
                        balance REAL NOT NULL,
                        PRIMARY KEY (timestamp, strategy)
                    )
                """)
                
                await db.commit()
                self.logger.info("数据库初始化完成")
                
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise
            
    async def save_trade(self, trade_data: Dict) -> bool:
        """保存交易记录"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO trades (
                        trade_id, strategy, symbol, entry_time, side,
                        entry_price, amount, status, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_data['trade_id'],
                    trade_data['strategy'],
                    trade_data['symbol'],
                    trade_data['entry_time'].isoformat(),
                    trade_data['side'],
                    float(trade_data['entry_price']),
                    float(trade_data['amount']),
                    trade_data['status'],
                    json.dumps(trade_data.get('metadata', {}))
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"保存交易记录失败: {e}")
            return False
            
    async def update_trade(self, trade_id: str, update_data: Dict) -> bool:
        """更新交易记录"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                update_fields = []
                params = []
                
                for key, value in update_data.items():
                    if key in ['exit_price', 'exit_time', 'pnl', 'status']:
                        update_fields.append(f"{key} = ?")
                        params.append(
                            value.isoformat() if isinstance(value, datetime) else float(value)
                        )
                        
                if update_fields:
                    params.append(trade_id)
                    query = f"""
                        UPDATE trades 
                        SET {', '.join(update_fields)}
                        WHERE trade_id = ?
                    """
                    
                    await db.execute(query, params)
                    await db.commit()
                    return True
                    
                return False
                
        except Exception as e:
            self.logger.error(f"更新交易记录失败: {e}")
            return False
            
    async def save_order(self, order_data: Dict) -> bool:
        """保存订单记录"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO orders (
                        order_id, trade_id, exchange, symbol, order_type,
                        side, amount, price, status, created_at, updated_at,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_data['order_id'],
                    order_data.get('trade_id'),
                    order_data['exchange'],
                    order_data['symbol'],
                    order_data['order_type'],
                    order_data['side'],
                    float(order_data['amount']),
                    float(order_data['price']) if order_data.get('price') else None,
                    order_data['status'],
                    order_data['created_at'].isoformat(),
                    order_data['updated_at'].isoformat(),
                    json.dumps(order_data.get('metadata', {}))
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"保存订单记录失败: {e}")
            return False
            
    async def save_performance_metrics(self, metrics_data: Dict) -> bool:
        """保存性能指标"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO performance_metrics (
                        timestamp, strategy, total_trades, winning_trades,
                        total_pnl, win_rate, sharpe_ratio, max_drawdown,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metrics_data['timestamp'].isoformat(),
                    metrics_data['strategy'],
                    metrics_data['total_trades'],
                    metrics_data['winning_trades'],
                    float(metrics_data['total_pnl']),
                    float(metrics_data['win_rate']),
                    float(metrics_data['sharpe_ratio']) if metrics_data.get('sharpe_ratio') else None,
                    float(metrics_data['max_drawdown']) if metrics_data.get('max_drawdown') else None,
                    json.dumps(metrics_data.get('metadata', {}))
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"保存性能指标失败: {e}")
            return False
            
    async def get_trades(self, 
                        strategy: Optional[str] = None,
                        symbol: Optional[str] = None,
                        start_time: Optional[datetime] = None,
                        end_time: Optional[datetime] = None,
                        status: Optional[str] = None) -> List[Dict]:
        """查询交易记录"""
        try:
            conditions = ["1=1"]
            params = []
            
            if strategy:
                conditions.append("strategy = ?")
                params.append(strategy)
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if start_time:
                conditions.append("entry_time >= ?")
                params.append(start_time.isoformat())
            if end_time:
                conditions.append("entry_time <= ?")
                params.append(end_time.isoformat())
            if status:
                conditions.append("status = ?")
                params.append(status)
                
            query = f"""
                SELECT * FROM trades
                WHERE {' AND '.join(conditions)}
                ORDER BY entry_time DESC
            """
            
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                    
        except Exception as e:
            self.logger.error(f"查询交易记录失败: {e}")
            return []
            
    async def get_performance_history(self,
                                    strategy: str,
                                    start_time: Optional[datetime] = None,
                                    end_time: Optional[datetime] = None) -> pd.DataFrame:
        """获取性能历史数据"""
        try:
            conditions = ["strategy = ?"]
            params = [strategy]
            
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time.isoformat())
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time.isoformat())
                
            query = f"""
                SELECT * FROM performance_metrics
                WHERE {' AND '.join(conditions)}
                ORDER BY timestamp ASC
            """
            
            async with aiosqlite.connect(self.db_path) as db:
                df = pd.read_sql_query(query, db, params=params)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
                
        except Exception as e:
            self.logger.error(f"获取性能历史数据失败: {e}")
            return pd.DataFrame()
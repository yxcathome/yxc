from typing import Dict, List, Optional, Any
import asyncio
import motor.motor_asyncio
from datetime import datetime
import json
from decimal import Decimal
from bson import Decimal128
from utils.logger import setup_logger

class Database:
    def __init__(self, config: Dict):
        self.logger = setup_logger("database")
        self.client = motor.motor_asyncio.AsyncIOMotorClient(config['mongodb_uri'])
        self.db = self.client[config['database_name']]
        
        # 集合定义
        self.trades = self.db.trades
        self.orders = self.db.orders
        self.positions = self.db.positions
        self.metrics = self.db.metrics
        self.market_data = self.db.market_data
        
    async def initialize(self):
        """初始化数据库"""
        try:
            # 创建索引
            await self.trades.create_index([("timestamp", -1)])
            await self.trades.create_index([("strategy", 1)])
            await self.orders.create_index([("timestamp", -1)])
            await self.positions.create_index([("open_time", -1)])
            await self.market_data.create_index([
                ("symbol", 1),
                ("exchange", 1),
                ("timestamp", -1)
            ])
            
            self.logger.info("数据库初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            return False
            
    async def save_trade(self, trade_data: Dict) -> bool:
        """保存交易记录"""
        try:
            # 转换Decimal为Decimal128
            trade_data = self._convert_decimal(trade_data)
            trade_data['timestamp'] = datetime.utcnow()
            
            await self.trades.insert_one(trade_data)
            return True
            
        except Exception as e:
            self.logger.error(f"保存交易记录失败: {e}")
            return False
            
    async def save_order(self, order_data: Dict) -> bool:
        """保存订单记录"""
        try:
            order_data = self._convert_decimal(order_data)
            order_data['timestamp'] = datetime.utcnow()
            
            await self.orders.insert_one(order_data)
            return True
            
        except Exception as e:
            self.logger.error(f"保存订单记录失败: {e}")
            return False
            
    async def save_position(self, position_data: Dict) -> bool:
        """保存持仓记录"""
        try:
            position_data = self._convert_decimal(position_data)
            
            await self.positions.insert_one(position_data)
            return True
            
        except Exception as e:
            self.logger ▋
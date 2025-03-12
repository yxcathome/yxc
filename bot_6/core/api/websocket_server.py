from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
from datetime import datetime
from utils.logger import setup_logger

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            'trades': set(),
            'orders': set(),
            'positions': set(),
            'system': set()
        }
        self.logger = setup_logger("websocket_manager")
        
    async def connect(self, websocket: WebSocket, channel: str):
        """建立WebSocket连接"""
        try:
            await websocket.accept()
            if channel in self.active_connections:
                self.active_connections[channel].add(websocket)
                self.logger.info(f"WebSocket连接建立: {channel}")
            else:
                await websocket.close(code=4000, reason="Invalid channel")
                
        except Exception as e:
            self.logger.error(f"WebSocket连接失败: {e}")
            
    async def disconnect(self, websocket: WebSocket, channel: str):
        """断开WebSocket连接"""
        try:
            self.active_connections[channel].remove(websocket)
            self.logger.info(f"WebSocket连接断开: {channel}")
            
        except Exception as e:
            self.logger.error(f"WebSocket断开连接失败: {e}")
            
    async def broadcast(self, channel: str, message: Dict):
        """广播消息"""
        if channel not in self.active_connections:
            return
            
        disconnected = set()
        message['timestamp'] = datetime.utcnow().isoformat()
        
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception as e:
                self.logger.error(f"广播消息失败: {e}")
                disconnected.add(connection)
                
        # 清理断开的连接
        for connection in disconnected:
            await self.disconnect(connection, channel)
            
class WebSocketServer:
    def __init__(self, app, trading_engine):
        self.app = app
        self.trading_engine = trading_engine
        self.manager = WebSocketManager()
        self.logger = setup_logger("websocket_server")
        
        # 注册WebSocket路由
        self._register_routes()
        
        # 启动状态广播任务
        asyncio.create_task(self._broadcast_system_status())
        
    def _register_routes(self):
        """注册WebSocket路由"""
        
        @self.app.websocket("/ws/{channel}")
        async def websocket_endpoint(websocket: WebSocket, channel: str):
            await self.manager.connect(websocket, channel)
            
            try:
                while True:
                    # 保持连接活跃
                    await websocket.receive_text()
                    
            except WebSocketDisconnect:
                await self.manager.disconnect(websocket, channel)
                
    async def _broadcast_system_status(self):
        """定期广播系统状态"""
        while True:
            try:
                status = {
                    "type": "system_status",
                    "data": {
                        "active_strategies": len(self.trading_engine.active_strategies),
                        "total_positions": len(self.trading_engine.positions),
                        "system_time": datetime.utcnow().isoformat()
                    }
                }
                
                await self.manager.broadcast('system', status)
                await asyncio.sleep(5)  # 每5秒更新一次
                
            except Exception as e:
                self.logger.error(f"广播系统状态失败: {e}")
                await asyncio.sleep(5)
                
    async def broadcast_trade(self, trade_data: Dict):
        """广播交易信息"""
        await self.manager.broadcast('trades', {
            "type": "trade",
            "data": trade_data
        })
        
    async def broadcast_order(self, order_data: Dict):
        """广播订单信息"""
        await self.manager.broadcast('orders', {
            "type": "order",
            "data": order_data
        })
        
    async def broadcast_position(self, position_data: Dict):
        """广播持仓信息"""
        await self.manager.broadcast('positions', {
            "type": "position",
            "data": position_data
        })
from typing import Dict, Optional, Any
from fastapi import FastAPI, HTTPException, Depends, Security, WebSocket
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
from pydantic import BaseModel
import asyncio
from utils.logger import setup_logger

class OrderRequest(BaseModel):
    strategy_id: str
    symbol: str
    side: str
    order_type: str
    amount: float
    price: Optional[float] = None

class SignalRequest(BaseModel):
    strategy_id: str
    symbol: str
    signal_type: str
    direction: str
    metadata: Optional[Dict] = None

class TradingServer:
    def __init__(self, trading_engine, config_manager):
        self.trading_engine = trading_engine
        self.config_manager = config_manager
        self.logger = setup_logger("trading_server")
        
        # 创建FastAPI应用
        self.app = FastAPI(
            title="Trading System API",
            description="Algorithmic Trading System REST API",
            version="1.0.0"
        )
        
        # API密钥验证
        self.api_key_header = APIKeyHeader(name="X-API-Key")
        
        # 设置CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # 注册路由
        self._register_routes()
        
    def _register_routes(self):
        """注册API路由"""
        
        @self.app.get("/api/v1/system/status")
        async def get_system_status(
            api_key: str = Security(self.api_key_header)
        ):
            """获取系统状态"""
            try:
                await self._validate_api_key(api_key)
                
                return {
                    "status": "running",
                    "timestamp": datetime.utcnow().isoformat(),
                    "uptime": (datetime.utcnow() - self.trading_engine.start_time).total_seconds(),
                    "active_strategies": len(self.trading_engine.active_strategies),
                    "total_positions": len(self.trading_engine.positions)
                }
                
            except Exception as e:
                self.logger.error(f"获取系统状态失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.post("/api/v1/orders")
        async def create_order(
            order_request: OrderRequest,
            api_key: str = Security(self.api_key_header)
        ):
            """创建订单"""
            try:
                await self._validate_api_key(api_key)
                
                order = await self.trading_engine.create_order(
                    strategy_id=order_request.strategy_id,
                    symbol=order_request.symbol,
                    side=order_request.side,
                    order_type=order_request.order_type,
                    amount=order_request.amount,
                    price=order_request.price
                )
                
                if order:
                    return {"status": "success", "order": order}
                else:
                    raise HTTPException(status_code=400, detail="创建订单失败")
                    
            except Exception as e:
                self.logger.error(f"创建订单失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.get("/api/v1/orders/{order_id}")
        async def get_order(
            order_id: str,
            api_key: str = Security(self.api_key_header)
        ):
            """获取订单信息"""
            try:
                await self._validate_api_key(api_key)
                
                order = await self.trading_engine.get_order(order_id)
                if order:
                    return order
                raise HTTPException(status_code=404, detail="订单不存在")
                
            except Exception as e:
                self.logger.error(f"获取订单信息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.delete("/api/v1/orders/{order_id}")
        async def cancel_order(
            order_id: str,
            api_key: str = Security(self.api_key_header)
        ):
            """取消订单"""
            try:
                await self._validate_api_key(api_key)
                
                success = await self.trading_engine.cancel_order(order_id)
                if success:
                    return {"status": "success", "message": "订单已取消"}
                raise HTTPException(status_code=400, detail="取消订单失败")
                
            except Exception as e:
                self.logger.error(f"取消订单失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.get("/api/v1/positions")
        async def get_positions(
            strategy_id: Optional[str] = None,
            symbol: Optional[str] = None,
            api_key: str = Security(self.api_key_header)
        ):
            """获取持仓信息"""
            try:
                await self._validate_api_key(api_key)
                
                positions = await self.trading_engine.get_positions(
                    strategy_id=strategy_id,
                    symbol=symbol
                )
                return positions
                
            except Exception as e:
                self.logger.error(f"获取持仓信息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.post("/api/v1/signals")
        async def process_signal(
            signal_request: SignalRequest,
            api_key: str = Security(self.api_key_header)
        ):
            """处理交易信号"""
            try:
                await self._validate_api_key(api_key)
                
                result = await self.trading_engine.process_signal(
                    strategy_id=signal_request.strategy_id,
                    symbol=signal_request.symbol,
                    signal_type=signal_request.signal_type,
                    direction=signal_request.direction,
                    metadata=signal_request.metadata
                )
                
                if result:
                    return {"status": "success", "result": result}
                raise HTTPException(status_code=400, detail="信号处理失败")
                
            except Exception as e:
                self.logger.error(f"处理交易信号失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.get("/api/v1/performance")
        async def get_performance(
            strategy_id: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            api_key: str = Security(self.api_key_header)
        ):
            """获取性能指标"""
            try:
                await self._validate_api_key(api_key)
                
                performance = await self.trading_engine.get_performance_metrics(
                    strategy_id=strategy_id,
                    start_time=datetime.fromisoformat(start_time) if start_time else None,
                    end_time=datetime.fromisoformat(end_time) if end_time else None
                )
                return performance
                
            except Exception as e:
                self.logger.error(f"获取性能指标失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
                
    async def _validate_api_key(self, api_key: str):
        """验证API密钥"""
        valid_keys = await self.config_manager.get_config('api', 'valid_keys')
        if not valid_keys or api_key not in valid_keys:
            raise HTTPException(
                status_code=401,
                detail="Invalid API Key"
            )
            
    async def start(self):
        """启动API服务器"""
        config = await self.config_manager.get_config('api')
        if not config:
            self.logger.error("无法获取API配置")
            return
            
        host = config.get('host', '0.0.0.0')
        port = config.get('port', 8000)
        
        uvicorn.run(
            self.app,
            host=host,
            port=port,
            log_level="info"
        )
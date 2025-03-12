from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
from decimal import Decimal
import asyncio
from datetime import datetime

from models.database import Database
from models.strategy import Strategy
from models.position import Position
from models.risk import RiskMetrics
from models.settings import Settings
from utils.logger import setup_logger

app = FastAPI(title="量化交易系统API")
logger = setup_logger("api")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 数据库连接
async def get_db():
    db = Database()
    try:
        await db.connect()
        yield db
    finally:
        await db.disconnect()

# 仪表盘接口
@app.get("/api/dashboard")
async def get_dashboard_data(db: Database = Depends(get_db)):
    try:
        # 获取账户统计数据
        account_stats = await db.get_account_stats()
        
        # 获取图表数据
        equity_history = await db.get_equity_history()
        strategy_pnl = await db.get_strategy_pnl()
        
        # 获取活跃策略
        active_strategies = await db.get_active_strategies()
        
        # 获取最近交易
        recent_trades = await db.get_recent_trades(limit=10)
        
        return {
            "accountStats": account_stats,
            "charts": {
                "equity": equity_history,
                "strategyPnL": strategy_pnl
            },
            "activeStrategies": active_strategies,
            "recentTrades": recent_trades
        }
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取仪表盘数据失败")

# 策略管理接口
@app.get("/api/strategies")
async def get_strategies(db: Database = Depends(get_db)):
    try:
        strategies = await db.get_strategies()
        return {"strategies": strategies}
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取策略列表失败")

@app.post("/api/strategies")
async def create_strategy(strategy_data: dict, db: Database = Depends(get_db)):
    try:
        strategy = Strategy(**strategy_data)
        await db.create_strategy(strategy)
        return {"message": "策略创建成功", "strategy": strategy}
    except Exception as e:
        logger.error(f"创建策略失败: {e}")
        raise HTTPException(status_code=500, detail="创建策略失败")

@app.post("/api/strategies/{strategy_id}/{action}")
async def control_strategy(strategy_id: str, action: str, db: Database = Depends(get_db)):
    try:
        if action not in ["start", "pause", "stop"]:
            raise HTTPException(status_code=400, detail="无效的操作")
            
        strategy = await db.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")
            
        if action == "start":
            await strategy.start()
        elif action == "pause":
            await strategy.pause()
        else:
            await strategy.stop()
            
        await db.update_strategy(strategy)
        return {"message": f"策略{action}成功"}
    except Exception as e:
        logger.error(f"控制策略失败: {e}")
        raise HTTPException(status_code=500, detail="控制策略失败")

# 持仓管理接口
@app.get("/api/positions")
async def get_positions(db: Database = Depends(get_db)):
    try:
        positions = await db.get_positions()
        stats = await db.get_position_stats()
        return {
            "positions": positions,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取持仓数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取持仓数据失败")

@app.post("/api/positions/{position_id}/close")
async def close_position(position_id: str, db: Database = Depends(get_db)):
    try:
        position = await db.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="持仓不存在")
            
        await position.close()
        await db.update_position(position)
        return {"message": "平仓成功"}
    except Exception as e:
        logger.error(f"平仓失败: {e}")
        raise HTTPException(status_code=500, detail="平仓失败")

# 风控监控接口
@app.get("/api/risk/metrics")
async def get_risk_metrics(db: Database = Depends(get_db)):
    try:
        metrics = await db.get_risk_metrics()
        alerts = await db.get_risk_alerts()
        return {
            "metrics": metrics,
            "alerts": alerts
        }
    except Exception as e:
        logger.error(f"获取风控数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取风控数据失败")

@app.post("/api/risk/alerts/{alert_id}/handle")
async def handle_risk_alert(alert_id: str, db: Database = Depends(get_db)):
    try:
        alert = await db.get_risk_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="警报不存在")
            
        await alert.handle()
        await db.update_risk_alert(alert)
        return {"message": "警报处理成功"}
    except Exception as e:
        logger.error(f"处理风控警报失败: {e}")
        raise HTTPException(status_code=500, detail="处理风控警报失败")

@app.post("/api/risk/settings")
async def update_risk_settings(settings: dict, db: Database = Depends(get_db)):
    try:
        await db.update_risk_settings(settings)
        return {"message": "风控设置更新成功"}
    except Exception as e:
        logger.error(f"更新风控设置失败: {e}")
        raise HTTPException(status_code=500, detail="更新风控设置失败")

# 系统设置接口
@app.get("/api/settings")
async def get_settings(db: Database = Depends(get_db)):
    try:
        settings = await db.get_settings()
        return settings
    except Exception as e:
        logger.error(f"获取系统设置失败: {e}")
        raise HTTPException(status_code=500, detail="获取系统设置失败")

@app.post("/api/settings")
async def update_settings(settings: dict, db: Database = Depends(get_db)):
    try:
        await db.update_settings(settings)
        return {"message": "设置更新成功"}
    except Exception as e:
        logger.error(f"更新系统设置失败: {e}")
        raise HTTPException(status_code=500, detail="更新系统设置失败")

@app.post("/api/exchanges/{exchange_id}/test")
async def test_exchange_connection(exchange_id: str, credentials: dict):
    try:
        # 测试交易所连接
        from exchanges.exchange_manager import ExchangeManager
        exchange_manager = ExchangeManager()
        status = await exchange_manager.test_connection(
            exchange_id,
            credentials['apiKey'],
            credentials['secretKey']
        )
        return {"status": status}
    except Exception as e:
        logger.error(f"测试交易所连接失败: {e}")
        raise HTTPException(status_code=500, detail="测试交易所连接失败")

# 主页路由
@app.get("/")
async def read_root():
    return {"message": "量化交易系统API服务正在运行"}

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
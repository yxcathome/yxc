from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List
import logging
from dotenv import load_dotenv

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/list")
async def list_strategies() -> List[Dict]:
    """获取所有策略列表"""
    try:
        from main import bot
        strategies = []
        for name, strategy in bot.strategies.items():
            strategies.append({
                "name": name,
                "is_active": strategy.is_active,
                "description": strategy.__doc__ or "No description available",
                "config": strategy.config
            })
        return strategies
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{strategy_name}/toggle")
async def toggle_strategy(strategy_name: str) -> Dict:
    """启用/禁用策略"""
    try:
        from main import bot
        if strategy_name not in bot.strategies:
            raise HTTPException(status_code=404, detail="Strategy not found")
            
        strategy = bot.strategies[strategy_name]
        strategy.is_active = not strategy.is_active
        
        return {
            "name": strategy_name,
            "is_active": strategy.is_active,
            "message": f"Strategy {strategy_name} {'enabled' if strategy.is_active else 'disabled'}"
        }
    except Exception as e:
        logger.error(f"切换策略状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{strategy_name}/status")
async def get_strategy_status(strategy_name: str) -> Dict:
    """获取策略状态"""
    try:
        from main import bot
        if strategy_name not in bot.strategies:
            raise HTTPException(status_code=404, detail="Strategy not found")
            
        strategy = bot.strategies[strategy_name]
        return {
            "name": strategy_name,
            "is_active": strategy.is_active,
            "positions": strategy.positions if hasattr(strategy, 'positions') else {},
            "last_signal": getattr(strategy, 'last_signal', None),
            "performance": {
                "total_trades": getattr(strategy, 'total_trades', 0),
                "successful_trades": getattr(strategy, 'successful_trades', 0),
                "total_profit": str(getattr(strategy, 'total_profit', 0))
            }
        }
    except Exception as e:
        logger.error(f"获取策略状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
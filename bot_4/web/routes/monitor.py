from fastapi import APIRouter, HTTPException
from typing import Dict, List
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/overview")
async def get_overview() -> Dict:
    """获取总览数据"""
    try:
        from main import bot
        
        current_time = datetime.now()
        start_time = bot.stats['start_time']
        runtime = current_time - start_time
        
        return {
            "status": "running" if bot.is_running else "stopped",
            "uptime": str(runtime),
            "total_equity": {
                "okx": str(bot.equity['okx']),
                "binance": str(bot.equity['binance'])
            },
            "daily_pnl": str(bot.risk_manager.daily_pnl),
            "max_drawdown": str(bot.risk_manager.max_drawdown),
            "active_positions": len(bot.positions),
            "total_trades_today": len(bot.risk_manager.trade_records)
        }
    except Exception as e:
        logger.error(f"获取总览数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/positions")
async def get_positions() -> List[Dict]:
    """获取当前持仓"""
    try:
        from main import bot
        positions = []
        
        # 获取OKX持仓
        okx_positions = await bot.okx.fetch_positions() or []
        for pos in okx_positions:
            if float(pos['contracts']) > 0:
                positions.append({
                    "exchange": "okx",
                    "symbol": pos['symbol'],
                    "side": pos['side'],
                    "amount": str(pos['contracts']),
                    "entry_price": str(pos['entryPrice']),
                    "current_price": str(pos['markPrice']),
                    "pnl": str(pos['unrealizedPnl']),
                    "timestamp": pos['timestamp']
                })
                
        # 获取Binance持仓
        binance_positions = await bot.binance.fetch_positions() or []
        for pos in binance_positions:
            if float(pos['contracts']) > 0:
                positions.append({
                    "exchange": "binance",
                    "symbol": pos['symbol'],
                    "side": pos['side'],
                    "amount": str(pos['contracts']),
                    "entry_price": str(pos['entryPrice']),
                    "current_price": str(pos['markPrice']),
                    "pnl": str(pos['unrealizedPnl']),
                    "timestamp": pos['timestamp']
                })
                
        return positions
    except Exception as e:
        logger.error(f"获取持仓数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades")
async def get_trades(limit: int = 50) -> List[Dict]:
    """获取最近交易记录"""
    try:
        from main import bot
        trades = bot.risk_manager.trade_records[-limit:]
        return [{
            "time": trade['time'].isoformat(),
            "symbol": trade['symbol'],
            "profit": str(trade['profit'])
        } for trade in trades]
    except Exception as e:
        logger.error(f"获取交易记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance")
async def get_performance() -> Dict:
    """获取性能统计"""
    try:
        from main import bot
        return {
            "total_trades": bot.stats['total_checks'],
            "successful_trades": bot.stats['successful_trades'],
            "failed_trades": bot.stats['failed_trades'],
            "total_profit": str(bot.stats['total_profit']),
            "max_drawdown": str(bot.risk_manager.max_drawdown),
            "win_rate": (bot.stats['successful_trades'] / bot.stats['total_checks'] * 100 
                        if bot.stats['total_checks'] > 0 else 0)
        }
    except Exception as e:
        logger.error(f"获取性能统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
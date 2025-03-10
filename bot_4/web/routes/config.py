from fastapi import APIRouter, HTTPException, Body
from typing import Dict
import logging
from decimal import Decimal
from copy import deepcopy

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def get_config() -> Dict:
    """获取当前配置"""
    try:
        from main import bot
        # 创建配置副本，确保decimal值可以被JSON序列化
        config = deepcopy(bot.config)
        _convert_decimal_to_str(config)
        return config
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update")
async def update_config(config_update: Dict = Body(...)) -> Dict:
    """更新配置"""
    try:
        from main import bot
        # 验证配置
        validated_config = _validate_config(config_update)
        
        # 更新主配置
        bot.config.update(validated_config)
        
        # 更新各个策略的配置
        for strategy in bot.strategies.values():
            strategy.update_config(validated_config)
            
        # 更新风控配置
        bot.risk_manager.config.update(validated_config)
        
        return {"status": "success", "message": "配置更新成功"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_config() -> Dict:
    """重置配置为默认值"""
    try:
        from main import bot
        from config.settings import CONFIG as default_config
        
        # 重置为默认配置
        bot.config = deepcopy(default_config)
        
        # 更新各个策略的配置
        for strategy in bot.strategies.values():
            strategy.update_config(default_config)
            
        # 更新风控配置
        bot.risk_manager.config.update(default_config)
        
        return {"status": "success", "message": "配置已重置为默认值"}
    except Exception as e:
        logger.error(f"重置配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _validate_config(config: Dict) -> Dict:
    """验证配置参数"""
    try:
        validated = {}
        
        # 验证交易参数
        if 'initial_trade_usdt' in config:
            value = Decimal(str(config['initial_trade_usdt']))
            if value <= 0:
                raise ValueError("初始交易金额必须大于0")
            validated['initial_trade_usdt'] = value
            
        # 验证风控参数
        if 'risk_control' in config:
            risk = config['risk_control']
            if 'max_position_size' in risk:
                value = Decimal(str(risk['max_position_size']))
                if not 0 < value <= 1:
                    raise ValueError("最大持仓比例必须在0-1之间")
                validated.setdefault('risk_control', {})['max_position_size'] = value
                
        # 验证策略参数
        if 'enabled_strategies' in config:
            validated['enabled_strategies'] = {
                k: bool(v) for k, v in config['enabled_strategies'].items()
            }
            
        return validated
    except Exception as e:
        raise ValueError(f"配置验证失败: {e}")

def _convert_decimal_to_str(config: Dict):
    """将配置中的Decimal转换为字符串"""
    for key, value in config.items():
        if isinstance(value, Decimal):
            config[key] = str(value)
        elif isinstance(value, dict):
            _convert_decimal_to_str(value)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, (Dict, list)):
                    _convert_decimal_to_str(item)
                elif isinstance(item, Decimal):
                    value[i] = str(item)
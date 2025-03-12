from typing import Dict, List
from datetime import datetime
import json
import os
import yaml

class Config:
    # 系统标识
    SYSTEM_ID = "PROD_CRYPTO_V1"
    VERSION = "2.0.0"
    
    # 交易所配置
    PRIMARY_EXCHANGE = "binance"
    EXCHANGES = {
        "binance": {
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET_KEY"),
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
                "recvWindow": 60000,
                "defaultMarginMode": "isolated"
            }
        }
    }
    
    # 交易参数
    TRADING_PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
    BASE_CURRENCY = "USDT"
    BASE_TIMEFRAME = "5m"
    STRATEGY_TIMEFRAMES = ["5m", "15m", "1h", "4h"]
    
    # 资金管理
    INITIAL_BALANCE = 10000
    MAX_POSITION_SIZE = 0.1  # 单个仓位最大资金比例
    MAX_TOTAL_POSITIONS = 0.3  # 总仓位最大资金比例
    LEVERAGE = 2  # 最大杠杆倍数
    
    # 风控参数
    RISK_LIMITS = {
        "max_drawdown": 0.15,
        "daily_loss_limit": 0.05,
        "position_loss_limit": 0.02,
        "max_positions": 5,
        "min_liquidity": 100000,
        "max_slippage": 0.002
    }
    
    # 执行参数
    EXECUTION_PARAMS = {
        "order_timeout": 30,
        "max_retries": 3,
        "retry_delay": 1,
        "min_order_value": 20
    }
    
    # 策略参数
    STRATEGY_PARAMS = {
        "mean_reversion": {
            "lookback_period": 20,
            "entry_threshold": 2.0,
            "exit_threshold": 0.5,
            "max_holding_time": 24  # hours
        },
        "ma_trend": {
            "fast_ma": 10,
            "slow_ma": 20,
            "trend_strength": 0.02,
            "min_volume_mult": 1.5
        },
        "breakout": {
            "breakout_period": 20,
            "volume_threshold": 2.0,
            "volatility_filter": 0.02
        },
        "arbitrage": {
            "min_spread": 0.003,
            "max_holding_time": 1,  # hours
            "min_profit_threshold": 0.002
        }
    }
    
    # 系统参数
    SYSTEM_PARAMS = {
        "market_update_interval": 5,  # seconds
        "strategy_interval": 10,      # seconds
        "risk_check_interval": 60,    # seconds
        "data_cleanup_days": 90,
        "log_level": "INFO",
        "max_memory_usage": 1024      # MB
    }
    
    # 数据库配置
    DATABASE_CONFIG = {
        "path": "data/trading.db",
        "backup_path": "data/backups/",
        "backup_interval": 24,        # hours
        "max_backup_count": 7
    }
    
    # 性能监控配置
    MONITORING = {
        "enabled": True,
        "metrics_interval": 60,       # seconds
        "alert_webhook": os.getenv("ALERT_WEBHOOK"),
        "performance_thresholds": {
            "execution_time": 1.0,    # seconds
            "slippage": 0.001,
            "success_rate": 0.95
        }
    }
    
    @classmethod
    def load_dynamic_config(cls):
        """加载动态配置"""
        try:
            with open('config/dynamic_config.yaml', 'r') as f:
                dynamic_config = yaml.safe_load(f)
                
            # 更新配置
            for key, value in dynamic_config.items():
                if hasattr(cls, key):
                    setattr(cls, key, value)
                    
        except Exception as e:
            print(f"Error loading dynamic config: {e}")
            
    @classmethod
    def save_dynamic_config(cls):
        """保存动态配置"""
        try:
            dynamic_config = {
                'TRADING_PAIRS': cls.TRADING_PAIRS,
                'RISK_LIMITS': cls.RISK_LIMITS,
                'STRATEGY_PARAMS': cls.STRATEGY_PARAMS,
                'SYSTEM_PARAMS': cls.SYSTEM_PARAMS
            }
            
            with open('config/dynamic_config.yaml', 'w') as f:
                yaml.dump(dynamic_config, f, default_flow_style=False)
                
        except Exception as e:
            print(f"Error saving dynamic config: {e}")
            
    @classmethod
    def validate_config(cls):
        """验证配置有效性"""
        try:
            # 验证交易对
            for pair in cls.TRADING_PAIRS:
                base, quote = pair.split('/')
                assert quote == cls.BASE_CURRENCY
                
            # 验证风控参数
            assert 0 < cls.RISK_LIMITS['max_drawdown'] < 1
            assert 0 < cls.RISK_LIMITS['daily_loss_limit'] < 1
            assert cls.RISK_LIMITS['max_positions'] > 0
            
            # 验证策略参数
            for strategy, params in cls.STRATEGY_PARAMS.items():
                assert all(value > 0 for value in params.values())
                
            # 验证系统参数
            assert cls.SYSTEM_PARAMS['market_update_interval'] > 0
            assert cls.SYSTEM_PARAMS['strategy_interval'] > 0
            assert cls.SYSTEM_PARAMS['risk_check_interval'] > 0
            
            return True
            
        except Exception as e:
            print(f"Config validation failed: {e}")
            return False
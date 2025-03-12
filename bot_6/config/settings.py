from decimal import Decimal
from typing import Dict, List
import os
from datetime import datetime

# 基础配置
BASE_CONFIG = {
    'total_balance': Decimal('40'),
    'exchange_allocation': {
        'okx': Decimal('20'),
        'binance': Decimal('20')
    },
    'risk_level': 'conservative',
    'log_level': 'INFO',
    'data_dir': os.path.join(os.path.dirname(__file__), '../data'),
    'db_url': 'sqlite:///data/trading.db'
}

# API配置
EXCHANGE_CONFIG = {
    'okx': {
        'api_key': 'your_okx_api_key',
        'secret_key': 'your_okx_secret_key',
        'password': 'your_okx_password',
        'test': False  # 实盘模式
    },
    'binance': {
        'api_key': 'your_binance_api_key',
        'secret_key': 'your_binance_secret_key',
        'test': False  # 实盘模式
    }
}

# 策略配置
STRATEGY_CONFIG = {
    'arbitrage': {
        'basic_arb': {
            'enabled': True,
            'weight': Decimal('0.3'),
            'min_spread': Decimal('0.001'),
            'max_waiting_time': 60,
            'min_volume': Decimal('10000')
        },
        'flash_arb': {
            'enabled': True,
            'weight': Decimal('0.2'),
            'trigger_pct': Decimal('0.005'),
            'max_holding_time': 30,
            'volume_threshold': Decimal('5000')
        },
        'funding_arb': {
            'enabled': True,
            'weight': Decimal('0.1'),
            'min_funding_diff': Decimal('0.0001'),
            'max_position_hold': 28800  # 8小时
        }
    },
    'trend': {
        'ma_follow': {
            'enabled': True,
            'weight': Decimal('0.1'),
            'fast_ma': 5,
            'slow_ma': 20,
            'volume_ma': 10
        },
        'breakout': {
            'enabled': True,
            'weight': Decimal('0.1'),
            'lookback_periods': 24,
            'breakout_threshold': Decimal('0.02')
        }
    },
    'mean_reversion': {
        'bounce_trading': {
            'enabled': True,
            'weight': Decimal('0.1'),
            'std_threshold': Decimal('2.0'),
            'mean_period': 20
        }
    },
    'grid': {
        'adaptive_grid': {
            'enabled': True,
            'weight': Decimal('0.1'),
            'grid_levels': 5,
            'grid_spread': Decimal('0.002'),
            'vol_threshold': Decimal('0.02')
        }
    }
}

# 风控配置
RISK_CONTROL = {
    'position_limits': {
        'max_single_position': Decimal('0.3'),  # 单个仓位最大资金比例
        'max_total_positions': Decimal('0.8'),  # 总仓位最大资金比例
        'min_position_size': Decimal('5'),     # 最小仓位USDT金额
        'max_leverage': 3                      # 最大杠杆倍数
    },
    'loss_limits': {
        'max_single_loss': Decimal('0.02'),    # 单笔最大亏损
        'daily_loss_limit': Decimal('0.05'),   # 日亏损限制
        'max_drawdown': Decimal('0.1')         # 最大回撤限制
    },
    'time_limits': {
        'position_timeout': 3600,              # 持仓超时(秒)
        'order_timeout': 60,                   # 订单超时(秒)
        'min_order_interval': 1                # 最小下单间隔(秒)
    },
    'price_limits': {
        'min_spread': Decimal('0.001'),        # 最小价差
        'max_slippage': Decimal('0.002'),      # 最大滑点
        'price_deviation_threshold': Decimal('0.05')  # 价格偏离阈值
    }
}

# 交易所规则
EXCHANGE_RULES = {
    'okx': {
        'contract_values': {
            'BTC-USDT-SWAP': Decimal('0.01'),
            'ETH-USDT-SWAP': Decimal('0.1'),
            'EOS-USDT-SWAP': Decimal('10')
        },
        'min_sizes': {
            'BTC-USDT-SWAP': Decimal('1'),
            'ETH-USDT-SWAP': Decimal('1'),
            'EOS-USDT-SWAP': Decimal('1')
        },
        'max_leverage': {
            'BTC-USDT-SWAP': 10,
            'ETH-USDT-SWAP': 10,
            'EOS-USDT-SWAP': 10
        }
    },
    'binance': {
        'min_notional': {
            'BTC-USDT': Decimal('5.0'),
            'ETH-USDT': Decimal('5.0'),
            'EOS-USDT': Decimal('20.0')
        },
        'step_sizes': {
            'BTC-USDT': Decimal('0.001'),
            'ETH-USDT': Decimal('0.01'),
            'EOS-USDT': Decimal('0.1')
        },
        'max_leverage': {
            'BTC-USDT': 10,
            'ETH-USDT': 10,
            'EOS-USDT': 10
        }
    }
}

# Web服务配置
WEB_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'debug': False,
    'secret_key': 'your_secret_key',
    'jwt_secret': 'your_jwt_secret'
}
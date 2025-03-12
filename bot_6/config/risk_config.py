from decimal import Decimal
from typing import Dict

# 全局风控配置
GLOBAL_RISK_CONFIG = {
    'max_positions': 4,                    # 最大同时持仓数
    'max_drawdown': Decimal('0.1'),       # 最大回撤 10%
    'daily_loss_limit': Decimal('0.05'),  # 日亏损限制 5%
    'total_exposure_limit': Decimal('0.8') # 总敞口限制 80%
}

# 仓位风控配置
POSITION_RISK_CONFIG = {
    'max_position_size': Decimal('0.3'),     # 单个仓位最大资金比例 30%
    'min_position_size': Decimal('0.01'),    # 最小仓位比例 1%
    'max_leverage': 3,                       # 最大杠杆倍数
    'max_holding_time': 3600,               # 最大持仓时间（秒）
    'stop_loss': {
        'initial': Decimal('0.02'),          # 初始止损 2%
        'trailing': Decimal('0.01')          # 追踪止损 1%
    },
    'take_profit': {
        'target': Decimal('0.03'),          # 止盈目标 3%
        'partial': Decimal('0.02')          # 部分止盈 2%
    }
}

# 策略风控配置
STRATEGY_RISK_CONFIG = {
    'arbitrage': {
        'min_spread': Decimal('0.001'),      # 最小价差 0.1%
        'max_slippage': Decimal('0.002'),    # 最大滑点 0.2%
        'max_waiting_time': 60,              # 最大等待时间（秒）
        'min_volume': Decimal('10000')       # 最小交易量
    },
    'trend': {
        'min_trend_strength': Decimal('0.02'), # 最小趋势强度 2%
        'max_entry_timeout': 300,             # 最大入场超时（秒）
        'confirmation_required': 2             # 所需确认数
    },
    'mean_reversion': {
        'max_deviation': Decimal('0.03'),     # 最大偏离度 3%
        'min_reversion_prob': Decimal('0.7'), # 最小回归概率 70%
        'max_position_hold': 1800             # 最大持仓时间（秒）
    },
    'grid': {
        'grid_spacing': Decimal('0.01'),      # 网格间距 1%
        'max_grid_levels': 5,                 # 最大网格层数
        'volume_filter': Decimal('5000')      # 成交量过滤
    }
}

# 交易所风控配置
EXCHANGE_RISK_CONFIG = {
    'okx': {
        'max_order_size': {
            'BTC-USDT': Decimal('0.1'),
            'ETH-USDT': Decimal('1.0'),
            'EOS-USDT': Decimal('100.0')
        },
        'min_order_size': {
            'BTC-USDT': Decimal('0.001'),
            'ETH-USDT': Decimal('0.01'),
            'EOS-USDT': Decimal('1.0')
        },
        'price_filters': {
            'BTC-USDT': Decimal('0.1'),
            'ETH-USDT': Decimal('0.01'),
            'EOS-USDT': Decimal('0.001')
        }
    },
    'binance': {
        'max_order_size': {
            'BTC-USDT': Decimal('0.1'),
            'ETH-USDT': Decimal('1.0'),
            'EOS-USDT': Decimal('100.0')
        },
        'min_order_size': {
            'BTC-USDT': Decimal('0.001'),
            'ETH-USDT': Decimal('0.01'),
            'EOS-USDT': Decimal('1.0')
        },
        'price_filters': {
            'BTC-USDT': Decimal('0.1'),
            'ETH-USDT': Decimal('0.01'),
            'EOS-USDT': Decimal('0.001')
        }
    }
}

# 时间风控配置
TIME_RISK_CONFIG = {
    'market_hours': {
        'start': '00:00:00',
        'end': '23:59:59'
    },
    'trade_intervals': {
        'min_order_interval': 1,    # 最小下单间隔（秒）
        'position_update': 1,       # 持仓更新间隔（秒）
        'risk_check': 5            # 风控检查间隔（秒）
    },
    'timeouts': {
        'order_timeout': 60,        # 订单超时（秒）
        'connection_timeout': 30,   # 连接超时（秒）
        'idle_timeout': 300        # 空闲超时（秒）
    }
}
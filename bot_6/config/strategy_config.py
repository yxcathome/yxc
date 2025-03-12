STRATEGY_CONFIGS = {
    # 套利策略组
    'arbitrage': {
        'basic_arb': {
            'enabled': True,
            'pairs': ['BTC-USDT', 'ETH-USDT'],
            'min_spread': 0.001,  # 最小价差
            'max_position': 0.1   # 最大仓位比例
        },
        'flash_arb': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'trigger_percent': 0.005,  # 触发价格偏离
            'execution_timeout': 1.0    # 执行超时(秒)
        },
        'funding_arb': {
            'enabled': True,
            'pairs': ['BTC-USDT-SWAP'],
            'min_funding_rate': 0.01    # 最小资金费率
        }
    },
    
    # 趋势策略组
    'trend': {
        'ma_follow': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'fast_period': 10,
            'slow_period': 20
        },
        'breakout': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'breakout_period': 20,
            'confirmation_bars': 3
        },
        'momentum': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'lookback_period': 14,
            'momentum_threshold': 0.02
        }
    },
    
    # 均值回归策略组
    'mean_reversion': {
        'pair_trading': {
            'enabled': True,
            'pairs': [('BTC-USDT', 'ETH-USDT')],
            'zscore_threshold': 2.0
        },
        'bounce_trading': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'lookback_period': 30,
            'std_multiplier': 2.0
        }
    },
    
    # 网格策略组
    'grid': {
        'range_grid': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'grid_levels': 10,
            'upper_price': 50000,
            'lower_price': 40000
        },
        'adaptive_grid': {
            'enabled': True,
            'pairs': ['BTC-USDT'],
            'grid_levels': 10,
            'volatility_period': 24
        }
    }
}
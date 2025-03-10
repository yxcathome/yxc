from decimal import Decimal

CONFIG = {
    # 交易基础配置
    'initial_trade_usdt': Decimal('10'),  # 初始交易金额
    'max_leverage': 20,                   # 最大杠杆倍数
    'orderbook_depth': 20,                # 订单簿深度

    # 交易所配置
    'exchange_limits': {
        'okx': 20,      # OKX API请求限制
        'binance': 20   # Binance API请求限制
    },

    # 风控配置
    'risk_control': {
        'max_position_size': Decimal('0.5'),     # 单标的最大持仓50%
        'max_drawdown': Decimal('0.1'),            # 最大回撤限制
        'daily_loss_limit': Decimal('0.05'),       # 每日亏损限制
        'position_limit': 5,                        # 最大持仓数量
        'max_daily_loss': Decimal('0.05')           # 5%最大日亏损
    },

    # 策略启用配置
    'enabled_strategies': {
        'arbitrage': True,      # 套利策略
        'trend': True,          # 趋势跟踪
        'grid': True,           # 网格策略
        'funding': True         # 资金费率策略
    },

    # 套利策略配置
    'arbitrage': {
        'min_spread': Decimal('0.001'),  # 最小价差
        'trade_amount': Decimal('0.01'), # 交易数量
        'max_slippage': Decimal('0.0005'),  # 最大滑点
        'timeout': 5                      # 超时时间 (秒)
    },

    # 趋势策略配置
    'trend': {
        'timeframe': '1h',       # K线周期
        'ma_fast': 5,            # 快速MA周期
        'ma_slow': 20,           # 慢速MA周期
        'rsi_period': 14,        # RSI周期
        'rsi_overbought': 70,    # RSI超买值
        'rsi_oversold': 30,      # RSI超卖值
        'stop_loss': Decimal('0.02'),   # 止损比例
        'take_profit': Decimal('0.03'), # 止盈比例
        'kline_limit': 100       # K线获取数量
    },

    # 网格策略配置
    'grid': {
        'grid_number': 10,                # 网格数量
        'price_range': Decimal('0.1'),      # 价格范围
        'invest_amount': Decimal('1000'),   # 投资金额
        'trigger_distance': Decimal('0.002')# 触发距离
    },

    # 资金费率策略配置
    'funding': {
        'min_rate': Decimal('0.001'),       # 最小费率差
        'hold_hours': 8,                    # 持仓时间 (小时)
        'position_size': Decimal('0.1')       # 持仓大小
    },

    # 交易对配置（预置的交易对，当自动获取失败时可作为兜底）
    'trading_pairs': [
        'BTC/USDT:USDT',
        'ETH/USDT:USDT',
        'BNB/USDT:USDT'
    ],

    # 系统配置
    'check_interval': 1,        # 检查间隔 (秒)
    'log_level': 'INFO',        # 日志级别
    'retry_times': 3,           # 重试次数
    'retry_delay': 1,           # 重试延迟 (秒)
    'request_delay': 0.5        # 主循环请求间隔
}
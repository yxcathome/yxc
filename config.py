# 配置文件
import os
from decimal import Decimal

# 从环境变量加载API密钥
OKX_API_KEY = os.environ.get('OKX_API_KEY')
OKX_SECRET = os.environ.get('OKX_SECRET')
OKX_PASSWORD = os.environ.get('OKX_PASSWORD')
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
BINANCE_SECRET = os.environ.get('BINANCE_SECRET')

# 交易配置
TRADE_CONFIG = {
    'initial_trade_usdt': Decimal('7.5'),  # 初始交易金额
    'max_trade_usdt': Decimal('100.0'),    # 最大交易金额
    'min_profit_margin': Decimal('0.0001'),  # 最小利润阈值
    'position_risk': Decimal('0.9'),       # 仓位风险控制
    'compound_percent': Decimal('0.01'),   # 复利比例
    'compound_enabled': True,              # 是否启用复利
    'slippage_allowance': Decimal('0.001'),  # 滑点容忍度
    'orderbook_depth': 20,                 # 订单簿深度
    'max_concurrent_checks': 10            # 最大并发检查数
}

# 手续费配置
FEES_CONFIG = {
    'okx': {'taker': Decimal('0.0005')},
    'binance': {'taker': Decimal('0.0004')}
}

# 系统配置
SYSTEM_CONFIG = {
    'webserver_port': 5000,                # Web服务端口
    'balance_refresh_interval': 30,        # 余额刷新间隔（秒）
    'funding_rate_interval': 4 * 3600,     # 资金费率更新间隔（秒）
    'health_check_interval': 60            # 健康检查间隔（秒）
}

# 日志配置
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s [%(levelname)s] %(message)s',
    'datefmt': '%Y-%m-%d %H:%M:%S'
}
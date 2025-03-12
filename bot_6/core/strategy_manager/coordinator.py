from typing import Dict, List, Optional
from decimal import Decimal
import asyncio
from datetime import datetime
from utils.logger import setup_logger
from config.strategy_config import STRATEGY_CONFIGS

class StrategyCoordinator:
    def __init__(self, bot):
        self.bot = bot
        self.logger = setup_logger("strategy_coordinator")
        
        # 策略组
        self.strategy_groups = {
            'arbitrage': {},
            'trend': {},
            'mean_reversion': {},
            'grid': {}
        }
        
        # 策略实例
        self.strategies = {}
        
        # 执行优先级
        self.priority_order = [
            'arbitrage',    # 套利优先
            'trend',        # 趋势策略
            'mean_reversion', # 均值回归
            'grid'          # 网格策略
        ]
        
    async def initialize(self):
        """初始化策略协调器"""
        try:
            # 加载策略配置
            await self._load_strategies()
            
            # 初始化策略实例
            await self._initialize_strategies()
            
            self.logger.info("策略协调器初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"策略协调器初始化失败: {e}")
            return False
            
    async def execute_strategies(self):
        """执行策略"""
        try:
            # 检查策略冲突
            conflicts = await self._check_conflicts()
            if conflicts:
                self.logger.warning(f"检测到策略冲突: {conflicts}")
                return
                
            # 按优先级执行策略组
            for group in self.priority_order:
                if group in self.strategy_groups:
                    await self._execute_strategy_group(group)
                    
        except Exception as e:
            self.logger.error(f"执行策略失败: {e}")
            
    async def stop_all(self):
        """停止所有策略"""
        try:
            for strategy in self.strategies.values():
                await strategy.stop()
            self.logger.info("所有策略已停止")
            return True
        except Exception as e:
            self.logger.error(f"停止策略失败: {e}")
            return False
            
    async def _load_strategies(self):
        """加载策略配置"""
        try:
            for group_name, group_config in STRATEGY_CONFIGS.items():
                for strategy_name, strategy_config in group_config.items():
                    if strategy_config.get('enabled', False):
                        self.strategy_groups[group_name][strategy_name] = strategy_config
                        
            self.logger.info(f"加载策略配置完成: {len(self.strategy_groups)} 个策略组")
            
        except Exception as e:
            self.logger.error(f"加载策略配置失败: {e}")
            raise
            
    async def _initialize_strategies(self):
        """初始化策略实例"""
        try:
            for group_name, strategies in self.strategy_groups.items():
                for strategy_name, config in strategies.items():
                    strategy = await self._create_strategy(
                        group_name,
                        strategy_name,
                        config
                    )
                    if strategy:
                        self.strategies[f"{group_name}.{strategy_name}"] = strategy
                        
            self.logger.info(f"初始化策略实例完成: {len(self.strategies)} 个策略")
            
        except Exception as e:
            self.logger.error(f"初始化策略实例失败: {e}")
            raise
            
    async def _create_strategy(self, group_name: str, strategy_name: str, 
                             config: Dict) -> Optional[object]:
        """创建策略实例"""
        try:
            # 导入策略类
            if group_name == 'arbitrage':
                if strategy_name == 'basic_arb':
                    from strategies.arbitrage.basic_arb import BasicArbitrageStrategy
                    return BasicArbitrageStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                elif strategy_name == 'flash_arb':
                    from strategies.arbitrage.flash_arb import FlashArbitrageStrategy
                    return FlashArbitrageStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                elif strategy_name == 'funding_arb':
                    from strategies.arbitrage.funding_arb import FundingArbitrageStrategy
                    return FundingArbitrageStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                    
            elif group_name == 'trend':
                if strategy_name == 'ma_follow':
                    from strategies.trend.ma_follow import MATrendStrategy
                    return MATrendStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                elif strategy_name == 'breakout':
                    from strategies.trend.breakout import BreakoutStrategy
                    return BreakoutStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                elif strategy_name == 'momentum':
                    from strategies.trend.momentum import MomentumStrategy
                    return MomentumStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                    
            elif group_name == 'mean_reversion':
                if strategy_name == 'bounce_trading':
                    from strategies.mean_reversion.bounce_trading import BounceStrategy
                    return BounceStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                    
            elif group_name == 'grid':
                if strategy_name == 'range_grid':
                    from strategies.grid.range_grid import RangeGridStrategy
                    return RangeGridStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                elif strategy_name == 'adaptive_grid':
                    from strategies.grid.adaptive_grid import AdaptiveGridStrategy
                    return AdaptiveGridStrategy(self.bot.exchange_manager, self.bot.risk_manager)
                    
            return None
            
        except Exception as e:
            self.logger.error(f"创建策略实例失败: {group_name}.{strategy_name} - {e}")
            return None
            
    async def _check_conflicts(self) -> List[str]:
        """检查策略冲突"""
        try:
            conflicts = []
            active_symbols = {}
            
            for strategy_id, strategy in self.strategies.items():
                if strategy.active:
                    for symbol in strategy.symbols:
                        if symbol in active_symbols:
                            conflicts.append(
                                f"策略冲突: {strategy_id} 与 {active_symbols[symbol]} "
                                f"在 {symbol} 上存在冲突"
                            )
                        else:
                            active_symbols[symbol] = strategy_id
                            
            return conflicts
            
        except Exception as e:
            self.logger.error(f"检查策略冲突失败: {e}")
            return []
            
    async def _execute_strategy_group(self, group_name: str):
        """执行策略组"""
        try:
            if group_name not in self.strategy_groups:
                return
                
            for strategy_name, strategy in self.strategies.items():
                if strategy_name.startswith(f"{group_name}."):
                    if strategy.active:
                        # 获取市场数据
                        market_data = await self._get_market_data(strategy.symbols)
                        
                        # 生成信号
                        signals = await strategy.generate_signals(market_data)
                        
                        # 执行信号
                        if signals:
                            for signal in signals:
                                await self._execute_signal(strategy, signal)
                                
        except Exception as e:
            self.logger.error(f"执行策略组失败: {group_name} - {e}")
            
    async def _get_market_data(self, symbols: List[str]) -> Dict:
        """获取市场数据"""
        try:
            market_data = {}
            for symbol in symbols:
                data = {
                    'orderbooks': {},
                    'trades': {},
                    'tickers': {}
                }
                
                for exchange in self.bot.exchanges.values():
                    orderbook = await exchange.fetch_order_book(symbol)
                    trades = await exchange.fetch_trades(symbol)
                    ticker = await exchange.fetch_ticker(symbol)
                    
                    if orderbook:
                        data['orderbooks'][exchange.name] = orderbook
                    if trades:
                        data['trades'][exchange.name] = trades
                    if ticker:
                        data['tickers'][exchange.name] = ticker
                        
                market_data[symbol] = data
                
            return market_data
            
        except Exception as e:
            self.logger.error(f"获取市场数据失败: {e}")
            return {}
            
    async def _execute_signal(self, strategy, signal: Dict):
        """执行交易信号"""
        try:
            # 风控检查
            if not await self.bot.risk_manager.can_execute_signal(strategy, signal):
                return
                
            # 计算仓位大小
            position_size = await strategy.calculate_position_size(
                signal['symbol'],
                signal
            )
            if not position_size:
                return
                
            # 执行交易
            orders = await self.bot.position_tracker.execute_orders(
                strategy.id,
                signal,
                position_size
            )
            
            if orders:
                self.logger.info(
                    f"执行信号成功: {strategy.id} - {signal['symbol']} - "
                    f"{signal['type']} - {position_size}"
                )
                
        except Exception as e:
            self.logger.error(f"执行信号失败: {e}")
import asyncio
from typing import Dict, Optional
from decimal import Decimal
import logging
from datetime import datetime

from config.settings import BASE_CONFIG
from core.strategy_manager.coordinator import StrategyCoordinator
from core.position_manager.position_tracker import PositionTracker
from core.risk_manager.global_risk import GlobalRiskManager
from core.risk_manager.position_risk import PositionRiskManager
from core.risk_manager.strategy_risk import StrategyRiskManager
from core.monitor.performance_monitor import PerformanceMonitor
from core.storage.database import Database
from exchanges.base_exchange import BaseExchange
from utils.logger import setup_logger

class TradingBot:
    def __init__(self):
        self.logger = setup_logger("trading_bot")
        self.config = BASE_CONFIG
        self.exchanges = {}
        self.active = False
        
    async def initialize(self):
        """初始化交易机器人"""
        try:
            # 初始化数据库
            self.database = Database(self.config)
            if not await self.database.initialize():
                raise Exception("数据库初始化失败")
                
            # 初始化交易所连接
            await self._initialize_exchanges()
            
            # 初始化风控系统
            self.global_risk = GlobalRiskManager(self)
            self.position_risk = PositionRiskManager(self)
            self.strategy_risk = StrategyRiskManager(self)
            
            await self.global_risk.initialize()
            await self.position_risk.initialize()
            await self.strategy_risk.initialize()
            
            # 初始化仓位管理
            self.position_tracker = PositionTracker(self)
            await self.position_tracker.initialize()
            
            # 初始化策略管理
            self.strategy_coordinator = StrategyCoordinator(self)
            await self.strategy_coordinator.initialize()
            
            # 初始化性能监控
            self.performance_monitor = PerformanceMonitor(self.global_risk)
            await self.performance_monitor.start()
            
            self.logger.info("交易机器人初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化失败: {e}")
            return False
            
    async def start(self):
        """启动交易机器人"""
        try:
            if not self.active:
                self.active = True
                
                # 启动各个组件
                asyncio.create_task(self._main_loop())
                asyncio.create_task(self._monitor_exchanges())
                asyncio.create_task(self._risk_check_loop())
                
                self.logger.info("交易机器人启动成功")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"启动失败: {e}")
            return False
            
    async def stop(self):
        """停止交易机器人"""
        try:
            if self.active:
                self.active = False
                
                # 停止所有策略
                await self.strategy_coordinator.stop_all()
                
                # 关闭所有连接
                for exchange in self.exchanges.values():
                    await exchange.close()
                    
                self.logger.info("交易机器人停止成功")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"停止失败: {e}")
            return False
            
    async def _initialize_exchanges(self):
        """初始化交易所"""
        try:
            for exchange_id, config in self.config['exchanges'].items():
                exchange = self._create_exchange(exchange_id, config)
                if exchange:
                    if await exchange.connect():
                        self.exchanges[exchange_id] = exchange
                        self.logger.info(f"交易所 {exchange_id} 连接成功")
                    else:
                        self.logger.error(f"交易所 {exchange_id} 连接失败")
                        
        except Exception as e:
            self.logger.error(f"初始化交易所失败: {e}")
            raise
            
    def _create_exchange(self, exchange_id: str, config: Dict) -> Optional[BaseExchange]:
        """创建交易所实例"""
        try:
            if exchange_id == 'okx':
                from exchanges.okx.client import OKXExchange
                return OKXExchange()
            elif exchange_id == 'binance':
                from exchanges.binance.client import BinanceExchange
                return BinanceExchange()
            else:
                self.logger.error(f"不支持的交易所: {exchange_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"创建交易所实例失败: {e}")
            return None
            
    async def _main_loop(self):
        """主循环"""
        while self.active:
            try:
                # 更新市场数据
                await self._update_market_data()
                
                # 执行策略
                await self.strategy_coordinator.execute_strategies()
                
                # 更新持仓
                await self.position_tracker.update_positions()
                
                # 休眠
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"主循环异常: {e}")
                await asyncio.sleep(5)
                
    async def _monitor_exchanges(self):
        """监控交易所状态"""
        while self.active:
            try:
                for exchange_id, exchange in self.exchanges.items():
                    if not await exchange.ping():
                        self.logger.warning(f"交易所 {exchange_id} 连接断开，尝试重连")
                        if await exchange.connect():
                            self.logger.info(f"交易所 {exchange_id} 重连成功")
                        else:
                            self.logger.error(f"交易所 {exchange_id} 重连失败")
                            
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"监控交易所异常: {e}")
                await asyncio.sleep(5)
                
    async def _risk_check_loop(self):
        """风控检查循环"""
        while self.active:
            try:
                # 全局风控检查
                await self.global_risk._check_risk()
                
                # 仓位风控检查
                await self.position_risk._check_positions()
                
                # 策略风控检查
                await self.strategy_risk._check_strategies()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"风控检查异常: {e}")
                await asyncio.sleep(5)
                
    async def _update_market_data(self):
        """更新市场数据"""
        try:
            for exchange in self.exchanges.values():
                for symbol in exchange.markets:
                    # 获取深度数据
                    orderbook = await exchange.fetch_order_book(symbol)
                    if orderbook:
                        await self.database.save_market_data({
                            'exchange': exchange.name,
                            'symbol': symbol,
                            'type': 'orderbook',
                            'data': orderbook,
                            'timestamp': datetime.utcnow()
                        })
                        
                    # 获取最新成交
                    trades = await exchange.fetch_trades(symbol)
                    if trades:
                        await self.database.save_market_data({
                            'exchange': exchange.name,
                            'symbol': symbol,
                            'type': 'trades',
                            'data': trades,
                            'timestamp': datetime.utcnow()
                        })
                        
        except Exception as e:
            self.logger.error(f"更新市场数据失败: {e}")
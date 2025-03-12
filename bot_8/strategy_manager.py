import threading
import queue
from typing import Dict, List, Optional
from datetime import datetime, timezone
import numpy as np
from collections import defaultdict

from strategies.strategy_base import StrategyBase
from strategies.strategy_mean_reversion import MeanReversionStrategy
from strategies.strategy_ma_trend import MATrendStrategy
from strategies.strategy_breakout import BreakoutStrategy
from strategies.strategy_arbitrage import ArbitrageStrategy
from logger import Logger
from config import Config

class StrategyManager:
    def __init__(self, exchange_id: str):
        self.logger = Logger("StrategyManager")
        self.exchange_id = exchange_id
        
        # 初始化策略实例
        self.strategies = self._initialize_strategies()
        
        # 策略性能统计
        self.strategy_stats = defaultdict(lambda: {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'pnl': 0.0,
            'last_signal': None,
            'last_update': None
        })
        
        # 信号队列
        self.signal_queue = queue.Queue()
        
        # 策略状态
        self.strategy_states = {}
        
        # 启动策略监控
        self._start_strategy_monitor()
        
    def _initialize_strategies(self) -> Dict[str, Dict]:
        """初始化策略实例"""
        try:
            strategies = {
                'mean_reversion': {
                    'instance': MeanReversionStrategy(self.exchange_id, None),
                    'params': Config.STRATEGY_PARAMS['mean_reversion'],
                    'pairs': Config.TRADING_PAIRS,
                    'enabled': True
                },
                'ma_trend': {
                    'instance': MATrendStrategy(self.exchange_id, None),
                    'params': Config.STRATEGY_PARAMS['ma_trend'],
                    'pairs': Config.TRADING_PAIRS,
                    'enabled': True
                },
                'breakout': {
                    'instance': BreakoutStrategy(self.exchange_id, None),
                    'params': Config.STRATEGY_PARAMS['breakout'],
                    'pairs': Config.TRADING_PAIRS,
                    'enabled': True
                },
                'arbitrage': {
                    'instance': ArbitrageStrategy(self.exchange_id, None),
                    'params': Config.STRATEGY_PARAMS['arbitrage'],
                    'pairs': Config.TRADING_PAIRS,
                    'enabled': True
                }
            }
            
            return strategies
            
        except Exception as e:
            self.logger.error(f"Error initializing strategies: {str(e)}")
            raise
            
    def run_strategies(self):
        """运行所有启用的策略"""
        try:
            current_time = datetime.now(timezone.utc)
            
            for strategy_name, strategy_info in self.strategies.items():
                if not strategy_info['enabled']:
                    continue
                    
                for pair in strategy_info['pairs']:
                    try:
                        # 检查策略运行条件
                        if not self._check_strategy_conditions(strategy_name, pair):
                            continue
                            
                        # 运行策略
                        signal = strategy_info['instance'].generate_signal(pair)
                        
                        # 处理信号
                        if signal and signal['action'] != 'hold':
                            self._process_strategy_signal(strategy_name, pair, signal)
                            
                        # 更新策略状态
                        self._update_strategy_state(strategy_name, pair, signal)
                        
                    except Exception as e:
                        self.logger.error(f"Error running strategy {strategy_name} for {pair}: {str(e)}")
                        
        except Exception as e:
            self.logger.error(f"Error in strategy execution: {str(e)}")
            
    def _check_strategy_conditions(self, strategy_name: str, pair: str) -> bool:
        """检查策略运行条件"""
        try:
            # 获取当前市场状态
            market_state = self.market_data.get_market_state(pair)
            
            # 检查策略适用性
            strategy_market_mapping = {
                'mean_reversion': ['ranging', 'sideways'],
                'ma_trend': ['trending'],
                'breakout': ['volatile'],
                'arbitrage': ['sideways', 'ranging']
            }
            
            if market_state not in strategy_market_mapping[strategy_name]:
                return False
                
            # 检查交易时间窗口
            current_time = datetime.now(timezone.utc)
            if not self._is_valid_trading_time(current_time):
                return False
                
            # 检查策略冷却时间
            last_update = self.strategy_stats[f"{strategy_name}_{pair}"]["last_update"]
            if last_update and (current_time - last_update).total_seconds() < Config.STRATEGY_PARAMS[strategy_name].get('cooldown', 0):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking strategy conditions: {str(e)}")
            return False
            
    def _process_strategy_signal(self, strategy_name: str, pair: str, signal: Dict):
        """处理策略信号"""
        try:
            # 信号增强
            enhanced_signal = self._enhance_signal(strategy_name, pair, signal)
            
            # 信号验证
            if not self._validate_signal(enhanced_signal):
                return
                
            # 添加到信号队列
            self.signal_queue.put({
                'strategy': strategy_name,
                'pair': pair,
                'signal': enhanced_signal,
                'timestamp': datetime.now(timezone.utc)
            })
            
            # 更新策略统计
            self._update_strategy_stats(strategy_name, pair, enhanced_signal)
            
        except Exception as e:
            self.logger.error(f"Error processing strategy signal: {str(e)}")
            
    def _enhance_signal(self, strategy_name: str, pair: str, signal: Dict) -> Dict:
        """增强策略信号"""
        try:
            # 获取市场数据
            market_data = self.market_data.get_market_data(pair)
            
            # 计算信号置信度
            confidence = self._calculate_signal_confidence(strategy_name, pair, signal)
            
            # 计算建议仓位大小
            position_size = self._calculate_position_size(pair, signal, confidence)
            
            # 添加风险管理参数
            risk_params = self._calculate_risk_params(pair, signal)
            
            enhanced_signal = {
                **signal,
                'confidence': confidence,
                'position_size': position_size,
                'stop_loss': risk_params['stop_loss'],
                'take_profit': risk_params['take_profit'],
                'trailing_stop': risk_params['trailing_stop']
            }
            
            return enhanced_signal
            
        except Exception as e:
            self.logger.error(f"Error enhancing signal: {str(e)}")
            return signal
            
    def _calculate_signal_confidence(self, strategy_name: str, pair: str, signal: Dict) -> float:
        """计算信号置信度"""
        try:
            # 基础置信度（来自策略）
            base_confidence = signal.get('confidence', 0.5)
            
            # 策略历史表现
            stats = self.strategy_stats[f"{strategy_name}_{pair}"]
            if stats['trades'] > 0:
                win_rate = stats['wins'] / stats['trades']
                historical_factor = win_rate * 0.5
            else:
                historical_factor = 0.25
                
            # 市场条件评分
            market_score = self._evaluate_market_conditions(pair)
            
            # 综合计算置信度
            confidence = (
                base_confidence * 0.4 +
                historical_factor * 0.3 +
                market_score * 0.3
            )
            
            return min(max(confidence, 0), 1)
            
        except Exception as e:
            self.logger.error(f"Error calculating signal confidence: {str(e)}")
            return 0.5
            
    def _calculate_position_size(self, pair: str, signal: Dict, confidence: float) -> float:
        """计算建议仓位大小"""
        try:
            # 基础仓位大小
            base_size = Config.MAX_POSITION_SIZE
            
            # 根据置信度调整
            confidence_factor = 0.5 + (confidence * 0.5)
            
            # 根据波动率调整
            volatility = self.market_data.get_volatility(pair)
            volatility_factor = 1 / (1 + volatility)
            
            # 计算最终仓位
            position_size = base_size * confidence_factor * volatility_factor
            
            # 确保不超过最大限制
            position_size = min(position_size, Config.MAX_POSITION_SIZE)
            
            return position_size
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {str(e)}")
            return Config.MAX_POSITION_SIZE * 0.5
            
    def _calculate_risk_params(self, pair: str, signal: Dict) -> Dict:
        """计算风险管理参数"""
        try:
            # 获取当前波动率
            volatility = self.market_data.get_volatility(pair)
            atr = self.market_data.get_atr(pair)
            
            # 计算止损水平
            stop_loss = signal['price'] * (1 - volatility * 2)
            if signal['action'] == 'sell':
                stop_loss = signal['price'] * (1 + volatility * 2)
                
            # 计算止盈水平
            take_profit = signal['price'] * (1 + volatility * 3)
            if signal['action'] == 'sell':
                take_profit = signal['price'] * (1 - volatility * 3)
                
            # 计算追踪止损
            trailing_stop = {
                'activation': signal['price'] * (1 + volatility),
                'distance': atr * 2
            }
            
            return {
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'trailing_stop': trailing_stop
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating risk parameters: {str(e)}")
            return {
                'stop_loss': None,
                'take_profit': None,
                'trailing_stop': None
            }

    def _update_strategy_stats(self, strategy_name: str, pair: str, signal: Dict):
        """更新策略统计数据"""
        key = f"{strategy_name}_{pair}"
        self.strategy_stats[key]['last_signal'] = signal
        self.strategy_stats[key]['last_update'] = datetime.now(timezone.utc)
        self.strategy_stats[key]['trades'] += 1

    def get_strategy_stats(self, strategy_name: Optional[str] = None) -> Dict:
        """获取策略统计数据"""
        if strategy_name:
            return {k: v for k, v in self.strategy_stats.items() if k.startswith(strategy_name)}
        return dict(self.strategy_stats)
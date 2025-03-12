from typing import Dict, Optional
from decimal import Decimal
import time
from config import Config
from logger import Logger
from market_data import MarketData
from position_manager import PositionManager

class RiskManager:
    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.logger = Logger("RiskManager")
        self.market_data = MarketData(exchange_id)
        self.position_manager = PositionManager(exchange_id)
        self.risk_metrics = {}
    
    def check_position(self, symbol: str) -> bool:
        """
        检查仓位风险
        """
        try:
            position = self.position_manager.get_position(symbol)
            if not position:
                return True
            
            current_price = self.market_data.get_current_price(symbol)
            entry_price = position['entry_price']
            
            # 计算浮动盈亏百分比
            pnl_pct = (
                (current_price - entry_price) / entry_price * 
                (1 if position['side'] == 'buy' else -1)
            )
            
            # 更新风险指标
            self.risk_metrics[symbol] = {
                'pnl_pct': pnl_pct,
                'last_check': time.time()
            }
            
            # 检查止损条件
            if pnl_pct < -Config.STOP_LOSS_PCT:
                self.logger.risk_log(
                    'STOP_LOSS',
                    'TRIGGERED',
                    f'PnL: {pnl_pct:.2%}'
                )
                return self.position_manager.close_position(
                    symbol, 
                    'Stop loss triggered'
                )
            
            # 检查止盈条件
            if pnl_pct > Config.TAKE_PROFIT_PCT:
                self.logger.risk_log(
                    'TAKE_PROFIT',
                    'TRIGGERED',
                    f'PnL: {pnl_pct:.2%}'
                )
                return self.position_manager.close_position(
                    symbol,
                    'Take profit triggered'
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking position risk: {str(e)}")
            return False
    
    def check_account_risk(self) -> bool:
        """
        检查账户风险
        """
        try:
            # 获取账户余额
            balance = self.position_manager.exchange.fetch_balance()
            total_balance = float(balance['total']['USDT'])
            used_balance = float(balance['used']['USDT'])
            
            # 计算账户使用率
            usage_ratio = used_balance / total_balance if total_balance > 0 else 0
            
            # 计算当日盈亏
            total_pnl = sum(
                metric['pnl_pct'] for metric in self.risk_metrics.values()
            )
            
            # 检查最大回撤
            if total_pnl < -Config.MAX_DRAWDOWN_PCT:
                self.logger.risk_log(
                    'MAX_DRAWDOWN',
                    'TRIGGERED',
                    f'Total PnL: {total_pnl:.2%}'
                )
                return self._close_all_positions('Max drawdown reached')
            
            # 检查是否超过最大持仓数
            active_positions = len(self.position_manager.positions)
            if active_positions > Config.MAX_POSITIONS:
                self.logger.risk_log(
                    'MAX_POSITIONS',
                    'EXCEEDED',
                    f'Active positions: {active_positions}'
                )
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking account risk: {str(e)}")
            return False
    
    def check_market_risk(self, symbol: str) -> bool:
        """
        检查市场风险
        """
        try:
            # 获取市场数据
            df = self.market_data.update_market_data(
                symbol, 
                Config.BASE_TIMEFRAME
            )
            
            # 计算波动率
            returns = df['close'].pct_change()
            volatility = returns.std() * (252 ** 0.5)  # 年化波动率
            
            # 检查是否存在异常波动
            if volatility > Config.VOLATILITY_THRESHOLD:
                self.logger.risk_log(
                    'HIGH_VOLATILITY',
                    'WARNING',
                    f'Volatility: {volatility:.2%}'
                )
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking market risk: {str(e)}")
            return False
    
    def _close_all_positions(self, reason: str) -> bool:
        """
        关闭所有持仓
        """
        try:
            success = True
            for symbol in list(self.position_manager.positions.keys()):
                if not self.position_manager.close_position(symbol, reason):
                    success = False
            return success
        except Exception as e:
            self.logger.error(f"Error closing all positions: {str(e)}")
            return False
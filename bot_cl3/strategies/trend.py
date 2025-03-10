from datetime import datetime
import pandas as pd
import pandas_ta as ta
import numpy as np
from decimal import Decimal
from typing import Optional, Dict, List
import logging
from .base import BaseStrategy

class TrendStrategy(BaseStrategy):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.name = "trend"
        self.is_active = config['enabled_strategies']['trend']
        self.trend_data = {}
        self.positions = {}
        
        # 从配置中获取参数
        trend_config = config['trend']
        self.timeframe = trend_config['timeframe']
        self.ma_fast = trend_config['ma_fast']
        self.ma_slow = trend_config['ma_slow']
        self.rsi_period = trend_config['rsi_period']
        self.rsi_overbought = trend_config['rsi_overbought']
        self.rsi_oversold = trend_config['rsi_oversold']
        self.stop_loss = Decimal(str(trend_config['stop_loss']))
        self.take_profit = Decimal(str(trend_config['take_profit']))
        self.kline_limit = trend_config['kline_limit']

    async def analyze(self, symbol: str) -> Optional[Dict]:
        """分析市场数据并生成交易信号"""
        try:
            # 获取K线数据
            klines = await self._get_klines(symbol)
            if not klines:
                return None

            # 计算技术指标
            indicators = self._calculate_indicators(klines)
            if not indicators:
                return None

            # 生成交易信号
            signal = self._generate_signal(symbol, indicators)
            return signal

        except Exception as e:
            self.logger.error(f"趋势分析异常: {e}")
            return None

    async def execute(self, signal: Dict) -> bool:
        """执行交易信号"""
        try:
            if not signal or 'action' not in signal:
                return False

            symbol = signal['symbol']
            action = signal['action']
            price = signal.get('price', None)
            amount = signal.get('amount', self.config['initial_trade_usdt'])

            if action == 'buy':
                # 开多仓
                order = await self.bot.okx.create_market_buy_order(
                    symbol=symbol,
                    amount=float(amount)
                )
                if order['status'] == 'closed':
                    self.positions[symbol] = {
                        'side': 'long',
                        'entry_price': Decimal(str(order['price'])),
                        'amount': Decimal(str(order['amount']))
                    }
                    self.logger.info(f"趋势策略开多仓成功: {symbol}")
                    return True

            elif action == 'sell':
                # 开空仓
                order = await self.bot.okx.create_market_sell_order(
                    symbol=symbol,
                    amount=float(amount)
                )
                if order['status'] == 'closed':
                    self.positions[symbol] = {
                        'side': 'short',
                        'entry_price': Decimal(str(order['price'])),
                        'amount': Decimal(str(order['amount']))
                    }
                    self.logger.info(f"趋势策略开空仓成功: {symbol}")
                    return True

            elif action == 'close':
                # 平仓
                if symbol in self.positions:
                    position = self.positions[symbol]
                    if position['side'] == 'long':
                        order = await self.bot.okx.create_market_sell_order(
                            symbol=symbol,
                            amount=float(position['amount'])
                        )
                    else:
                        order = await self.bot.okx.create_market_buy_order(
                            symbol=symbol,
                            amount=float(position['amount'])
                        )
                    
                    if order['status'] == 'closed':
                        del self.positions[symbol]
                        self.logger.info(f"趋势策略平仓成功: {symbol}")
                        return True

            return False

        except Exception as e:
            self.logger.error(f"执行交易信号异常: {e}")
            return False

    async def _get_klines(self, symbol: str) -> Optional[List]:
        """获取K线数据"""
        try:
            klines = await self.bot.okx.fetch_ohlcv(
                symbol,
                timeframe=self.timeframe,
                limit=self.kline_limit
            )
            return klines
        except Exception as e:
            self.logger.error(f"获取K线数据异常: {e}")
            return None

    def _calculate_indicators(self, klines: List) -> Optional[Dict]:
        """计算技术指标"""
        try:
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 计算移动平均线
            ma_fast = df.ta.sma(length=self.ma_fast)
            ma_slow = df.ta.sma(length=self.ma_slow)
            
            # 计算RSI
            rsi = df.ta.rsi(length=self.rsi_period)
            
            return {
                'ma_fast': ma_fast.iloc[-1],
                'ma_slow': ma_slow.iloc[-1],
                'rsi': rsi.iloc[-1],
                'close': df['close'].iloc[-1]
            }
            
        except Exception as e:
            self.logger.error(f"计算技术指标异常: {e}")
            return None

    def _generate_signal(self, symbol: str, indicators: Dict) -> Optional[Dict]:
        """生成交易信号"""
        if not indicators:
            return None

        try:
            ma_fast = indicators['ma_fast']
            ma_slow = indicators['ma_slow']
            rsi = indicators['rsi']
            current_price = indicators['close']

            signal = None

            # 检查是否有持仓
            if symbol in self.positions:
                position = self.positions[symbol]
                entry_price = position['entry_price']
                
                # 检查止盈止损
                if position['side'] == 'long':
                    profit_ratio = (Decimal(str(current_price)) - entry_price) / entry_price
                    if profit_ratio >= self.take_profit or profit_ratio <= -self.stop_loss:
                        signal = {'action': 'close', 'symbol': symbol}
                else:
                    profit_ratio = (entry_price - Decimal(str(current_price))) / entry_price
                    if profit_ratio >= self.take_profit or profit_ratio <= -self.stop_loss:
                        signal = {'action': 'close', 'symbol': symbol}

            # 生成开仓信号
            elif ma_fast > ma_slow and rsi < self.rsi_oversold:
                signal = {
                    'action': 'buy',
                    'symbol': symbol,
                    'price': current_price
                }
            elif ma_fast < ma_slow and rsi > self.rsi_overbought:
                signal = {
                    'action': 'sell',
                    'symbol': symbol,
                    'price': current_price
                }

            return signal

        except Exception as e:
            self.logger.error(f"生成交易信号异常: {e}")
            return None

    async def on_tick(self):
        """定时检查持仓状态"""
        try:
            for symbol in list(self.positions.keys()):
                ticker = await self.bot.okx.fetch_ticker(symbol)
                current_price = Decimal(str(ticker['last']))
                position = self.positions[symbol]
                
                # 检查止盈止损
                if position['side'] == 'long':
                    profit_ratio = (current_price - position['entry_price']) / position['entry_price']
                else:
                    profit_ratio = (position['entry_price'] - current_price) / position['entry_price']
                
                if profit_ratio >= self.take_profit or profit_ratio <= -self.stop_loss:
                    await self.execute({
                        'action': 'close',
                        'symbol': symbol
                    })
                    
        except Exception as e:
            self.logger.error(f"定时检查异常: {e}")
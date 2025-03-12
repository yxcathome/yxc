                # 更新风险指标
                risk_metrics = await self._calculate_risk_metrics(position)
                if risk_metrics:
                    position['risk_metrics'] = risk_metrics
                    
                # 检查是否需要平仓
                if await self._should_close_position(position):
                    await self.close_position(position_id, 'risk_trigger')
                    
        except Exception as e:
            self.logger.error(f"更新持仓状态失败: {e}")
            
    async def _load_positions(self):
        """加载持仓数据"""
        try:
            # 从数据库加载持仓
            positions = await self.bot.database.load_positions()
            if positions:
                for position in positions:
                    if position['status'] == 'open':
                        self.positions[position['id']] = position
                    else:
                        self.position_history[position['id']] = position
                        
            self.logger.info(f"加载持仓数据完成: {len(self.positions)} 个活跃持仓")
            
        except Exception as e:
            self.logger.error(f"加载持仓数据失败: {e}")
            
    async def _monitor_positions(self):
        """监控持仓状态"""
        while True:
            try:
                await self.update_positions()
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"监控持仓状态异常: {e}")
                await asyncio.sleep(5)
                
    async def _monitor_orders(self):
        """监控订单状态"""
        while True:
            try:
                for order_id, order_info in list(self.active_orders.items()):
                    exchange_name = order_info['order']['exchange']
                    symbol = order_info['order']['symbol']
                    
                    # 更新订单状态
                    updated_order = await self.bot.exchanges[exchange_name].fetch_order(
                        order_id,
                        symbol
                    )
                    
                    if updated_order:
                        order_info['order'].update(updated_order)
                        
                        # 如果订单完成，移至历史记录
                        if updated_order['status'] in ['closed', 'canceled', 'expired']:
                            self.order_history[order_id] = order_info
                            del self.active_orders[order_id]
                            
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"监控订单状态异常: {e}")
                await asyncio.sleep(5)
                
    async def _calculate_pnl(self, position: Dict, close_orders: Dict) -> Optional[Decimal]:
        """计算已实现盈亏"""
        try:
            total_pnl = Decimal('0')
            
            for exchange_name, order in position['orders'].items():
                if exchange_name not in close_orders:
                    continue
                    
                close_order = close_orders[exchange_name]
                
                # 计算每个交易所的盈亏
                entry_price = Decimal(str(order['price']))
                exit_price = Decimal(str(close_order['price']))
                size = Decimal(str(order['filled']))
                
                if position['direction'] == 'buy':
                    pnl = (exit_price - entry_price) * size
                else:
                    pnl = (entry_price - exit_price) * size
                    
                total_pnl += pnl
                
            return total_pnl
            
        except Exception as e:
            self.logger.error(f"计算已实现盈亏失败: {e}")
            return None
            
    async def _calculate_unrealized_pnl(self, position: Dict) -> Optional[Decimal]:
        """计算未实现盈亏"""
        try:
            total_pnl = Decimal('0')
            
            for exchange_name, order in position['orders'].items():
                exchange = self.bot.exchanges[exchange_name]
                
                # 获取当前市场价格
                ticker = await exchange.fetch_ticker(position['symbol'])
                if not ticker:
                    continue
                    
                current_price = Decimal(str(ticker['last']))
                entry_price = Decimal(str(order['price']))
                size = Decimal(str(order['filled']))
                
                # 计算未实现盈亏
                if position['direction'] == 'buy':
                    pnl = (current_price - entry_price) * size
                else:
                    pnl = (entry_price - current_price) * size
                    
                total_pnl += pnl
                
            return total_pnl
            
        except Exception as e:
            self.logger.error(f"计算未实现盈亏失败: {e}")
            return None
            
    async def _calculate_risk_metrics(self, position: Dict) -> Optional[Dict]:
        """计算风险指标"""
        try:
            metrics = {}
            
            # 计算持仓时间
            hold_time = (datetime.utcnow() - position['entry_time']).total_seconds()
            metrics['hold_time'] = hold_time
            
            # 计算回撤
            unrealized_pnl = position.get('unrealized_pnl', Decimal('0'))
            max_unrealized_pnl = position.get('max_unrealized_pnl', unrealized_pnl)
            
            if unrealized_pnl > max_unrealized_pnl:
                metrics['max_unrealized_pnl'] = unrealized_pnl
            else:
                metrics['max_unrealized_pnl'] = max_unrealized_pnl
                
            if max_unrealized_pnl > 0:
                drawdown = (max_unrealized_pnl - unrealized_pnl) / max_unrealized_pnl
                metrics['drawdown'] = drawdown
                
            # 计算收益率
            total_value = Decimal('0')
            for order in position['orders'].values():
                value = Decimal(str(order['price'])) * Decimal(str(order['filled']))
                total_value += value
                
            if total_value > 0:
                roi = unrealized_pnl / total_value
                metrics['roi'] = roi
                
            return metrics
            
        except Exception as e:
            self.logger.error(f"计算风险指标失败: {e}")
            return None
            
    async def _should_close_position(self, position: Dict) -> bool:
        """检查是否应该平仓"""
        try:
            risk_metrics = position.get('risk_metrics', {})
            
            # 检查止损条件
            if 'roi' in risk_metrics:
                roi = risk_metrics['roi']
                if roi < Decimal('-0.02'):  # -2%止损
                    return True
                    
            # 检查最大持仓时间
            if 'hold_time' in risk_metrics:
                hold_time = risk_metrics['hold_time']
                if hold_time > 3600:  # 1小时最大持仓时间
                    return True
                    
            # 检查最大回撤
            if 'drawdown' in risk_metrics:
                drawdown = risk_metrics['drawdown']
                if drawdown > Decimal('0.03'):  # 3%最大回撤
                    return True
                    
            return False
            
        except Exception as e:
            self.logger.error(f"检查平仓条件失败: {e}")
            return False
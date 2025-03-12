            # 获取当前价格
            current_prices = {}
            for exchange_name, exchange_data in data['tickers'].items():
                current_prices[exchange_name] = Decimal(str(exchange_data['last']))
                
            if not current_prices:
                return None
                
            # 计算平均价格
            avg_price = sum(current_prices.values()) / len(current_prices)
            
            # 根据波动率计算网格范围
            volatility = await self._calculate_volatility(symbol)
            if not volatility:
                volatility = Decimal('0.02')  # 默认2%波动率
                
            grid_width = volatility * 2  # 使用两倍波动率作为网格宽度
            
            return {
                'upper': avg_price * (1 + grid_width),
                'lower': avg_price * (1 - grid_width),
                'mid': avg_price
            }
            
        except Exception as e:
            self.logger.error(f"计算网格区间失败: {e}")
            return None
            
    async def _calculate_volatility(self, symbol: str) -> Optional[Decimal]:
        """计算波动率"""
        try:
            volatilities = []
            
            for exchange in self.exchange_manager.exchanges.values():
                # 获取K线数据
                klines = await exchange.fetch_ohlcv(symbol, '1h', limit=24)
                if not klines:
                    continue
                    
                # 计算收益率序列
                returns = []
                for i in range(1, len(klines)):
                    prev_close = Decimal(str(klines[i-1][4]))
                    curr_close = Decimal(str(klines[i][4]))
                    returns.append((curr_close - prev_close) / prev_close)
                    
                # 计算标准差
                if returns:
                    mean = sum(returns) / len(returns)
                    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
                    volatility = Decimal(str(variance ** 0.5))
                    volatilities.append(volatility)
                    
            if volatilities:
                return sum(volatilities) / len(volatilities)
                
            return None
            
        except Exception as e:
            self.logger.error(f"计算波动率失败: {e}")
            return None
            
    async def _monitor_grids(self):
        """监控网格状态"""
        while self.active:
            try:
                for symbol, grid in list(self.grids.items()):
                    # 更新网格订单状态
                    await self._update_grid_orders(symbol, grid)
                    
                    # 检查是否需要重新平衡网格
                    if await self._should_rebalance_grid(symbol, grid):
                        await self._rebalance_grid(symbol, grid)
                        
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"监控网格状态异常: {e}")
                await asyncio.sleep(5)
                
    async def _update_grid_orders(self, symbol: str, grid: Dict):
        """更新网格订单"""
        try:
            for exchange_name, orders in list(grid['orders'].items()):
                exchange = self.exchange_manager.exchanges[exchange_name]
                
                # 更新订单状态
                for order_id, order_info in list(orders.items()):
                    order = await exchange.fetch_order(order_id, symbol)
                    if order:
                        if order['status'] == 'closed':
                            # 移除已完成的订单
                            del orders[order_id]
                            
                            # 创建对手方向的订单
                            await self._create_counter_order(
                                symbol,
                                exchange_name,
                                order,
                                grid
                            )
                        elif order['status'] == 'canceled':
                            # 移除已取消的订单
                            del orders[order_id]
                            
        except Exception as e:
            self.logger.error(f"更新网格订单失败: {e}")
            
    async def _should_rebalance_grid(self, symbol: str, grid: Dict) -> bool:
        """检查是否需要重新平衡网格"""
        try:
            # 获取当前价格
            current_price = None
            for exchange in self.exchange_manager.exchanges.values():
                ticker = await exchange.fetch_ticker(symbol)
                if ticker:
                    current_price = Decimal(str(ticker['last']))
                    break
                    
            if not current_price:
                return False
                
            # 检查价格是否超出网格范围
            if current_price < grid['range']['lower'] * Decimal('0.95'):
                return True
            if current_price > grid['range']['upper'] * Decimal('1.05'):
                return True
                
            # 检查网格订单数量
            total_orders = sum(
                len(orders) for orders in grid['orders'].values()
            )
            if total_orders < self.grid_levels / 2:  # 如果订单数量少于一半
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"检查网格平衡失败: {e}")
            return False
            
    async def _rebalance_grid(self, symbol: str, grid: Dict):
        """重新平衡网格"""
        try:
            # 取消所有活跃订单
            for exchange_name, orders in grid['orders'].items():
                exchange = self.exchange_manager.exchanges[exchange_name]
                for order_id in orders:
                    await exchange.cancel_order(order_id, symbol)
                    
            # 重新计算网格区间
            data = {
                'tickers': {}
            }
            for exchange_name, exchange in self.exchange_manager.exchanges.items():
                ticker = await exchange.fetch_ticker(symbol)
                if ticker:
                    data['tickers'][exchange_name] = ticker
                    
            new_range = await self._calculate_grid_range(symbol, data)
            if not new_range:
                return
                
            # 更新网格范围
            grid['range'] = new_range
            
            # 创建新的网格订单
            await self._create_grid_orders(symbol, grid)
            
            self.logger.info(f"重新平衡网格完成: {symbol}")
            
        except Exception as e:
            self.logger.error(f"重新平衡网格失败: {e}")
            
    async def _create_grid_orders(self, symbol: str, grid: Dict):
        """创建网格订单"""
        try:
            grid_range = grid['range']
            grid_size = grid['size']
            
            # 计算网格价格
            price_step = (grid_range['upper'] - grid_range['lower']) / (self.grid_levels - 1)
            grid_prices = [
                grid_range['lower'] + price_step * i
                for i in range(self.grid_levels)
            ]
            
            # 在每个交易所创建订单
            for exchange_name, exchange in self.exchange_manager.exchanges.items():
                if exchange_name not in grid['orders']:
                    grid['orders'][exchange_name] = {}
                    
                # 创建买单
                for price in grid_prices[:-1]:  # 除了最高价
                    order = await exchange.create_order(
                        symbol=symbol,
                        order_type='limit',
                        side='buy',
                        amount=grid_size,
                        price=price
                    )
                    if order:
                        grid['orders'][exchange_name][order['id']] = order
                        
                # 创建卖单
                for price in grid_prices[1:]:  # 除了最低价
                    order = await exchange.create_order(
                        symbol=symbol,
                        order_type='limit',
                        side='sell',
                        amount=grid_size,
                        price=price
                    )
                    if order:
                        grid['orders'][exchange_name][order['id']] = order
                        
        except Exception as e:
            self.logger.error(f"创建网格订单失败: {e}")
            
    async def _create_counter_order(self, symbol: str, exchange_name: str,
                                  filled_order: Dict, grid: Dict):
        """创建对手方向订单"""
        try:
            exchange = self.exchange_manager.exchanges[exchange_name]
            
            # 计算对手方向价格
            filled_price = Decimal(str(filled_order['price']))
            if filled_order['side'] == 'buy':
                counter_price = filled_price * (1 + self.grid_spread)
                counter_side = 'sell'
            else:
                counter_price = filled_price * (1 - self.grid_spread)
                counter_side = 'buy'
                
            # 创建对手方向订单
            order = await exchange.create_order(
                symbol=symbol,
                order_type='limit',
                side=counter_side,
                amount=grid['size'],
                price=counter_price
            )
            
            if order:
                grid['orders'][exchange_name][order['id']] = order
                
        except Exception as e:
            self.logger.error(f"创建对手方向订单失败: {e}")
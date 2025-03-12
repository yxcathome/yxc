                    break
                    
            if not current_price:
                return None
                
            # 根据市场条件调整网格参数
            trend_strength = market_condition['trend_strength']
            volatility = market_condition['volatility']
            volume_trend = market_condition['volume_trend']
            
            # 调整网格层数
            if trend_strength > Decimal('0.7'):
                # 趋势强烈时减少网格层数
                grid_levels = self.base_grid_levels - 2
            elif volatility > self.vol_threshold:
                # 波动率高时增加网格层数
                grid_levels = int(self.base_grid_levels * float(self.grid_expansion_factor))
            else:
                grid_levels = self.base_grid_levels
                
            # 调整网格间距
            base_spread = max(volatility / 2, self.min_grid_spread)
            if volume_trend > Decimal('0.5'):
                # 成交量上升时扩大网格间距
                grid_spread = base_spread * self.grid_expansion_factor
            else:
                grid_spread = base_spread
                
            # 计算网格范围
            grid_range = await self._calculate_grid_range(
                current_price,
                grid_spread,
                grid_levels,
                volatility
            )
            
            return {
                'current_price': current_price,
                'grid_levels': grid_levels,
                'grid_spread': grid_spread,
                'grid_range': grid_range
            }
            
        except Exception as e:
            self.logger.error(f"生成网格配置失败: {e}")
            return None
            
    async def _calculate_trend_strength(self, symbol: str) -> Optional[Decimal]:
        """计算趋势强度"""
        try:
            trend_values = []
            
            for exchange in self.exchange_manager.exchanges.values():
                # 获取K线数据
                klines = await exchange.fetch_ohlcv(symbol, '1h', limit=24)
                if not klines:
                    continue
                    
                # 计算移动平均线
                closes = [Decimal(str(k[4])) for k in klines]
                ma_short = sum(closes[-6:]) / 6    # 6小时MA
                ma_long = sum(closes) / len(closes) # 24小时MA
                
                # 计算趋势强度
                if ma_long > 0:
                    trend = abs(ma_short - ma_long) / ma_long
                    trend_values.append(trend)
                    
            if trend_values:
                return sum(trend_values) / len(trend_values)
                
            return None
            
        except Exception as e:
            self.logger.error(f"计算趋势强度失败: {e}")
            return None
            
    async def _calculate_volume_trend(self, symbol: str) -> Optional[Decimal]:
        """计算成交量趋势"""
        try:
            volume_trends = []
            
            for exchange in self.exchange_manager.exchanges.values():
                # 获取K线数据
                klines = await exchange.fetch_ohlcv(symbol, '1h', limit=24)
                if not klines:
                    continue
                    
                # 计算成交量MA
                volumes = [Decimal(str(k[5])) for k in klines]
                vol_ma_short = sum(volumes[-6:]) / 6    # 6小时MA
                vol_ma_long = sum(volumes) / len(volumes) # 24小时MA
                
                # 计算成交量趋势
                if vol_ma_long > 0:
                    trend = (vol_ma_short - vol_ma_long) / vol_ma_long
                    volume_trends.append(trend)
                    
            if volume_trends:
                return sum(volume_trends) / len(volume_trends)
                
            return None
            
        except Exception as e:
            self.logger.error(f"计算成交量趋势失败: {e}")
            return None
            
    async def _calculate_grid_range(self, current_price: Decimal, grid_spread: Decimal,
                                  grid_levels: int, volatility: Decimal) -> Dict:
        """计算网格范围"""
        try:
            # 根据波动率调整范围
            range_width = max(volatility * 2, grid_spread * grid_levels)
            
            # 计算上下限
            upper = current_price * (1 + range_width)
            lower = current_price * (1 - range_width)
            
            # 确保网格间距合理
            price_step = (upper - lower) / (grid_levels - 1)
            if price_step < current_price * self.min_grid_spread:
                # 如果网格间距过小，调整范围
                price_step = current_price * self.min_grid_spread
                half_range = price_step * (grid_levels - 1) / 2
                upper = current_price + half_range
                lower = current_price - half_range
                
            return {
                'upper': upper,
                'lower': lower,
                'step': price_step
            }
            
        except Exception as e:
            self.logger.error(f"计算网格范围失败: {e}")
            return None
            
    async def _monitor_market_conditions(self):
        """监控市场条件"""
        while self.active:
            try:
                for symbol in self.grids:
                    # 分析市场条件
                    data = await self._get_market_data(symbol)
                    if not data:
                        continue
                        
                    market_condition = await self._analyze_market_condition(symbol, data)
                    if not market_condition:
                        continue
                        
                    # 检查是否需要调整网格
                    if await self._should_adjust_grid(symbol, market_condition):
                        await self._adjust_grid(symbol, market_condition)
                        
                await asyncio.sleep(300)  # 每5分钟检查一次
                
            except Exception as e:
                self.logger.error(f"监控市场条件异常: {e}")
                await asyncio.sleep(5)
                
    async def _get_market_data(self, symbol: str) -> Optional[Dict]:
        """获取市场数据"""
        try:
            data = {
                'tickers': {},
                'orderbooks': {},
                'trades': {}
            }
            
            for exchange in self.exchange_manager.exchanges.values():
                ticker = await exchange.fetch_ticker(symbol)
                orderbook = await exchange.fetch_order_book(symbol)
                trades = await exchange.fetch_trades(symbol)
                
                if ticker:
                    data['tickers'][exchange.name] = ticker
                if orderbook:
                    data['orderbooks'][exchange.name] = orderbook
                if trades:
                    data['trades'][exchange.name] = trades
                    
            return data if data['tickers'] else None
            
        except Exception as e:
            self.logger.error(f"获取市场数据失败: {e}")
            return None
            
    async def _should_adjust_grid(self, symbol: str, market_condition: Dict) -> bool:
        """检查是否需要调整网格"""
        try:
            grid = self.grids[symbol]
            
            # 检查波动率变化
            if market_condition['volatility'] > grid['volatility'] * Decimal('1.5'):
                return True
                
            # 检查趋势强度变化
            if abs(market_condition['trend_strength'] - grid['trend_strength']) > Decimal('0.3'):
                return True
                
            # 检查价格是否接近网格边界
            current_price = None
            for exchange in self.exchange_manager.exchanges.values():
                ticker = await exchange.fetch_ticker(symbol)
                if ticker:
                    current_price = Decimal(str(ticker['last']))
                    break
                    
            if current_price:
                grid_range = grid['config']['grid_range']
                if current_price < grid_range['lower'] * Decimal('1.05') or \
                   current_price > grid_range['upper'] * Decimal('0.95'):
                    return True
                    
            return False
            
        except Exception as e:
            self.logger.error(f"检查网格调整失败: {e}")
            return False
            
    async def _adjust_grid(self, symbol: str, market_condition: Dict):
        """调整网格"""
        try:
            # 生成新的网格配置
            grid_config = await self._generate_grid_config(symbol, market_condition)
            if not grid_config:
                return
                
            # 取消现有订单
            grid = self.grids[symbol]
            for exchange_name, orders in grid['orders'].items():
                exchange = self.exchange_manager.exchanges[exchange_name]
                for order_id in orders:
                    await exchange.cancel_order(order_id, symbol)
                    
            # 更新网格配置
            grid['config'] = grid_config
            grid['volatility'] = market_condition['volatility']
            grid['trend_strength'] = market_condition['trend_strength']
            
            # 创建新的网格订单
            await self._create_grid_orders(symbol, grid)
            
            self.logger.info(f"调整网格完成: {symbol}")
            
        except Exception as e:
            self.logger.error(f"调整网格失败: {e}")
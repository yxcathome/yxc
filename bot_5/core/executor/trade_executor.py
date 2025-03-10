    async def _get_valid_price(self, exchange_name: str, symbol: str, 
                             side: str) -> Optional[Decimal]:
        """获取有效价格"""
        try:
            exchange = self.exchange_manager.exchanges[exchange_name]
            price_info = await exchange.get_best_price(symbol)
            if not price_info:
                return None
                
            # 根据方向选择买卖价
            base_price = price_info['ask'] if side == 'buy' else price_info['bid']
            
            # 检查深度
            orderbook = await exchange.fetch_order_book(symbol)
            if not orderbook:
                return None
                
            # 计算滑点
            spread = (price_info['ask'] - price_info['bid']) / price_info['bid']
            if spread > self.max_slippage:
                self.logger.warning(f"价差过大: {spread}")
                return None
                
            # 返回调整后的价格
            if side == 'buy':
                return base_price * (1 + self.max_slippage / 2)
            else:
                return base_price * (1 - self.max_slippage / 2)
                
        except Exception as e:
            self.logger.error(f"获取有效价格失败: {e}")
            return None
            
    async def _calculate_realized_pnl(self, position: Dict, 
                                    close_orders: Dict) -> Optional[Decimal]:
        """计算已实现盈亏"""
        try:
            total_pnl = Decimal('0')
            
            for exchange_name, order in position['info']['orders'].items():
                if exchange_name not in close_orders:
                    continue
                    
                close_order = close_orders[exchange_name]
                
                entry_price = Decimal(str(order['price']))
                exit_price = Decimal(str(close_order['executed_price']))
                amount = Decimal(str(order['amount']))
                
                if order['side'] == 'buy':
                    pnl = (exit_price - entry_price) * amount
                else:
                    pnl = (entry_price - exit_price) * amount
                    
                total_pnl += pnl
                
            return total_pnl
            
        except Exception as e:
            self.logger.error(f"计算已实现盈亏失败: {e}")
            return None
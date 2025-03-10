    def _validate_prices(self, prices: Dict[str, Decimal]) -> bool:
        """验证价格是否合理"""
        if not prices:
            return False

        price_list = list(prices.values())
        avg_price = sum(price_list) / len(price_list)
        
        # 检查价格偏差是否在允许范围内 (0.1%)
        for price in price_list:
            deviation = abs(price - avg_price) / avg_price
            if deviation > Decimal('0.001'):
                return False
                
        return True

    async def update_metrics(self, trade_result: Dict):
        """更新策略性能指标"""
        try:
            self.performance_metrics['total_trades'] += 1
            pnl = trade_result['realized_pnl']
            
            if pnl > 0:
                self.performance_metrics['winning_trades'] += 1
            else:
                self.performance_metrics['losing_trades'] += 1
                
            self.performance_metrics['total_profit'] += pnl
            
            # 更新最大回撤
            if pnl < 0:
                current_drawdown = abs(pnl)
                self.performance_metrics['max_drawdown'] = max(
                    self.performance_metrics['max_drawdown'],
                    current_drawdown
                )
                
            # 计算夏普比率
            await self._calculate_sharpe_ratio()
            
        except Exception as e:
            self.logger.error(f"更新性能指标失败: {e}")

    async def _calculate_sharpe_ratio(self):
        """计算夏普比率"""
        try:
            if self.performance_metrics['total_trades'] < 2:
                return
                
            # 获取过去的交易记录
            trades = await self._get_historical_trades()
            if not trades:
                return
                
            # 计算收益率序列
            returns = [trade['return_rate'] for trade in trades]
            avg_return = sum(returns) / len(returns)
            
            # 计算标准差
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = Decimal(str(variance)).sqrt()
            
            # 计算夏普比率 (假设无风险利率为3%)
            risk_free_rate = Decimal('0.03')
            if std_dev > 0:
                self.performance_metrics['sharpe_ratio'] = \
                    (avg_return - risk_free_rate) / std_dev
                    
        except Exception as e:
            self.logger.error(f"计算夏普比率失败: {e}")
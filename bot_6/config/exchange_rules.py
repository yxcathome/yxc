                        'step_size': Decimal('0.001')
                    }
                },
                'EOS-USDT': {
                    'min_amount': Decimal('0.1'),
                    'max_amount': Decimal('10000'),
                    'amount_precision': 1,
                    'price_precision': 3,
                    'min_notional': Decimal('5'),
                    'max_leverage': 50,
                    'maintenance_margin': Decimal('0.02'),
                    'maker_fee': Decimal('0.0002'),
                    'taker_fee': Decimal('0.0005'),
                    'price_filters': {
                        'min_price': Decimal('0.1'),
                        'max_price': Decimal('1000'),
                        'tick_size': Decimal('0.001')
                    },
                    'quantity_filters': {
                        'min_qty': Decimal('0.1'),
                        'max_qty': Decimal('10000'),
                        'step_size': Decimal('0.1')
                    }
                }
            }
        elif self.exchange_id == 'binance':
            return {
                'BTCUSDT': {
                    'min_amount': Decimal('0.00001'),
                    'max_amount': Decimal('100'),
                    'amount_precision': 5,
                    'price_precision': 2,
                    'min_notional': Decimal('10'),
                    'max_leverage': 125,
                    'maintenance_margin': Decimal('0.004'),
                    'maker_fee': Decimal('0.0002'),
                    'taker_fee': Decimal('0.0004'),
                    'price_filters': {
                        'min_price': Decimal('100'),
                        'max_price': Decimal('1000000'),
                        'tick_size': Decimal('0.1')
                    },
                    'quantity_filters': {
                        'min_qty': Decimal('0.00001'),
                        'max_qty': Decimal('100'),
                        'step_size': Decimal('0.00001')
                    }
                },
                'ETHUSDT': {
                    'min_amount': Decimal('0.0001'),
                    'max_amount': Decimal('1000'),
                    'amount_precision': 4,
                    'price_precision': 2,
                    'min_notional': Decimal('10'),
                    'max_leverage': 100,
                    'maintenance_margin': Decimal('0.008'),
                    'maker_fee': Decimal('0.0002'),
                    'taker_fee': Decimal('0.0004'),
                    'price_filters': {
                        'min_price': Decimal('10'),
                        'max_price': Decimal('100000'),
                        'tick_size': Decimal('0.01')
                    },
                    'quantity_filters': {
                        'min_qty': Decimal('0.0001'),
                        'max_qty': Decimal('1000'),
                        'step_size': Decimal('0.0001')
                    }
                },
                'EOSUSDT': {
                    'min_amount': Decimal('0.01'),
                    'max_amount': Decimal('10000'),
                    'amount_precision': 2,
                    'price_precision': 3,
                    'min_notional': Decimal('10'),
                    'max_leverage': 75,
                    'maintenance_margin': Decimal('0.01'),
                    'maker_fee': Decimal('0.0002'),
                    'taker_fee': Decimal('0.0004'),
                    'price_filters': {
                        'min_price': Decimal('0.1'),
                        'max_price': Decimal('1000'),
                        'tick_size': Decimal('0.001')
                    },
                    'quantity_filters': {
                        'min_qty': Decimal('0.01'),
                        'max_qty': Decimal('10000'),
                        'step_size': Decimal('0.01')
                    }
                }
            }
        return {}

    def get_symbol_rules(self, symbol: str) -> Optional[Dict]:
        """获取交易对规则"""
        return self.rules.get(symbol)

    def check_order_quantity(self, symbol: str, quantity: Decimal) -> bool:
        """检查订单数量是否有效"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return False

        filters = rules['quantity_filters']
        if quantity < filters['min_qty'] or quantity > filters['max_qty']:
            return False

        # 检查步长
        remainder = quantity % filters['step_size']
        return remainder == 0

    def check_order_price(self, symbol: str, price: Decimal) -> bool:
        """检查订单价格是否有效"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return False

        filters = rules['price_filters']
        if price < filters['min_price'] or price > filters['max_price']:
            return False

        # 检查价格精度
        remainder = price % filters['tick_size']
        return remainder == 0

    def check_notional_value(self, symbol: str, quantity: Decimal, price: Decimal) -> bool:
        """检查订单名义价值是否有效"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return False

        notional = quantity * price
        return notional >= rules['min_notional']

    def normalize_quantity(self, symbol: str, quantity: Decimal) -> Optional[Decimal]:
        """标准化订单数量"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return None

        filters = rules['quantity_filters']
        if quantity < filters['min_qty']:
            return None
        if quantity > filters['max_qty']:
            quantity = filters['max_qty']

        # 调整到步长
        steps = int(quantity / filters['step_size'])
        return filters['step_size'] * Decimal(str(steps))

    def normalize_price(self, symbol: str, price: Decimal) -> Optional[Decimal]:
        """标准化订单价格"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return None

        filters = rules['price_filters']
        if price < filters['min_price']:
            return filters['min_price']
        if price > filters['max_price']:
            return filters['max_price']

        # 调整到价格精度
        ticks = int(price / filters['tick_size'])
        return filters['tick_size'] * Decimal(str(ticks))

    def get_fees(self, symbol: str) -> Dict[str, Decimal]:
        """获取交易手续费"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return {'maker': Decimal('0'), 'taker': Decimal('0')}

        return {
            'maker': rules['maker_fee'],
            'taker': rules['taker_fee']
        }

    def get_leverage_tiers(self, symbol: str) -> Dict:
        """获取杠杆档位"""
        rules = self.get_symbol_rules(symbol)
        if not rules:
            return {}

        return {
            'max_leverage': rules['max_leverage'],
            'maintenance_margin': rules['maintenance_margin']
        }
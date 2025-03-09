from decimal import Decimal
from typing import Dict

class ProfitCalculator:
    def __init__(self, bot):
        self.bot = bot

    def calc_dynamic_spread(self, ex1: str, ex2: str, symbol1: str, symbol2: str) -> Decimal:
        fee_total = self.bot.fees_config[ex1]['taker'] + self.bot.fees_config[ex2]['taker']
        funding_fee = self.bot.funding_fees[ex1].get(symbol1, Decimal('0')) + self.bot.funding_fees[ex2].get(symbol2, Decimal('0'))
        return fee_total + funding_fee + self.bot.trade_config['min_profit_margin']
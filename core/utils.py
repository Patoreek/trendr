import numpy as np
from config.bot_config import known_currencies, binance_client, COLORS
from decimal import Decimal

def split_market_pair(market_pair):
    for i in range(3, len(market_pair) + 1):
        base = market_pair[:i]
        quote = market_pair[i:]
        if base in known_currencies and quote in known_currencies:
            return base, quote
    return market_pair, 'Unknown'

def convert_usd_to_quantity(symbol, amount_in_usd):
    price = Decimal(binance_client.get_symbol_ticker(symbol=symbol)["price"])
    return amount_in_usd / price

def get_notional_limit(symbol):
    symbol_info = binance_client.get_symbol_info(symbol)
    for filter in symbol_info['filters']:
        if filter['filterType'] == 'MIN_NOTIONAL':
            return Decimal(filter['minNotional'])
    return Decimal('0.0')

def get_quantity_precision(symbol):
    symbol_info = binance_client.get_symbol_info(symbol)
    for filter in symbol_info['filters']:
        if filter['filterType'] == 'LOT_SIZE':
            min_qty = Decimal(filter['minQty'])
            step_size = Decimal(filter['stepSize'])
            return min_qty, step_size
    return Decimal('1.0'), Decimal('1.0')

def adjust_quantity(quantity, min_qty, step_size):
    adjusted = max(min_qty, quantity)
    return adjusted - (adjusted % step_size)

def colorize_cli_text(text, color=None):
    # If color is provided, use it
    if color and color in COLORS:
        return f"{COLORS[color]}{text}{COLORS['reset']}"
    
    # If no color is provided, check if the text matches any color keys
    if text in COLORS:
        return f"{COLORS[text]}{text}{COLORS['reset']}"
    
    # Return text as is if no color is found
    return f"{text}"
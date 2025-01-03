from decimal import Decimal
from dotenv import load_dotenv
from binance.client import Client
import os

load_dotenv()

bot_data = {
    "running": False,
    "symbol": "",
    "fiat_stablecoin": 'USDT',
    "base_currency": '',
    "quote_currency": '',
    "interval": "",
    "trade_allocation": 0,
    "starting_trade_amount": Decimal('100.0'),
    "current_trade_amount": Decimal('100.0'),
    "base_starting_currency_quantity": Decimal('0.0'),
    "base_current_currency_quantity": Decimal('0.0'),
    "quote_current_currency_quantity": Decimal('0.0'),
    "currency_quantity_precision": 0,
    "previous_market_price": Decimal('0.0'),
    "current_market_price": Decimal('0.0'),
    "total_trades": 0,
    "successful_trades": 0,
    "failed_trades": 0,
    "total_profit_loss": 0,
    "daily_log": [],
}

# Initialize Binance client
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY_TESTNET")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET_TESTNET")
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET, testnet=True)
binance_client.API_URL = 'https://testnet.binance.vision/api'

# Reset color
COLOR_RESET = "\033[0m"

# Action colors
COLOR_GREEN_BG_WHITE_TEXT = "\033[42;97m"  # Buy
COLOR_RED_BG_WHITE_TEXT = "\033[41;97m"    # Sell
COLOR_YELLOW_BG_WHITE_TEXT = "\033[43;97m" # Hold

# Neutral color
COLOR_BLUE_BG_WHITE_TEXT = "\033[44;97m"   # Neutral info
COLOR_MAGENTA_BG_WHITE_TEXT = "\033[45;97m"  # Failed Action / Error

# Crypto colors (only text color, no background)
COLOR_BTC = "\033[38;5;214m"  # BTC - text-orange-500
COLOR_ETH = "\033[38;5;93m"   # ETH - text-purple-600
COLOR_XRP = "\033[38;5;240m"  # XRP - text-blue-gray-600
COLOR_ADA = "\033[38;5;58m"   # ADA - text-indigo-600
COLOR_SOL = "\033[38;5;50m"   # SOL - text-cyan-500
COLOR_LTC = "\033[38;5;235m"  # LTC - text-gray-400
COLOR_BNB = "\033[38;5;220m"  # BNB - text-yellow-500
COLOR_DOGE = "\033[38;5;220m" # DOGE - text-yellow-400
COLOR_MATIC = "\033[38;5;93m" # MATIC - text-purple-500
COLOR_USDT = "\033[38;5;34m"  # USDT - text-green-500

# Other colors
COLOR_BOTNAME = "\033[48;5;129m\033[97m"  # botname - bg-purple-700 text-white
COLOR_SYMBOL = "\033[48;5;220m\033[30m"  # symbol - bg-yellow-400 text-black
COLOR_PROFIT = "\033[38;5;34m"  # Profit - text-green-500
COLOR_LOSS = "\033[38;5;196m"   # Loss - text-red-500
COLOR_PROFIT_BG = "\033[48;5;34m\033[97m"  # Profit with bg - green background, white text
COLOR_LOSS_BG = "\033[48;5;196m\033[97m"   # Loss with bg - red background, white text


COLORS = {
    "botname": COLOR_BOTNAME,               # Botname - purple-700
    "symbol": COLOR_SYMBOL,                 # Symbol - yellow-400
    "reset": COLOR_RESET,                   # Reset color
    "buy": COLOR_GREEN_BG_WHITE_TEXT,       # Green background, white text
    "sell": COLOR_RED_BG_WHITE_TEXT,        # Red background, white text
    "hold": COLOR_YELLOW_BG_WHITE_TEXT,     # Yellow background, white text
    "neutral": COLOR_BLUE_BG_WHITE_TEXT,    # Blue background, white text
    "error": COLOR_MAGENTA_BG_WHITE_TEXT,   # Magenta background, white text
    "profit": COLOR_PROFIT,                 # Profit - green text
    "loss": COLOR_LOSS,                     # Loss - red text
    "profit_bg": COLOR_PROFIT_BG,           # Profit with background - green bg, white text
    "loss_bg": COLOR_LOSS_BG,               # Loss with background - red bg, white text
    "BTC": COLOR_BTC,                       # BTC - Bitcoin
    "ETH": COLOR_ETH,                       # ETH - Ethereum
    "XRP": COLOR_XRP,                       # XRP - Ripple
    "ADA": COLOR_ADA,                       # ADA - Cardano
    "SOL": COLOR_SOL,                       # SOL - Solana
    "LTC": COLOR_LTC,                       # LTC - Litecoin
    "BNB": COLOR_BNB,                       # BNB - Binance Coin
    "DOGE": COLOR_DOGE,                     # DOGE - Dogecoin
    "MATIC": COLOR_MATIC,                   # MATIC - Polygon
    "USDT": COLOR_USDT                      # USDT - Tether
}

known_currencies = {
    'BTC', 'ETH', 'XRP', 'ADA', 'SOL', 'LTC', 'BNB', 'DOGE', 'MATIC', 'USDT'
}
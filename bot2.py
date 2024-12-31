import json
from flask import Flask, jsonify, request
from binance.client import Client
import numpy as np
import threading
import time
import os
from dotenv import load_dotenv
from decimal import Decimal, getcontext
from datetime import datetime


getcontext().prec = 8  # Set precision to 8 for financial calculations

app = Flask(__name__)
load_dotenv()

bot_data = {
    "running": False,
    "symbol": "",
    "fiat": 'USD $',  # This is only for USD currently. Integration needed for other fiats
    "base_currency": '',  # Example base currency (XRP)
    "quote_currency": '',  # Example quote currency (USDT)
    "interval": "",
    "trade_allocation": 0,
    "starting_trade_amount": Decimal('100.0'),  # In USD
    "current_trade_amount": Decimal('100.0'),  # In USD
    "base_starting_currency_quantity": Decimal('0.0'),  # e.g., XRP
    "base_current_currency_quantity": Decimal('0.0'),  # e.g., XRP
    "quote_current_currency_quantity": Decimal('0.0'),  # Amount of quote currency (USDT)
    "currency_quantity_precision": 0,
    "previous_market_price": Decimal('0.0'),
    "current_market_price": Decimal('0.0'),
    "total_trades": 0,
    "successful_trades": 0,
    "failed_trades": 0,
    "daily_log": [],  # Log of trades for the current day
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

known_currencies = {
    'BTC', 'ETH', 'XRP', 'ADA', 'SOL', 'LTC', 'BNB', 'DOGE', 'MATIC', 'USDT'
}

trading_thread = None

# Utility functions
def calculate_ema(prices, window):
    prices = np.array(prices)
    weights = np.exp(np.linspace(-1., 0., window))
    weights /= weights.sum()
    return np.convolve(prices, weights, mode='valid')[-1]

def split_market_pair(market_pair):
    for i in range(3, len(market_pair) + 1):  # Start from 3 as most base currencies are at least 3 chars
        base = market_pair[:i]
        quote = market_pair[i:]
        if base in known_currencies and quote in known_currencies:
            return base, quote
    return market_pair, 'Unknown'  # If no valid split found

def convert_usd_to_quantity(symbol, amount_in_usd):
    price = Decimal(binance_client.get_symbol_ticker(symbol=symbol)["price"])
    return amount_in_usd / price

def get_notional_limit(symbol):
    """
    Retrieve the minimum notional value for a trading pair.
    """
    symbol_info = binance_client.get_symbol_info(symbol)
    for filter in symbol_info['filters']:
        if filter['filterType'] == 'MIN_NOTIONAL':
            return Decimal(filter['minNotional'])
    return Decimal('0.0')

def get_quantity_precision(symbol):
    """
    Retrieve the precision and step size for a trading pair.
    """
    symbol_info = binance_client.get_symbol_info(symbol)
    for filter in symbol_info['filters']:
        if filter['filterType'] == 'LOT_SIZE':
            min_qty = Decimal(filter['minQty'])
            step_size = Decimal(filter['stepSize'])
            return min_qty, step_size
    return Decimal('1.0'), Decimal('1.0')

def adjust_quantity(quantity, min_qty, step_size):
    """
    Adjust quantity to meet minimum quantity and step size requirements.
    """
    adjusted = max(min_qty, quantity)
    return adjusted - (adjusted % step_size)

def buy_crypto(symbol, available_amount):
    try:
        min_notional = get_notional_limit(symbol)
        price = Decimal(binance_client.get_symbol_ticker(symbol=symbol)["price"])
        min_qty, step_size = get_quantity_precision(symbol)
        
        # Use trade allocation to determine amount to spend
        trade_amount = Decimal(bot_data["current_trade_amount"]) * (Decimal(bot_data["trade_allocation"]) / Decimal('100.0'))
        quantity = trade_amount / price
        adjusted_quantity = adjust_quantity(quantity, min_qty, step_size)
        required_quote_balance = adjusted_quantity * price
        
        # Check conditions and raise errors with colors
        if bot_data["quote_current_currency_quantity"] < required_quote_balance:
            raise ValueError(
                f"{COLOR_MAGENTA_BG_WHITE_TEXT}Insufficient {bot_data['quote_currency']} balance: required {required_quote_balance}, available {bot_data['quote_current_currency_quantity']}{COLOR_RESET}"
            )

        # Check if the trade amount meets the minimum notional value
        if adjusted_quantity * price < min_notional:
            raise ValueError(
                f"{COLOR_MAGENTA_BG_WHITE_TEXT}Trade amount {adjusted_quantity * price} is below minimum notional {min_notional}{COLOR_RESET}"
            )

        order = binance_client.order_market_buy(symbol=symbol, quantity=f"{adjusted_quantity:.8f}")
                
        # # Assuming fee rate is known or can be fetched, here's an example:
        fee_rate = Decimal('0.001')  # Example rate, adjust based on actual fees
        total_cost = adjusted_quantity * price
        fee = total_cost * fee_rate
        net_cost = total_cost + fee
        
        # Update bot_data after the buy
        bot_data["current_trade_amount"] -= net_cost
        bot_data["base_current_currency_quantity"] += adjusted_quantity
        bot_data["quote_current_currency_quantity"] -= total_cost
        
        bot_data["successful_trades"] += 1
        
        bot_data["daily_log"].append({
            "action": "Buy",
            "symbol": symbol,
            "price": float(price),
            "quantity": float(adjusted_quantity),
            "value": float(total_cost),
            "fee": float(fee),
            "net_value": float(net_cost),
            "timestamp": time.time(),
        })
        
        return order
    except Exception as e:
        print(f"Error placing buy order: {e}")
        bot_data["failed_trades"] += 1
        return False

def sell_crypto(symbol, available_quantity):
    try:
        min_notional = get_notional_limit(symbol)
        price = Decimal(binance_client.get_symbol_ticker(symbol=symbol)["price"])
        min_qty, step_size = get_quantity_precision(symbol)

        # Use trade allocation to determine quantity to sell
        trade_amount = Decimal(bot_data["current_trade_amount"]) * (Decimal(bot_data["trade_allocation"]) / Decimal('100.0'))
        quantity = min(trade_amount / price, available_quantity)  # Sell only what we have
        adjusted_quantity = adjust_quantity(quantity, min_qty, step_size)
        
        if bot_data["base_current_currency_quantity"] < adjusted_quantity:
            raise ValueError(f"Insufficient base currency balance: required {adjusted_quantity}, available {bot_data['base_current_currency_quantity']}")
            return false
        
        trade_value = adjusted_quantity * price
        if trade_value < min_notional:
            raise ValueError(f"Trade value {trade_value} is below minimum notional {min_notional}")
            return false

        order = binance_client.order_market_sell(symbol=symbol, quantity=f"{adjusted_quantity:.8f}")
        
        fee_rate = Decimal('0.001')  # Example rate, adjust based on actual fees
        fee = trade_value * fee_rate
        net_value = trade_value - fee

        # Update bot_data after the sell
        bot_data["current_trade_amount"] += net_value
        bot_data["base_current_currency_quantity"] -= adjusted_quantity
        bot_data["quote_current_currency_quantity"] += trade_value

        bot_data["base_current_currency_quantity"] = max(Decimal('0.0'), bot_data["base_current_currency_quantity"])

        bot_data["successful_trades"] += 1

        bot_data["daily_log"].append({
            "action": "Sell",
            "symbol": symbol,
            "price": float(price),
            "quantity": float(adjusted_quantity),
            "value": float(trade_value),
            "fee": float(fee),
            "net_value": float(net_value),
            "timestamp": time.time(),
        })
        return order
        # return order
    except Exception as e:
        print(f"Error placing sell order: {e}")
        bot_data["failed_trades"] += 1
        return False
    
def get_historical_data(symbol, interval, limit):
    klines = binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    return [float(kline[4]) for kline in klines]

def trading_loop():
    INTERVAL_TO_SECONDS = {
        "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400,
    }
    print(f"{COLOR_BLUE_BG_WHITE_TEXT} System Update: All systems operational. {COLOR_RESET}")
    total_profit_loss = 0
    
    while bot_data["running"]:
        try:
            symbol = bot_data["symbol"]
            interval = bot_data["interval"]
            wait_time = INTERVAL_TO_SECONDS.get(interval, 3600)
            prices = get_historical_data(symbol, interval, limit=50)
            short_ema = calculate_ema(prices, window=5)
            long_ema = calculate_ema(prices, window=20)
            print(f"{COLOR_BLUE_BG_WHITE_TEXT} Starting Trade | {symbol} | {interval} | Profit/Loss: {bot_data['fiat']}{total_profit_loss:.8f}  {COLOR_RESET}")
            print(f"""
                  bot_data["base_current_currency_quantity"]: {bot_data["base_current_currency_quantity"]}
                  bot_data["quote_current_currency_quantity"]: {bot_data["quote_current_currency_quantity"]}
                  S-EMA: {short_ema}
                  L-EMA: {long_ema}
                  Should Buy? {short_ema > long_ema}
                  Should Sell? {short_ema < long_ema}
                  """)
            if bot_data["base_current_currency_quantity"] > 0 and short_ema > long_ema and bot_data["quote_current_currency_quantity"] > 0:
                action = "Buy"
                color = COLOR_GREEN_BG_WHITE_TEXT
                available_amount = bot_data["current_trade_amount"]
                order = buy_crypto(symbol, available_amount)
            elif bot_data["base_current_currency_quantity"] > 0 and short_ema < long_ema:
                action = "Sell"
                color = COLOR_RED_BG_WHITE_TEXT
                available_quantity = bot_data["base_current_currency_quantity"]
                order = sell_crypto(symbol, available_quantity)
            else:
                # Determine why the bot is holding
                if bot_data["base_current_currency_quantity"] <= 0 and short_ema < long_ema:
                    hold_msg = f"Cannot [SELL]: insufficient {bot_data['base_currency']} funds. Holding..."
                elif bot_data["quote_current_currency_quantity"] <= 0 and short_ema > long_ema:
                    hold_msg = f"Cannot [BUY]: insufficient {bot_data['quote_currency']} funds. Holding..."
                else:
                    hold_msg = "Holding: Market conditions do not allow a trade."
                    
                action = "Hold"
                color = COLOR_MAGENTA_BG_WHITE_TEXT
                print(f"{color}{hold_msg}{COLOR_RESET}")
                color = COLOR_YELLOW_BG_WHITE_TEXT

            
            
            # Profit/Loss Calculation
            current_market_price = Decimal(prices[-1])
            # Convert base currency to USD
            btc_to_usd_price = Decimal(binance_client.get_symbol_ticker(symbol=f"{bot_data['base_currency']}USDT")["price"]) if bot_data["base_currency"] != "USDT" else Decimal('1.0')
            base_value_current = bot_data["base_current_currency_quantity"] * btc_to_usd_price
            # # # Convert quote currency to USD if it's not USDT
            quote_to_usd_price = Decimal('1.0') if bot_data["quote_currency"] == "USDT" else Decimal(binance_client.get_symbol_ticker(symbol=f"{bot_data['quote_currency']}USDT")["price"])
            quote_value_current = bot_data["quote_current_currency_quantity"] * quote_to_usd_price
            total_current_value_usd = base_value_current + quote_value_current
            if (action != "Hold"): 
                # Calculate profit/loss in USD
                total_profit_loss = total_current_value_usd - bot_data["starting_trade_amount"]

            
            # print(f"""
            # Starting Amount: {bot_data['starting_trade_amount']} {bot_data['fiat']}
            # Current Amount: {total_current_value_usd} {bot_data['fiat']}
            # ---
            # # {bot_data['base_currency']} Start Amount: {bot_data['base_starting_currency_quantity']:.8f}
            # # {bot_data['base_currency']} Current Amount: {bot_data['base_current_currency_quantity']:.8f}
            # # {bot_data['quote_currency']} Current Amount: {bot_data['quote_current_currency_quantity']:.8f}
            # # Total Profit/Loss (in USD): {total_profit_loss:.8f} USD
            # """)
            timestamp = datetime.now().strftime("%d-%m-%Y %I:%M:%S%p")
            print(f"{color}{timestamp} | [{action.upper()}] | {symbol} | {interval} | S-EMA: {short_ema:.6f} | L-EMA: {long_ema:.6f} | Total: {bot_data['fiat']}{total_current_value_usd}{COLOR_RESET}")
            print(f"{color}{timestamp} | [{action.upper()}] | {symbol} | {interval} | Start {bot_data['base_currency']}: {bot_data['base_starting_currency_quantity']:.8f} | {bot_data['base_currency']}: {bot_data['base_current_currency_quantity']:.8f} | {bot_data['quote_currency']}: {bot_data['quote_current_currency_quantity']:.8f} | Total Profit/Loss: {bot_data['fiat']}{total_profit_loss:.8f}{COLOR_RESET}")

            # Update previous market price for next iteration
            bot_data["previous_market_price"] = current_market_price

        except Exception as e:
            print(f"Error in trading loop: {e}")

        time.sleep(wait_time)

@app.route("/")
def home():
    return jsonify({"message": "Trend Following Bot is ready!"})

@app.route("/start", methods=["POST"])
def start_bot():
    global trading_thread

    if bot_data["running"]:
        return jsonify({"message": "Bot is already running!", "status": "On"}), 400

    data = request.json
    bot_data["symbol"] = data.get("symbol")
    bot_data["trade_allocation"] = Decimal(data.get("trade_allocation", 0))
    base, quote = split_market_pair(bot_data["symbol"])
    split_funds = True
    bot_data["base_currency"] = base
    bot_data["quote_currency"] = quote
    bot_data["interval"] = data.get("interval", "1h")
    bot_data["starting_trade_amount"] = Decimal(data.get("starting_trade_amount", 0.0))
    bot_data["current_trade_amount"] = bot_data["starting_trade_amount"]

    # Fetch price and calculate initial quantity
    current_price = Decimal(binance_client.get_symbol_ticker(symbol=bot_data["symbol"])["price"])
    min_qty, step_size = get_quantity_precision(bot_data["symbol"])
    min_notional = get_notional_limit(bot_data["symbol"])

    # Ensure the trade meets the minimum notional value
    required_quantity = max(min_qty, min_notional / current_price)
    starting_trade_amount = bot_data["starting_trade_amount"]
    if (split_funds): 
        starting_trade_amount = starting_trade_amount / 2
         # Calculate the quantity of the base currency
        bot_data["base_starting_currency_quantity"] = adjust_quantity(starting_trade_amount / current_price, min_qty, step_size)
        bot_data["base_current_currency_quantity"] = bot_data["base_starting_currency_quantity"]
        
        if quote == "USDT":
            # If the quote currency is USDT, we can directly assign the value
            bot_data["quote_current_currency_quantity"] = adjust_quantity(starting_trade_amount, min_qty, step_size)
        else:
            # Fetch the price of the quote currency in terms of USDT
            quote_price = Decimal(binance_client.get_symbol_ticker(symbol=f"{quote}USDT")["price"])
            bot_data["quote_current_currency_quantity"] = adjust_quantity(starting_trade_amount / quote_price, min_qty, step_size)
        
    else:
        # If not splitting funds, use the entire amount for base currency
        bot_data["base_starting_currency_quantity"] = adjust_quantity(starting_trade_amount / current_price, min_qty, step_size)
        bot_data["base_current_currency_quantity"] = bot_data["base_starting_currency_quantity"]
        
    print(starting_trade_amount)
    bot_data["currency_quantity_precision"] = step_size
    bot_data["previous_market_price"] = current_price

    bot_data["running"] = True
    print(f"Bot started with {bot_data['symbol']} | Interval: {bot_data['interval']} | Starting {bot_data['base_currency']}: {bot_data['base_starting_currency_quantity']} | Starting {bot_data['quote_currency']}: {bot_data['quote_current_currency_quantity']} Starting  (Total: {bot_data['fiat']}{bot_data['starting_trade_amount']})")
    
    trading_thread = threading.Thread(target=trading_loop, daemon=True)
    trading_thread.start()

    return jsonify({
        "message": "Bot started successfully!",
    })

@app.route("/stop", methods=["POST"])
def stop_bot():
    if not bot_data["running"]:
        return jsonify({"message": "Bot is not running!"}), 400
    bot_data["running"] = False
    with open("bot_data.json", "w") as f:
        json.dump(bot_data, f, indent=4)
    return jsonify({"message": "Bot stopped successfully!"})

@app.route("/daily-log", methods=["GET"])
def daily_log():
    return jsonify({"daily_log": bot_data["daily_log"]})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
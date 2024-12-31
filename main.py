from flask import Flask, jsonify, request
from core.trader import trading_loop
from config.bot_config import bot_data, binance_client
from core.utils import split_market_pair, adjust_quantity, get_quantity_precision, get_notional_limit, colorize_cli_text
from decimal import Decimal, getcontext
import json
import threading

app = Flask(__name__)

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
        
    bot_data["currency_quantity_precision"] = step_size
    bot_data["previous_market_price"] = current_price

    bot_data["running"] = True
    print(f"{colorize_cli_text('🚀 Trendr','botname')} started with {colorize_cli_text(bot_data['symbol'], 'symbol')} | Interval: {bot_data['interval']} | Starting {colorize_cli_text(bot_data['base_currency'],bot_data['base_currency'])}: {bot_data['base_starting_currency_quantity']} | Starting {colorize_cli_text(bot_data['quote_currency'])}: {bot_data['quote_current_currency_quantity']}")
    
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
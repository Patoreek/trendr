from flask import Flask, jsonify, request, Response
from core.trader import trading_loop
from config.bot_config import bot_data, binance_client
from core.utils import split_market_pair, adjust_quantity, get_quantity_precision, get_notional_limit, colorize_cli_text, parse_trade_window
from decimal import Decimal, getcontext
import json
import threading
from core.logger import stop_logger, CustomJSONEncoder


app = Flask(__name__)

# Global bot registry
bot_registry = {}

@app.route("/")
def home():
    return jsonify({"message": "Trend Following Bot is ready!"})

@app.route("/start", methods=["POST"])
def start_bot():

    data = request.json
    bot_data_instance = bot_data.copy()
    bot_data_instance["symbol"] = data.get("symbol")
    bot_data_instance["trade_allocation"] = Decimal(data.get("trade_allocation", 0))
    base, quote = split_market_pair(bot_data_instance["symbol"])
    split_funds = True
    bot_data_instance["base_currency"] = base
    bot_data_instance["quote_currency"] = quote
    bot_data_instance["interval"] = data.get("interval", "1h")
    bot_data_instance["starting_trade_amount"] = Decimal(data.get("starting_trade_amount", 0.0))
    bot_data_instance["current_trade_amount"] = bot_data_instance["starting_trade_amount"]
    
    # Check for duplicate bot
    for bot_name, bot in bot_registry.items():
        if (
            bot["data"]["symbol"] == bot_data_instance["symbol"] and
            bot["data"]["interval"] == bot_data_instance["interval"] and
            bot["data"]["starting_trade_amount"] == bot_data_instance["starting_trade_amount"] and
            bot["data"]["trade_allocation"] == bot_data_instance["trade_allocation"]
        ):
            return jsonify({
                "message": f"A bot ({bot_name}) for {bot_data_instance['symbol']} with interval {bot_data_instance['interval']} is already running!",
                "status": "On",
                "bot_name": bot_name  # Include the bot_name in the response
            }), 400

    # Create unique bot name for user listing
    bot_name = f"bot-{len(bot_registry)+1:03d}-{bot_data_instance['symbol']}-{bot_data_instance['interval']}-S:{bot_data_instance["starting_trade_amount"]}-{bot_data_instance["trade_allocation"]}%"

    # Fetch price and calculate initial quantity
    current_price = Decimal(binance_client.get_symbol_ticker(symbol=bot_data_instance["symbol"])["price"])
    min_qty, step_size = get_quantity_precision(bot_data_instance["symbol"])
    min_notional = get_notional_limit(bot_data_instance["symbol"])

    # Ensure the trade meets the minimum notional value
    required_quantity = max(min_qty, min_notional / current_price)
    starting_trade_amount = bot_data_instance["starting_trade_amount"]
    if (split_funds): 
        starting_trade_amount = starting_trade_amount / 2
         # Calculate the quantity of the base currency
        bot_data_instance["base_starting_currency_quantity"] = adjust_quantity(starting_trade_amount / current_price, min_qty, step_size)
        bot_data_instance["base_current_currency_quantity"] = bot_data_instance["base_starting_currency_quantity"]
        
        if quote == "USDT":
            # If the quote currency is USDT, we can directly assign the value
            bot_data_instance["quote_current_currency_quantity"] = adjust_quantity(starting_trade_amount, min_qty, step_size)
        else:
            # Fetch the price of the quote currency in terms of USDT
            quote_price = Decimal(binance_client.get_symbol_ticker(symbol=f"{quote}USDT")["price"])
            bot_data_instance["quote_current_currency_quantity"] = adjust_quantity(starting_trade_amount / quote_price, min_qty, step_size)
        
    else:
        # If not splitting funds, use the entire amount for base currency
        bot_data_instance["base_starting_currency_quantity"] = adjust_quantity(starting_trade_amount / current_price, min_qty, step_size)
        bot_data_instance["base_current_currency_quantity"] = bot_data_instance["base_starting_currency_quantity"]
        
    bot_data_instance["currency_quantity_precision"] = step_size
    bot_data_instance["previous_market_price"] = current_price

    bot_data_instance["running"] = True
    
    trade_window = data.get('trade_window')
    bot_data_instance["trade_window"] = parse_trade_window(trade_window)    
    
    # Thread target function
    def bot_thread(bot_name, bot_data_instance):
        try:
            trading_loop(bot_name, bot_data_instance)
        finally:
            bot_registry.pop(bot_name, None)  # Clean up when thread exits

    thread = threading.Thread(target=bot_thread, args=(bot_name, bot_data_instance), daemon=True)
    thread.start()

    bot_registry[bot_name] = {
        "data": bot_data_instance,
        "thread": thread,
    }
    print(f"{colorize_cli_text('🚀 Trendr','botname')} started with {colorize_cli_text(bot_data_instance['symbol'], 'symbol')} | Interval: {bot_data['interval']} | Starting {colorize_cli_text(bot_data['base_currency'],bot_data['base_currency'])}: {bot_data['base_starting_currency_quantity']} | Starting {colorize_cli_text(bot_data['quote_currency'])}: {bot_data['quote_current_currency_quantity']}")
    return jsonify({"message": f"Bot {bot_name} started successfully!", "bot_name": bot_name})


@app.route("/stop", methods=["POST"])
def stop_bot():
    data = request.json
    bot_name = data.get("bot_name")

    if not bot_name:
        return jsonify({"message": "Bot name is required to stop the bot!"}), 400

    # Check if the bot exists in the registry
    bot = bot_registry.get(bot_name)
    if not bot:
        return jsonify({"message": f"Bot with name {bot_name} does not exist or is not running!"}), 404
    
    logger = bot["data"].get("logger")
    if logger and logger.connection_successful:  # Only stop the logger if the connection was successful
        stop_logger(bot["data"])
    # Mark the bot as not running
    bot["data"]["running"] = False

    # Wait for the thread to exit gracefully
    bot["thread"].join(timeout=5)
    
    # Remove the bot from the registry
    bot_registry.pop(bot_name, None)

    return jsonify({"message": f"Bot {bot_name} has stopped successfully!"})

@app.route("/statuses", methods=["GET"])
def get_bot_statuses():
    # Prepare a list of all currently running bots
    running_bots = []
    for bot_name, bot in bot_registry.items():
        bot_data_serializable = {
            key: value for key, value in bot["data"].items()
            if key not in ["logger", "logger_thread"]  # Exclude non-serializable fields
        }
        running_bots.append({
            "bot_name": bot_name,
            "bot_data": bot_data_serializable
        })
    
    # Serialize using CustomJSONEncoder
    response_data = {"running_bots": running_bots}
    response_json = json.dumps(response_data, cls=CustomJSONEncoder)
    return Response(response_json, content_type="application/json", status=200)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
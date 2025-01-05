from decimal import Decimal
from core.utils import get_notional_limit, get_quantity_precision, adjust_quantity, colorize_cli_text, parse_trade_window, get_current_datetime
from strategies.ema_strategy import calculate_ema
from config.bot_config import bot_data, binance_client, COLORS
from core.logger import start_logger, wsprint, create_message_data
import time
from datetime import datetime
import pytz
sydney_tz = pytz.timezone('Australia/Sydney')

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
                f"{COLORS['error']}Insufficient {bot_data['quote_currency']} balance: required {required_quote_balance}, available {bot_data['quote_current_currency_quantity']}{COLORS['reset']}"
            )

        # Check if the trade amount meets the minimum notional value
        if adjusted_quantity * price < min_notional:
            raise ValueError(
                f"{COLORS['error']}Trade amount {adjusted_quantity * price} is below minimum notional {min_notional}{COLORS['reset']}"
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
        # print(f"Error placing buy order: {e}")
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
        # print(f"Error placing sell order: {e}")
        bot_data["failed_trades"] += 1
        return False
    
def get_historical_data(symbol, interval, limit):
    klines = binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    return [float(kline[4]) for kline in klines]

def trading_loop(bot_name, bot_data):
    INTERVAL_TO_SECONDS = {
        "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400,
    }
    print(f"{COLORS['neutral']} System Update: All systems operational. {bot_name}{COLORS['reset']}")
    total_profit_loss = 0
    
    # Create Bot trading window deadline
    if isinstance(bot_data['trade_window'], str):
        bot_data['trade_window'] = parse_trade_window(bot_data['trade_window'])
    bot_data['end_trade_time'] = get_current_datetime() + bot_data['trade_window']
    # Start the logger
    logger = start_logger(bot_name)
    
    while bot_data["running"]:
        if get_current_datetime() >= bot_data['end_trade_time']:
            message_data = create_message_data(
                message=f"⏰ Trade window for bot {bot_name} has ended.",
                status="notify"
            )
            wsprint(logger, message_data)
            # Optionally log final stats or perform cleanup here
            break
        
        try:
            symbol = bot_data["symbol"]
            interval = bot_data["interval"]
            wait_time = INTERVAL_TO_SECONDS.get(interval, 3600)
            prices = get_historical_data(symbol, interval, limit=50)
            short_ema = calculate_ema(prices, window=5)
            long_ema = calculate_ema(prices, window=20)
            color_option = 'loss' if total_profit_loss < 0 else 'profit'
            print(f"{COLORS['neutral']} Starting Trade | {symbol} | {interval} |{COLORS['reset']} Profit/Loss: {colorize_cli_text(bot_data['fiat_stablecoin'])}: {colorize_cli_text(f"{total_profit_loss:.8f}", color_option)} {COLORS['reset']}")
            if bot_data["base_current_currency_quantity"] > 0 and short_ema > long_ema and bot_data["quote_current_currency_quantity"] > 0:
                action = "Buy"
                color = COLORS['buy']
                available_amount = bot_data["current_trade_amount"]
                order = buy_crypto(symbol, available_amount)
            elif bot_data["base_current_currency_quantity"] > 0 and short_ema < long_ema:
                action = "Sell"
                color = COLORS['sell']
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
                color = COLORS['error']
                print(f"{color}{hold_msg}{COLORS['reset']}")
                color = COLORS['hold']

            
            
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
                bot_data['total_profit_loss'] = total_profit_loss
            
          
            timestamp = get_current_datetime().strftime("%d-%m-%Y %I:%M:%S%p")
            print(f"{color}{timestamp} | [{action.upper()}] | {symbol} | {interval} | S-EMA: {short_ema:.6f} | L-EMA: {long_ema:.6f} | Total: {bot_data['fiat_stablecoin']}{total_current_value_usd}{COLORS['reset']}")
            print(f"{color}{timestamp} | [{action.upper()}] | {symbol} | {interval} | Start {bot_data['base_currency']}: {bot_data['base_starting_currency_quantity']:.8f} | {bot_data['base_currency']}: {bot_data['base_current_currency_quantity']:.8f} | {bot_data['quote_currency']}: {bot_data['quote_current_currency_quantity']:.8f} | Total Profit/Loss: {bot_data['fiat_stablecoin']}{total_profit_loss:.8f}{COLORS['reset']}")
            
            # Update previous market price for next iteration
            bot_data["previous_market_price"] = current_market_price
            
            message_data = create_message_data(
                message=f"[STORE] {bot_name} data",
                status="log",
                data=bot_data
            )
            wsprint(logger, message_data)

        except Exception as e:
            print(f"Error in trading loop: {e}")

        time.sleep(wait_time)

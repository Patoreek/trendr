from decimal import Decimal
from core.utils import get_notional_limit, get_quantity_precision, adjust_quantity, colorize_cli_text, parse_trade_window, get_current_datetime
from strategies.ema_strategy import calculate_ema
from config.bot_config import binance_client, COLORS
from core.logger import start_logger, wsprint, create_message_data
import time
from datetime import datetime
import pytz
import numpy as np
import pandas as pd


sydney_tz = pytz.timezone('Australia/Sydney')

def buy_crypto(symbol, bot_data):
    try:
        min_notional = get_notional_limit(symbol)
        price = Decimal(binance_client.get_symbol_ticker(symbol=symbol)["price"])
        min_qty, step_size = get_quantity_precision(symbol)
        
        # Calculate trade amount using quote_current_currency_quantity
        trade_amount = Decimal(bot_data["quote_current_currency_quantity"]) * (Decimal(bot_data["trade_allocation"]) / Decimal('100.0'))
        quantity = trade_amount / price
        adjusted_quantity = adjust_quantity(quantity, min_qty, step_size)
        
        # Ensure adjusted quantity meets minimum notional value
        if adjusted_quantity * price < min_notional:
            adjusted_quantity = min_notional / price
            adjusted_quantity = adjust_quantity(adjusted_quantity, min_qty, step_size)
        
        required_quote_balance = adjusted_quantity * price
        
        # Check for sufficient quote balance
        if bot_data["quote_current_currency_quantity"] < required_quote_balance:
            raise ValueError(
                f"{COLORS['error']}Insufficient {bot_data['quote_currency']} balance: required {required_quote_balance}, available {bot_data['quote_current_currency_quantity']}{COLORS['reset']}"
            )
        
        # Place market buy order
        order = binance_client.order_market_buy(symbol=symbol, quantity=f"{adjusted_quantity:.8f}")
        
        # Calculate fees and update bot_data
        fee_rate = get_fee_rate(symbol)
        total_cost = adjusted_quantity * price
        fee = total_cost * fee_rate
        net_cost = total_cost + fee
        
        bot_data["current_trade_amount"] -= net_cost
        bot_data["base_current_currency_quantity"] += adjusted_quantity
        bot_data["quote_current_currency_quantity"] -= total_cost
        
        print(f'BUYING {bot_data["base_currency"]} WITH {bot_data["quote_currency"]}')
        bot_data["successful_trades"] += 1
        bot_data["total_buys"] += 1
        bot_data["total_trades"] += 1
        
        # Market Log Data
        bot_data["market_action"] = "Buy"
        bot_data["market_price"] = float(price)
        bot_data["market_quantity"] = float(adjusted_quantity)
        bot_data["market_value"] = float(total_cost)
        bot_data["market_fee"] = float(fee)
        bot_data["market_net_value"] = float(net_cost)
        bot_data["market_timestamp"] = time.time()
        
        return order
    except Exception as e:
        print(f"Error placing buy order: {e}")
        bot_data["failed_trades"] += 1
        bot_data["total_trades"] += 1
        return False
    
def sell_crypto(symbol, bot_data):
    try:
        min_notional = get_notional_limit(symbol)
        price = Decimal(binance_client.get_symbol_ticker(symbol=symbol)["price"])
        min_qty, step_size = get_quantity_precision(symbol)

        # Use trade allocation to determine quantity to sell
        trade_amount = Decimal(bot_data["current_trade_amount"]) * (Decimal(bot_data["trade_allocation"]) / Decimal('100.0'))
        quantity = min(trade_amount / price, bot_data["base_current_currency_quantity"])  # Sell only what we have
        adjusted_quantity = adjust_quantity(quantity, min_qty, step_size)
         
        if bot_data["base_current_currency_quantity"] < adjusted_quantity:
            raise ValueError(f"Insufficient base currency balance: required {adjusted_quantity}, available {bot_data['base_current_currency_quantity']}")
            return false
        
        trade_value = adjusted_quantity * price
        if trade_value < min_notional:
            raise ValueError(f"Trade value {trade_value} is below minimum notional {min_notional}")
            return false

        order = binance_client.order_market_sell(symbol=symbol, quantity=f"{adjusted_quantity:.8f}")
        
        fee_rate = get_fee_rate(symbol)
        fee = trade_value * fee_rate
        net_value = trade_value - fee

        # Update bot_data after the sell
        bot_data["current_trade_amount"] += net_value
        bot_data["base_current_currency_quantity"] -= adjusted_quantity
        bot_data["quote_current_currency_quantity"] += trade_value

        bot_data["base_current_currency_quantity"] = max(Decimal('0.0'), bot_data["base_current_currency_quantity"])

        print(f'SELLING {bot_data["base_currency"]} FOR {bot_data["quote_currency"]}')
        bot_data["successful_trades"] += 1
        bot_data["total_sells"] += 1
        bot_data["total_trades"] += 1
        # Market Log Data
        bot_data["action"] = "Sell"
        bot_data["symbol"] = symbol
        bot_data["price"] = float(price)
        bot_data["quantity"] = float(adjusted_quantity)
        bot_data["value"] = float(trade_value)
        bot_data["fee"] = float(fee)
        bot_data["net_value"] = float(net_value)
        bot_data["timestamp"] = time.time()
            
        return order
        # return order
    except Exception as e:
        print(f"Error placing sell order: {e}")
        # print(f"Error placing sell order: {e}")
        bot_data["failed_trades"] += 1
        bot_data["total_trades"] += 1
        return False
    
def get_historical_data(symbol, interval, limit):
    klines = binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    return [float(kline[4]) for kline in klines]

def loss_limiter(bot_data, symbol):
    stop_loss_percentage = 5  # Exit if loss exceeds 5%
    take_profit_percentage = 10  # Exit if profit exceeds 10%

    # Calculate the percentage change
    percentage_change = (bot_data['current_trade_amount'] - bot_data['starting_trade_amount']) / bot_data['starting_trade_amount'] * 100

    # Check for stop-loss or take-profit
    if percentage_change <= -stop_loss_percentage:
        action = "Sell"
        print(f"{COLORS['error']} Stop-Loss triggered: Exiting position. {percentage_change:.2f}% loss {COLORS['reset']}")
        order = sell_crypto(symbol, bot_data)
        return True

    elif percentage_change >= take_profit_percentage:
        action = "Sell"
        print(f"{COLORS['profit']} Take-Profit triggered: Exiting position. {percentage_change:.2f}% profit {COLORS['reset']}")
        order = sell_crypto(symbol, bot_data)
        return True
    
    print(f'Loss limiter not trigger. All ok...')
    return False

def dynamic_trade_allocation(bot_data, short_ema, long_ema, atr):
    """
    Adjust the trade allocation dynamically based on trend strength and market volatility (ATR).

    Parameters:
        bot_data (dict): Contains bot-related data, including trade allocation and current trade amount.
        short_ema (float): The short EMA value.
        long_ema (float): The long EMA value.
        atr (float): The Average True Range, used to measure market volatility.

    Returns:
        float: Adjusted trade allocation.
    """
    trade_allocation = bot_data['trade_allocation']
    trend_strength = short_ema / long_ema

    # Adjust trade allocation based on trend strength
    if trend_strength > 1.1:  # Strong uptrend
        print(f"Strong uptrend detected (trend_strength={trend_strength:.2f}). Increasing trade allocation.")
        trade_allocation *= 1.5  # Increase trade size
    elif trend_strength < 0.9:  # Weak trend
        print(f"Weak trend detected (trend_strength={trend_strength:.2f}). Decreasing trade allocation.")
        trade_allocation *= 0.5  # Decrease trade size

    # Adjust trade allocation based on ATR
    atr_threshold_high = bot_data.get('atr_threshold_high', 25)  # Example threshold, adjust as needed
    atr_threshold_low = bot_data.get('atr_threshold_low', 5)     # Example threshold, adjust as needed

    if atr > atr_threshold_high:
        print(f"High volatility detected (ATR={atr:.2f}). Decreasing trade allocation.")
        trade_allocation *= Decimal('0.7')  # Decrease trade size for high volatility
    elif atr < atr_threshold_low:
        print(f"Low volatility detected (ATR={atr:.2f}). Increasing trade allocation.")
        trade_allocation *= Decimal('1.2')  # Increase trade size for low volatility

    # Ensure the trade allocation is within bounds
    trade_allocation = min(trade_allocation, bot_data['current_trade_amount'])
    return max(trade_allocation, bot_data.get('min_trade_allocation', 10))  # Ensure a minimum trade allocation

def check_ema_threshold(bot_data, short_ema, long_ema):
    # crossover_threshold = 0.3  # e.g., Min 0.2 | Max 0.5% buffer
    crossover_threshold = 0  # e.g., Min 0.2 | Max 0.5% buffer
    
    if bot_data["base_current_currency_quantity"] > 0 and short_ema > (long_ema * (1 + crossover_threshold / 100)) and bot_data["quote_current_currency_quantity"] > 0:
        action = "Buy"
        return action
    elif bot_data["base_current_currency_quantity"] > 0 and short_ema < (long_ema * (1 - crossover_threshold / 100)):
        action = "Sell"
        return action
    else:
        # Determine why the bot is holding
        if bot_data["base_current_currency_quantity"] <= 0 and short_ema < long_ema:
            hold_msg = f"Cannot [SELL]: insufficient {bot_data['base_currency']} funds. Holding..."
        elif bot_data["quote_current_currency_quantity"] <= 0 and short_ema > long_ema:
            hold_msg = f"Cannot [BUY]: insufficient {bot_data['quote_currency']} funds. Holding..."
        else:
            hold_msg = "Holding: Market conditions do not allow a trade."
            
        action = "Hold"
        bot_data["total_holds"] += 1
        color = COLORS['error']
        print(f"{color}{hold_msg}{COLORS['reset']}")
        return action
            
def risk_reward_ratio(prices, short_ema, long_ema, atr, reward_to_risk_ratio=.25):
    """
    Calculate and check the risk-to-reward ratio for a potential trade, adjusted by ATR.

    Parameters:
        prices (list of float): Historical prices.
        short_ema (float): The short EMA value.
        long_ema (float): The long EMA value.
        atr (float): The Average True Range, used to adjust risk.
        reward_to_risk_ratio (float): The minimum acceptable reward-to-risk ratio. Default is 2.

    Returns:
        bool: True if the risk-to-reward ratio is favorable, False otherwise.
    """
    current_price = prices[-1]  # Use the most recent price from the prices list

    # Calculate potential reward and risk
    potential_reward = abs(current_price - short_ema)  # Potential profit
    potential_risk = max(abs(short_ema - long_ema), atr)  # Use ATR as a lower bound for risk

    # Avoid division by zero
    if potential_risk == 0:
        print(f"{COLORS['neutral']} Skipping trade: Risk is zero, invalid ratio. {COLORS['reset']}")
        return False

    # Calculate risk-to-reward ratio
    risk_reward = potential_reward / potential_risk
    print(f"Risk/reward {risk_reward:.2f}:1 (Target: {reward_to_risk_ratio}:1)")

    # Evaluate if the reward outweighs the risk
    if risk_reward >= reward_to_risk_ratio:
        print(f"{COLORS['positive']} Reward outweighs risk! Continue! {COLORS['reset']}")
        return True  # Favorable ratio
    else:
        print(f"{COLORS['neutral']} Skipping trade: Unfavorable risk-to-reward ratio. {COLORS['reset']}")
        return False  # Unfavorable ratio


def calculate_atr(symbol, interval, limit, window):
    # Fetch the Kline data
    klines = binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    
    # Convert the Kline data into a dictionary of high, low, close prices
    prices = {
        'high': [float(kline[2]) for kline in klines],  # High prices
        'low': [float(kline[3]) for kline in klines],   # Low prices
        'close': [float(kline[4]) for kline in klines]  # Closing prices
    }
    
    # Convert to numpy arrays for efficient calculation
    highs = np.array(prices['high'])
    lows = np.array(prices['low'])
    closes = np.array(prices['close'])
    
    # Convert closes to a pandas Series to use shift()
    closes_series = pd.Series(closes)
    
    # Calculate True Range (TR)
    tr = np.maximum(
        highs - lows,
        np.maximum(
            abs(highs - np.roll(closes, shift=1)),  # Use np.roll to shift the closes array
            abs(lows - np.roll(closes, shift=1))
        )
    )
    
    # The first TR value is undefined due to lack of a previous close, set it to 0
    tr[0] = 0

    # Calculate Average True Range (ATR) using rolling window
    atr = pd.Series(tr).rolling(window=window).mean()
    
    return atr

def atr_filter(atr, atr_threshold_high=50, atr_threshold_low=10): # High (30-50) | Low (10-15)
    """
    Evaluates if the current ATR value is within acceptable bounds for trading.

    Parameters:
        atr (float): The calculated ATR value.
        atr_threshold_high (float): The upper threshold for ATR. Default is 25.
        atr_threshold_low (float): The lower threshold for ATR. Default is 5.

    Returns:
        tuple: (bool, str)
            - bool: True if ATR is within bounds and trading should proceed, False otherwise.
            - str: A message explaining the decision.
    """
    if atr > atr_threshold_high:
        return False, f"ATR ({atr}) is too high. Skipping trade due to high volatility."
    elif atr < atr_threshold_low:
        return False, f"ATR ({atr}) is too low. Skipping trade due to low volatility."
    return True, "ATR is within acceptable bounds for trading."

def get_fee_rate(symbol):
    """
    Fetch the current trading fee rate for a given market pair.

    Parameters:
        symbol (str): The market pair symbol (e.g., "BTCUSDT").

    Returns:
        Decimal: The trading fee rate as a Decimal.
    """
    fee_info = binance_client.get_trade_fee(symbol=symbol)
    # Binance API returns a list; fee rate is in "makerCommission" and "takerCommission".
    maker_fee = Decimal(fee_info[0]["makerCommission"])
    taker_fee = Decimal(fee_info[0]["takerCommission"])
    # Use taker fee as the default trading fee rate
    return taker_fee / Decimal('100')  # Convert percentage to decimal

def trailing_stop_loss(bot_data, symbol, prices, atr):
    """
    Implements a trailing stop-loss mechanism with ATR adjustments.

    Parameters:
        bot_data (dict): Contains bot-related data, including the highest market price.
        symbol (str): The trading pair symbol (e.g., BTCUSDT).
        prices (list of float): Historical prices, with the latest price as the last element.
        atr (float): The Average True Range, used to measure market volatility.

    Returns:
        bool: True if the trailing stop-loss is triggered, False otherwise.
    """
    # Base trailing stop-loss percentage
    base_trailing_stop_loss_percentage = bot_data.get('base_trailing_stop_loss_percentage', 2)

    # Adjust trailing stop-loss percentage based on ATR
    atr_threshold_high = bot_data.get('atr_threshold_high', 50)
    atr_threshold_low = bot_data.get('atr_threshold_low', 10)
    if atr > atr_threshold_high:
        print(f"High volatility detected (ATR={atr:.2f}). Widening trailing stop-loss.")
        trailing_stop_loss_percentage = base_trailing_stop_loss_percentage * 1.5  # Increase tolerance for high volatility
    elif atr < atr_threshold_low:
        print(f"Low volatility detected (ATR={atr:.2f}). Tightening trailing stop-loss.")
        trailing_stop_loss_percentage = base_trailing_stop_loss_percentage * 0.75  # Decrease tolerance for low volatility
    else:
        trailing_stop_loss_percentage = base_trailing_stop_loss_percentage

    # Get the highest price (from previous or current highest market price)
    highest_market_price = max(bot_data.get('highest_market_price', 0), prices[-1])  # Use the latest price

    # Calculate the trailing stop price
    trailing_stop_price = highest_market_price * (1 - trailing_stop_loss_percentage / 100)
    print(f"Highest Market Price: {highest_market_price:.2f}, Trailing Stop Price: {trailing_stop_price:.2f}")

    # Compare the most recent price with the trailing stop price
    if prices[-1] < trailing_stop_price:  # Compare with the latest price in the list
        print(f"{COLORS['error']} Trailing Stop-Loss triggered: Exiting position. {COLORS['reset']}")
        order = sell_crypto(symbol, bot_data)  # Replace with your actual sell logic
        return True

    # Update the highest market price if needed
    bot_data['highest_market_price'] = highest_market_price
    return False

def trading_loop(bot_name, bot_data):
    INTERVAL_TO_SECONDS = {
        "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400,
    }
    print(f"{COLORS['neutral']} System Update: All systems operational. {bot_name}{COLORS['reset']}")
    total_profit_loss = 0
    
    # Create Bot trading window deadline
    bot_data['start_trade_time'] = get_current_datetime()
    if isinstance(bot_data['trade_window'], str):
        if bot_data['trade_window'] != "infinite":
            bot_data['trade_window'] = parse_trade_window(bot_data['trade_window'])
    if bot_data['trade_window'] != "infinite":
        bot_data['end_trade_time'] = get_current_datetime() + bot_data['trade_window']
        
        
    # Start the logger
    logger = start_logger(bot_name)
    
    while bot_data["running"]:
        # Stop bot if designated trade window is done.
        if bot_data['end_trade_time'] and get_current_datetime() >= bot_data['end_trade_time']:
            message = f"⏰ Trade window for bot {bot_name} has ended."
            message_data = create_message_data(
                message=message,
                status="notify"
            )
            wsprint(logger, message_data)
            print(message)
            break
        
        try:
            symbol = bot_data["symbol"]
            interval = bot_data["interval"]
            wait_time = INTERVAL_TO_SECONDS.get(interval, 3600)
            prices = get_historical_data(symbol, interval, limit=50)
            color_option = 'loss' if total_profit_loss < 0 else 'profit'
            print(f"{COLORS['neutral']} Starting Trade | {symbol} | {interval} |{COLORS['reset']} Profit/Loss: {colorize_cli_text(bot_data['fiat_stablecoin'])}: {colorize_cli_text(f"{total_profit_loss:.8f}", color_option)} {COLORS['reset']}")
            
            #Strategies
            short_ema = calculate_ema(prices, window=5)
            long_ema = calculate_ema(prices, window=20)
            
            # Loss Limiter              >> Does the final order then should stop the bot. Log action with what the bot has done.
            stop_trading = loss_limiter(bot_data, symbol)
            if stop_trading: break
            
            # calculate_atr             >> Avoid trading during highly volatile markets by using metrics like Average True Range (ATR) or Bollinger Bands.
            atr_series = calculate_atr(symbol, interval, limit=50, window=14) # Common default for ATR calculation is 14. Adjust this depending on your strategy and market conditions.
            # print(f"atr_series: {atr_series}")
            # Extract the most recent ATR value
            atr = atr_series.iloc[-1]  # Get the last value in the Series
            print(f"Most recent ATR: {atr}")
            atr_ok, atr_message = atr_filter(atr)
            print(atr_message)  # Log the decision
            if not atr_ok:
                time.sleep(wait_time)  # Wait for the specified amount of time
                continue  # Skip to the next iteration
            
            
            
            
            # Risk/Reward Ratio         >> 2:1 Currently Reward outweights risk 2:1
            # is_rewarding = risk_reward_ratio(prices, short_ema, long_ema, atr)
            # print(f"[is_rewarding] Trade decision: {'Proceed' if is_rewarding else 'Skip'}")
            # if not is_rewarding:
            #     print("The trade is not rewarding based on risk/reward ratio. Not proceeding.")
            #     time.sleep(wait_time)  # Wait for the specified amount of time
            #     continue  # Skip to the next iteration
            
            # Dynamic Trade Allocation  >> size of trade changes on strong or weak trends accordingly.
            bot_data['dynamic_trade_allocation'] = dynamic_trade_allocation(bot_data, short_ema, long_ema, atr)

            # trailing stop/loss        >> lock in profits by dynamically updating the exit price as the trade moves in your favor.
            stop_loss_triggered = trailing_stop_loss(bot_data, symbol, prices, atr)
            print(f"stop_loss_triggered: {stop_loss_triggered}")
            if stop_loss_triggered:
                print("Trade exited due to trailing stop-loss.")
                break
            
            # Check EMA Thresholds      >> OG functionality + threshold amount
            ema_result = check_ema_threshold(bot_data, short_ema, long_ema)
            # Returns "Buy", "Sell", "Hold"
            if ema_result == "Buy":
                print("EMA signals a buy. Proceeding with the buy action.")
                color = COLORS['buy']
                buy_crypto(symbol, bot_data)  # Execute buy order

            elif ema_result == "Sell":
                print("EMA signals a sell. Proceeding with the sell action.")
                color = COLORS['sell']
                sell_crypto(symbol, bot_data)  # Execute sell order

            elif ema_result == "Hold":
                print("EMA signals hold. No action taken.")
                time.sleep(wait_time)  # Wait for the specified amount of time
                continue  # Skip to the next iteration

            # Profit/Loss Calculation
            current_market_price = Decimal(prices[-1])
            # Convert base currency to USD
            btc_to_usd_price = Decimal(binance_client.get_symbol_ticker(symbol=f"{bot_data['base_currency']}USDT")["price"]) if bot_data["base_currency"] != "USDT" else Decimal('1.0')
            base_value_current = bot_data["base_current_currency_quantity"] * btc_to_usd_price
            # # # Convert quote currency to USD if it's not USDT
            quote_to_usd_price = Decimal('1.0') if bot_data["quote_currency"] == "USDT" else Decimal(binance_client.get_symbol_ticker(symbol=f"{bot_data['quote_currency']}USDT")["price"])
            quote_value_current = bot_data["quote_current_currency_quantity"] * quote_to_usd_price
            total_current_value_usd = base_value_current + quote_value_current
            if (ema_result != "Hold"): 
                # Calculate profit/loss in USD
                total_profit_loss = total_current_value_usd - bot_data["starting_trade_amount"]
                bot_data['total_profit_loss'] = total_profit_loss
            
          
            timestamp = get_current_datetime().strftime("%d-%m-%Y %I:%M:%S%p")
            print(f"{color}{timestamp} | [{ema_result.upper()}] | {symbol} | {interval} | S-EMA: {short_ema:.6f} | L-EMA: {long_ema:.6f} | Total: {bot_data['fiat_stablecoin']}{total_current_value_usd}{COLORS['reset']}")
            print(f"{color}{timestamp} | [{ema_result.upper()}] | {symbol} | {interval} | Start {bot_data['base_currency']}: {bot_data['base_starting_currency_quantity']:.8f} | {bot_data['base_currency']}: {bot_data['base_current_currency_quantity']:.8f} | {bot_data['quote_currency']}: {bot_data['quote_current_currency_quantity']:.8f} | Total Profit/Loss: {bot_data['fiat_stablecoin']}{total_profit_loss:.8f}{COLORS['reset']}")
            
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

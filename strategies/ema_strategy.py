import numpy as np
from decimal import Decimal

# ---- Exponential Moving Average (EMA) ----
def calculate_ema(prices, window):
    """
    Calculates the Exponential Moving Average (EMA) for a given list of prices.
    
    Parameters:
        prices (list of float): Historical prices.
        window (int): Number of periods for the EMA.
    
    Returns:
        float: The EMA value.
    """
    prices = np.array(prices)
    weights = np.exp(np.linspace(-1., 0., window))
    weights /= weights.sum()
    return np.convolve(prices, weights, mode='valid')[-1]


# ---- Simple Moving Average (SMA) ----
def calculate_sma(prices, window):
    """
    Calculates the Simple Moving Average (SMA) for a given list of prices.
    
    Parameters:
        prices (list of float): Historical prices.
        window (int): Number of periods for the SMA.
    
    Returns:
        float: The SMA value.
    """
    return sum(prices[-window:]) / window if len(prices) >= window else None


# ---- Relative Strength Index (RSI) ----
def calculate_rsi(prices, window=14):
    """
    Calculates the Relative Strength Index (RSI) for a given list of prices.
    
    Parameters:
        prices (list of float): Historical prices.
        window (int): Number of periods to calculate RSI. Default is 14.
    
    Returns:
        float: The RSI value (0 to 100).
    """
    if len(prices) < window + 1:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:window])
    avg_loss = np.mean(losses[:window])

    if avg_loss == 0:
        return 100  # No losses, RSI is maximum.
    if avg_gain == 0:
        return 0  # No gains, RSI is minimum.

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---- Moving Average Convergence Divergence (MACD) ----
def calculate_macd(prices, fast_window=12, slow_window=26, signal_window=9):
    """
    Calculates the MACD and signal line.
    
    Parameters:
        prices (list of float): Historical prices.
        fast_window (int): Number of periods for the fast EMA. Default is 12.
        slow_window (int): Number of periods for the slow EMA. Default is 26.
        signal_window (int): Number of periods for the signal line EMA. Default is 9.
    
    Returns:
        tuple of float: (MACD value, Signal line value).
    """
    fast_ema = calculate_ema(prices, fast_window)
    slow_ema = calculate_ema(prices, slow_window)
    macd = fast_ema - slow_ema

    macd_list = [macd]  # For simplicity, mock history for signal EMA
    signal = calculate_ema(macd_list, signal_window)
    return macd, signal


# ---- Bollinger Bands ----
def calculate_bollinger_bands(prices, window=20, num_std_dev=2):
    """
    Calculates the Bollinger Bands.
    
    Parameters:
        prices (list of float): Historical prices.
        window (int): Number of periods for the SMA. Default is 20.
        num_std_dev (int): Number of standard deviations. Default is 2.
    
    Returns:
        tuple of float: (Upper band, SMA, Lower band).
    """
    if len(prices) < window:
        return None, None, None

    sma = calculate_sma(prices, window)
    std_dev = np.std(prices[-window:])
    upper_band = sma + (num_std_dev * std_dev)
    lower_band = sma - (num_std_dev * std_dev)
    return upper_band, sma, lower_band


# ---- Average True Range (ATR) ----
def calculate_atr(highs, lows, closes, window=14):
    """
    Calculates the Average True Range (ATR).
    
    Parameters:
        highs (list of float): High prices.
        lows (list of float): Low prices.
        closes (list of float): Close prices.
        window (int): Number of periods for ATR. Default is 14.
    
    Returns:
        float: The ATR value.
    """
    if len(highs) < window or len(lows) < window or len(closes) < window:
        return None

    true_ranges = [
        max(h - l, abs(h - c), abs(l - c))
        for h, l, c in zip(highs[1:], lows[1:], closes[:-1])
    ]
    return np.mean(true_ranges[-window:])


# ---- Parabolic SAR ----
def calculate_parabolic_sar(highs, lows, step=0.02, max_step=0.2):
    """
    Calculates the Parabolic SAR.
    
    Parameters:
        highs (list of float): High prices.
        lows (list of float): Low prices.
        step (float): Acceleration factor step. Default is 0.02.
        max_step (float): Maximum acceleration factor. Default is 0.2.
    
    Returns:
        float: The current Parabolic SAR value.
    """
    if len(highs) < 2 or len(lows) < 2:
        return None

    # Simplified implementation (advanced requires full data tracking)
    prev_high = highs[-2]
    prev_low = lows[-2]
    return prev_high + (prev_high - prev_low) * step


# ---- Donchian Channel ----
def calculate_donchian_channel(highs, lows, window=20):
    """
    Calculates the Donchian Channel.
    
    Parameters:
        highs (list of float): High prices.
        lows (list of float): Low prices.
        window (int): Number of periods for the channel. Default is 20.
    
    Returns:
        tuple of float: (Upper channel, Lower channel).
    """
    if len(highs) < window or len(lows) < window:
        return None, None

    upper_channel = max(highs[-window:])
    lower_channel = min(lows[-window:])
    return upper_channel, lower_channel
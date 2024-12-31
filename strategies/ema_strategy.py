import numpy as np

def calculate_ema(prices, window):
    prices = np.array(prices)
    weights = np.exp(np.linspace(-1., 0., window))
    weights /= weights.sum()
    return np.convolve(prices, weights, mode='valid')[-1]
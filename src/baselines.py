"""
baselines.py - the simple forecasts every model must beat.

All baselines are ONE-STEP-AHEAD: the forecast for week t uses actual demand up to week t-1.
  Naive            forecast = last week's demand
  Moving average   forecast = mean of the last k weeks
  Exp. smoothing   level_t = alpha*actual_t + (1-alpha)*level_{t-1};  forecast for t+1 = level_t
  Seasonal naive   forecast = demand of the same week last year (reference only)

Y is a matrix [n_series, n_weeks]. NaN = the item was not on sale that week (see cleaning.py); a forecast that would
need a NaN is NaN too, so we never forecast from weeks when the item did not exist.
"""
import numpy as np

import metrics


def naive(Y):
    out = np.full_like(Y, np.nan)
    out[:, 1:] = Y[:, :-1]
    return out


def moving_average(Y, k):
    """Forecast for week t = mean of weeks t-k ... t-1 (NaN if any of them is NaN)."""
    out = np.full_like(Y, np.nan)
    for t in range(k, Y.shape[1]):
        out[:, t] = Y[:, t - k:t].mean(axis=1)
    return out


def exp_smoothing(Y, alpha):
    out = np.full_like(Y, np.nan)
    level = np.full(Y.shape[0], np.nan)
    for t in range(Y.shape[1]):
        out[:, t] = level                                      # forecast made BEFORE seeing week t
        y = Y[:, t]
        level = np.where(np.isnan(y), level, np.where(np.isnan(level), y, alpha * y + (1 - alpha) * level))
    return out


def seasonal_naive(Y, season=52):
    out = np.full_like(Y, np.nan)
    out[:, season:] = Y[:, :-season]
    return out


def tune_on_dev(Y, weeks_dev, windows=(2, 3, 4, 6, 8), alphas=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)):
    """Pick the moving-average window and smoothing alpha with the lowest DEV WAPE (test is never used)."""
    cols = np.array(weeks_dev)
    best_k = min(windows, key=lambda k: metrics.wape(Y[:, cols], moving_average(Y, k)[:, cols]))
    best_a = min(alphas, key=lambda a: metrics.wape(Y[:, cols], exp_smoothing(Y, a)[:, cols]))
    return best_k, best_a

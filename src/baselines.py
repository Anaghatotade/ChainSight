"""
baselines.py - the simple forecasts every model must beat.

All baselines are ONE-STEP-AHEAD: the forecast for week t uses actual demand up to week t-1.
  Naive            forecast = last week's demand
  Moving average   forecast = mean of the last k weeks
  Exp. smoothing   level_t = alpha*actual_t + (1-alpha)*level_{t-1};  forecast for t+1 = level_t
  Seasonal naive   forecast = demand of the same week last year (reference only)
"""
import numpy as np
import pandas as pd

import metrics


def to_matrix(weekly, value="units_demanded"):
    """weekly (long) -> matrix [n_sku, n_weeks] and the list of SKUs."""
    wide = weekly.pivot(index="sku", columns="week_idx", values=value).sort_index()
    return wide.to_numpy(dtype=float), list(wide.index)


def naive(Y):
    out = np.full_like(Y, np.nan)
    out[:, 1:] = Y[:, :-1]
    return out


def moving_average(Y, k):
    out = np.full_like(Y, np.nan)
    c = np.cumsum(np.insert(Y, 0, 0.0, axis=1), axis=1)       # prefix sums -> fast rolling mean
    for t in range(k, Y.shape[1]):
        out[:, t] = (c[:, t] - c[:, t - k]) / k
    return out


def exp_smoothing(Y, alpha):
    out = np.full_like(Y, np.nan)
    level = Y[:, 0].copy()
    for t in range(1, Y.shape[1]):
        out[:, t] = level                                      # forecast made BEFORE seeing week t
        level = alpha * Y[:, t] + (1 - alpha) * level
    return out


def seasonal_naive(Y, season=52):
    out = np.full_like(Y, np.nan)
    out[:, season:] = Y[:, :-season]
    return out


def to_long(M, skus, name):
    """Matrix of forecasts -> long table (sku, week_idx, forecast)."""
    df = pd.DataFrame(M, index=skus).rename_axis("sku").reset_index().melt(id_vars="sku", var_name="week_idx", value_name=name)
    df["week_idx"] = df["week_idx"].astype(int)
    return df


def tune_on_dev(Y, weeks_dev, windows=(2, 3, 4, 6, 8), alphas=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)):
    """Pick the moving-average window and smoothing alpha with the lowest DEV WAPE (test is never used)."""
    cols = np.array(weeks_dev)
    best_k = min(windows, key=lambda k: metrics.wape(Y[:, cols], moving_average(Y, k)[:, cols]))
    best_a = min(alphas, key=lambda a: metrics.wape(Y[:, cols], exp_smoothing(Y, a)[:, cols]))
    return best_k, best_a

"""
metrics.py - forecast accuracy metrics (all take plain arrays: actual first, forecast second).

Primary (optimising) metric : WAPE  = sum|forecast - actual| / sum(actual)
Satisficing metrics         : RMSE (units), Bias = sum(forecast - actual) / sum(actual)
Why WAPE? It weights errors by volume, never divides by a zero actual, and reads like
"we are off by x% of demand" - a sentence a business manager understands.
"""
import numpy as np


def _clean(actual, forecast):
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    ok = ~(np.isnan(a) | np.isnan(f))
    return a[ok], f[ok]


def wape(actual, forecast):
    a, f = _clean(actual, forecast)
    return float(np.abs(f - a).sum() / a.sum()) if a.sum() > 0 else np.nan


def mape(actual, forecast):
    """Mean absolute % error; rows with actual == 0 are skipped (MAPE is undefined there)."""
    a, f = _clean(actual, forecast)
    nz = a != 0
    return float(np.mean(np.abs(f[nz] - a[nz]) / np.abs(a[nz]))) if nz.any() else np.nan


def rmse(actual, forecast):
    a, f = _clean(actual, forecast)
    return float(np.sqrt(np.mean((f - a) ** 2)))


def mae(actual, forecast):
    a, f = _clean(actual, forecast)
    return float(np.mean(np.abs(f - a)))


def bias(actual, forecast):
    """Positive = we over-forecast on average (-> excess stock); negative = under-forecast (-> stockouts)."""
    a, f = _clean(actual, forecast)
    return float((f - a).sum() / a.sum()) if a.sum() > 0 else np.nan


def score_all(actual, forecast):
    return dict(WAPE=wape(actual, forecast), MAPE=mape(actual, forecast), RMSE=rmse(actual, forecast),
                MAE=mae(actual, forecast), Bias=bias(actual, forecast))

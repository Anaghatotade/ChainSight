"""
features.py - turn weekly item x state demand into a supervised-learning table.

One row = one item in one state in one week. We predict demand of week t using ONLY information known before week t,
plus calendar / price information of week t itself (price lists, SNAP days and holidays are known in advance).

Features (all simple and explainable):
  lag_1, lag_2, lag_4, lag_52   demand 1, 2, 4 and 52 weeks ago (52 = same week last year)
  roll_mean_4, roll_mean_8      average demand of the previous 4 / 8 weeks
  month_sin, month_cos          month of the year on a circle (so December is next to January)
  price_ratio                   this week's price / average price of the previous 8 weeks (< 0.9 = a price cut)
  snap_share                    share of days in the week that are SNAP-benefit days in that state (0 .. 1)
  event_flag                    1 if the week contains a calendar event (holiday, sports final ...)

Scaling: items differ by 100x in size, so every series' demand is divided by that series' TRAIN-period mean
("relative demand ~ 1.0"). Then each feature is standardised with TRAIN-set mean/std.
Dev and test rows reuse those train numbers -> no leakage from the future.
"""
import warnings

import numpy as np
import pandas as pd

import baselines
import config as cfg
import kpis
import splits

FEATURES = ["lag_1", "lag_2", "lag_4", "lag_52", "roll_mean_4", "roll_mean_8",
            "month_sin", "month_cos", "price_ratio", "snap_share", "event_flag"]
LAG_COLS = ["lag_1", "lag_2", "lag_4", "lag_52", "roll_mean_4", "roll_mean_8"]


def build_matrices(panel):
    """Item x state weekly matrices: groups table g, demand Y (NaN = not on sale), price P, SNAP share S."""
    g, units, price, _ = kpis.aggregate_item_state(panel)
    w = panel.weeks
    snap_days = np.stack([w[f"snap_days_{s}"].to_numpy() for s in ("CA", "TX", "WI")])          # [3, W]
    state_row = g["state_id"].map({"CA": 0, "TX": 1, "WI": 2}).to_numpy()
    snap = snap_days[state_row] / 7.0
    return g, units, price, snap


def build_feature_table(panel, train_weeks=cfg.TRAIN_WEEKS, dev_weeks=cfg.DEV_WEEKS, test_weeks=cfg.TEST_WEEKS):
    """Returns (feature table, g, Y, P). Table columns: gi (group row), week_idx, y, raw + scaled features, split, scale."""
    g, Y, P, snap = build_matrices(panel)
    G, W = Y.shape
    w = panel.weeks
    lag = {"lag_1": baselines.naive(Y), "lag_2": np.full_like(Y, np.nan), "lag_4": np.full_like(Y, np.nan),
           "lag_52": baselines.seasonal_naive(Y, 52), "roll_mean_4": baselines.moving_average(Y, 4),
           "roll_mean_8": baselines.moving_average(Y, 8)}
    lag["lag_2"][:, 2:] = Y[:, :-2]
    lag["lag_4"][:, 4:] = Y[:, :-4]
    with np.errstate(invalid="ignore", divide="ignore"):
        price_ratio = P / baselines.moving_average(P, cfg.EVENT_WINDOW_WEEKS)
    month = w["month"].to_numpy()
    event = (w["event_days"].to_numpy() > 0).astype(float)

    split = splits.assign_split(np.arange(W), train_weeks, dev_weeks, test_weeks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                  # "mean of empty slice" for never-sold series
        scale = np.nanmean(Y[:, :train_weeks], axis=1)                   # per-series mean over TRAIN on-sale weeks
    ok_series = np.isfinite(scale)                                       # (no train on-sale week at all -> cannot be scaled)
    scale = np.maximum(scale, cfg.SCALE_FLOOR)

    valid = ~np.isnan(Y) & (np.arange(W)[None, :] >= cfg.MIN_HISTORY) & (split != "unused")[None, :] & ok_series[:, None]
    for k in LAG_COLS:
        valid &= np.isfinite(lag[k])
    valid &= np.isfinite(price_ratio)
    gi, wi = np.nonzero(valid)

    df = pd.DataFrame({"gi": gi.astype(np.int32), "week_idx": wi.astype(np.int16), "y": Y[gi, wi]})
    sc = scale[gi]
    df["scale"] = sc
    for k in LAG_COLS:
        df[k] = lag[k][gi, wi] / sc
    df["month_sin"] = np.sin(2 * np.pi * month[wi] / 12)
    df["month_cos"] = np.cos(2 * np.pi * month[wi] / 12)
    df["price_ratio"] = price_ratio[gi, wi]
    df["snap_share"] = snap[gi, wi]
    df["event_flag"] = event[wi]
    df["y_scaled"] = df["y"] / sc
    df["split"] = split[wi]
    # helper columns for error analysis / segments (not model inputs)
    df["price"] = P[gi, wi]
    df["price_cut"] = (df["price_ratio"] <= cfg.PRICE_CUT_RATIO).astype(np.int8)
    prev_cut = np.zeros((G, W), dtype=bool)
    prev_cut[:, 1:] = (np.nan_to_num(price_ratio, nan=1.0)[:, :-1] <= cfg.PRICE_CUT_RATIO)
    df["price_cut_lag1"] = prev_cut[gi, wi].astype(np.int8)
    df["prev8_mean"] = df["roll_mean_8"] * sc
    df["month_mid"] = month[wi]
    info = {"n_series_total": G, "n_series_dropped_no_train_sales": int((~ok_series).sum())}
    return df, g, Y, P, info


def winsor_cap(df):
    """Cap for scaled demand: the train 99.9th percentile of relative demand. Applied to model inputs/targets only."""
    return float(np.quantile(df.loc[df["split"] == "train", "y_scaled"], cfg.WINSOR_Q))


def model_matrix(df, cap):
    """Raw (un-standardised) model inputs with demand-like columns capped. Returns an array [rows, len(FEATURES)]."""
    X = df[FEATURES].to_numpy(dtype=float).copy()
    for j, f in enumerate(FEATURES):
        if f in LAG_COLS:
            X[:, j] = np.minimum(X[:, j], cap)
    return X


class Standardizer:
    """z = (x - mean_train) / std_train. fit() on TRAIN rows only; transform() anywhere."""

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0)
        self.std_[self.std_ < 1e-8] = 1.0          # constant column -> avoid divide-by-zero
        return self

    def transform(self, X):
        return (np.asarray(X, dtype=float) - self.mean_) / self.std_

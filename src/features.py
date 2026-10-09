"""
features.py - turn weekly demand into a supervised-learning table.

One row = one SKU in one week. We predict demand of week t using ONLY information known before week t,
plus the promo calendar of week t (promotions are planned in advance, so that is legitimate).

Features (all simple and explainable):
  lag_1, lag_2, lag_4        demand 1, 2, 4 weeks ago
  roll_mean_4, roll_mean_8   average demand of the previous 4 / 8 weeks
  month_sin, month_cos       month of the year on a circle (so December is next to January)
  promo_flag                 1 if the target week has a promotion
  promo_lag1                 1 if the PREVIOUS week had a promotion (its lag value is inflated)

Scaling: SKUs differ by 100x in size, so every SKU's demand is divided by that SKU's TRAIN-period
mean ("relative demand ~ 1.0"). Then each feature is standardised with TRAIN-set mean/std.
Dev and test rows reuse those train numbers -> no leakage from the future.
"""
import numpy as np
import pandas as pd

import config as cfg
import splits

FEATURES = ["lag_1", "lag_2", "lag_4", "roll_mean_4", "roll_mean_8",
            "month_sin", "month_cos", "promo_flag", "promo_lag1"]
MIN_HISTORY = 8     # rolling_mean_8 needs 8 earlier weeks


def build_feature_table(weekly, train_weeks=cfg.TRAIN_WEEKS, dev_weeks=cfg.DEV_WEEKS, test_weeks=cfg.TEST_WEEKS):
    """weekly: output of kpis.weekly_demand(). Returns one tidy table with raw and scaled columns."""
    df = weekly.sort_values(["sku", "week_idx"]).copy()
    df["y"] = df["units_demanded"].astype(float)
    g = df.groupby("sku")["y"]
    for k in (1, 2, 4):
        df[f"lag_{k}"] = g.shift(k)
    shifted = g.shift(1)
    df["roll_mean_4"] = shifted.groupby(df["sku"]).transform(lambda s: s.rolling(4).mean())
    df["roll_mean_8"] = shifted.groupby(df["sku"]).transform(lambda s: s.rolling(8).mean())
    mid_month = (df["week_start"] + pd.Timedelta(days=3)).dt.month
    df["month_sin"] = np.sin(2 * np.pi * mid_month / 12)
    df["month_cos"] = np.cos(2 * np.pi * mid_month / 12)
    df["promo_lag1"] = df.groupby("sku")["promo_flag"].shift(1)
    df["split"] = splits.assign_split(df["week_idx"], train_weeks, dev_weeks, test_weeks)

    # scale = SKU mean demand over TRAIN weeks only
    train_mean = df[df["week_idx"] < train_weeks].groupby("sku")["y"].mean().rename("scale")
    df = df.join(train_mean, on="sku")
    for c in ("lag_1", "lag_2", "lag_4", "roll_mean_4", "roll_mean_8"):
        df[c] = df[c] / df["scale"]
    df["y_scaled"] = df["y"] / df["scale"]
    df = df[(df["week_idx"] >= MIN_HISTORY) & (df["split"] != "unused")].dropna(subset=FEATURES)
    return df.reset_index(drop=True)


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

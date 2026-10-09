"""
error_analysis.py - tag and tally the biggest forecast errors (spreadsheet-style).

Process (Andrew Ng's "error analysis"): take the ~100 largest DEV-set errors, give each a few simple
yes/no tags (promo week? post-promo? outlier? seasonal turn?), then count which cause is most common.
The biggest bucket tells you where improving the model is worth the effort.

Tags are rule-based so the result is reproducible; the CSV also has an empty 'manual_cause' column
for you to override after eyeballing each row in Excel.
"""
import numpy as np
import pandas as pd

import config as cfg

CAUSE_ORDER = ["outlier_week", "promo_week", "post_promo_week", "seasonal_turn", "no_clear_cause"]


def category_season_index(weekly_train, products):
    """Seasonal index by category x month, from TRAIN weeks only (no peeking at dev/test)."""
    w = weekly_train.merge(products[["sku", "category"]], on="sku")
    w["month"] = (w["week_start"] + pd.Timedelta(days=3)).dt.month
    m = w.groupby(["category", "month"])["units_demanded"].mean().unstack("month")
    return m.div(m.mean(axis=1), axis=0)


def tag_errors(df, season_idx):
    """
    df needs: sku, category, month_mid, actual, forecast, promo_flag, promo_lag1, prev8_mean (raw units).
    Adds boolean tag columns + 'primary_cause' (first matching cause in CAUSE_ORDER).
    """
    d = df.copy()
    d["error"] = d["forecast"] - d["actual"]
    d["abs_error"] = d["error"].abs()
    d["pct_error"] = d["error"] / d["actual"].replace(0, np.nan)
    ratio = d["actual"] / d["prev8_mean"].replace(0, np.nan)
    d["tag_outlier_week"] = ((ratio < cfg.OUTLIER_RATIO_LOW) | (ratio > cfg.OUTLIER_RATIO_HIGH)).astype(int)
    d["tag_promo_week"] = (d["promo_flag"] == 1).astype(int)
    d["tag_post_promo_week"] = ((d["promo_lag1"] == 1) & (d["promo_flag"] == 0)).astype(int)
    prev_month = (d["month_mid"] - 2) % 12 + 1
    step = [abs(season_idx.loc[c, m] - season_idx.loc[c, pm]) for c, m, pm in zip(d["category"], d["month_mid"], prev_month)]
    d["tag_seasonal_turn"] = (np.array(step) >= cfg.SEASON_STEP).astype(int)
    conditions = [d["tag_outlier_week"] == 1, d["tag_promo_week"] == 1, d["tag_post_promo_week"] == 1, d["tag_seasonal_turn"] == 1]
    d["primary_cause"] = np.select(conditions, CAUSE_ORDER[:-1], default="no_clear_cause")
    d["direction"] = np.where(d["error"] > 0, "over-forecast", "under-forecast")
    return d


def tally(top):
    """Count top errors by primary cause (with share of the top-N error volume)."""
    g = top.groupby("primary_cause").agg(n_errors=("abs_error", "size"), abs_error_units=("abs_error", "sum"),
                                         under_forecast=("direction", lambda s: int((s == "under-forecast").sum())))
    g = g.reindex(CAUSE_ORDER).fillna(0)
    g["share_of_errors"] = g["n_errors"] / g["n_errors"].sum()
    g["share_of_error_units"] = g["abs_error_units"] / g["abs_error_units"].sum()
    return g.reset_index()


def tally_tags(top):
    """Multi-label view: how many of the top errors carry each tag (a row can have several)."""
    tags = [c for c in top.columns if c.startswith("tag_")]
    return pd.DataFrame({"tag": [c[4:] for c in tags], "n_errors": [int(top[c].sum()) for c in tags],
                         "share": [float(top[c].mean()) for c in tags]})

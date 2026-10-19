"""
error_analysis.py - tag and tally the biggest forecast errors (spreadsheet-style).

Process (Andrew Ng's "error analysis"): take the ~100 largest DEV-set errors, give each a few simple
yes/no tags (price cut? holiday week? outlier? seasonal turn?), then count which cause is most common.
The biggest bucket tells you where improving the model is worth the effort.

Because a tag such as "event week" is true for many ordinary weeks too, the tag table also shows the BASE RATE
(how often the tag is true across ALL dev rows) and the lift = share among top errors / base rate.

Tags are rule-based so the result is reproducible; the CSV also has an empty 'manual_cause' column
for you to override after eyeballing each row in Excel.
"""
import numpy as np
import pandas as pd

import analysis
import config as cfg
import panel as pn

CAUSE_ORDER = ["outlier_week", "price_cut_week", "post_price_cut_week", "seasonal_turn", "event_week", "no_clear_cause"]
TAGS = ["outlier_week", "price_cut_week", "post_price_cut_week", "seasonal_turn", "event_week"]


def category_season_index(panel, train_weeks=cfg.TRAIN_WEEKS):
    """Seasonal index by category x month, from TRAIN weeks only (no peeking at dev/test)."""
    view = pn.Panel(panel.series, panel.weeks.iloc[:train_weeks], panel.units[:, :train_weeks], panel.price[:, :train_weeks])
    return analysis.seasonality_index(view, "cat_id")


def tag_errors(df, season_idx):
    """
    df needs: category, month_mid, actual, forecast, price_cut, price_cut_lag1, event_flag, prev8_mean (raw units).
    Adds 0/1 tag columns + 'primary_cause' (first matching cause in CAUSE_ORDER).
    """
    d = df.copy()
    d["error"] = d["forecast"] - d["actual"]
    d["abs_error"] = d["error"].abs()
    d["pct_error"] = d["error"] / d["actual"].replace(0, np.nan)
    ratio = d["actual"] / d["prev8_mean"].replace(0, np.nan)
    d["tag_outlier_week"] = ((ratio < cfg.OUTLIER_RATIO_LOW) | (ratio > cfg.OUTLIER_RATIO_HIGH)).astype(int)
    d["tag_price_cut_week"] = (d["price_cut"] == 1).astype(int)
    d["tag_post_price_cut_week"] = ((d["price_cut_lag1"] == 1) & (d["price_cut"] == 0)).astype(int)
    d["tag_event_week"] = (d["event_flag"] == 1).astype(int)
    prev_month = (d["month_mid"] - 2) % 12 + 1
    cats, m, pm = d["category"].to_numpy(), d["month_mid"].to_numpy(), prev_month.to_numpy()
    step = np.array([abs(season_idx.loc[c, mm] - season_idx.loc[c, pp]) for c, mm, pp in zip(cats, m, pm)])
    d["tag_seasonal_turn"] = (step >= cfg.SEASON_STEP).astype(int)
    conditions = [d[f"tag_{t}"] == 1 for t in CAUSE_ORDER[:-1]]
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


def tally_tags(top, all_dev):
    """Multi-label view: how many top errors carry each tag, vs how often the tag is true on ALL dev rows (lift)."""
    rows = []
    for t in TAGS:
        c = f"tag_{t}"
        share, base = float(top[c].mean()), float(all_dev[c].mean())
        rows.append(dict(tag=t, n_errors=int(top[c].sum()), share=share, base_rate_all_dev_rows=base, lift=share / base if base > 0 else np.nan))
    return pd.DataFrame(rows)

"""analysis.py - small demand-analysis helpers (seasonality, weekday pattern, price-cut uplift, growth)."""
import numpy as np
import pandas as pd

import baselines
import config as cfg


def complete_years(weeks):
    """Calendar years in which all 12 months are present (the first and last year of M5 are partial)."""
    n_months = weeks.groupby("year")["month"].nunique()
    return [int(y) for y in n_months[n_months == 12].index]


def group_rate_by_week(panel, by):
    """Units per on-sale item-store per week for each group (dept / category). Normalising by the number of items on sale
    removes the effect of the assortment growing over time, so seasonality is not mixed up with new items."""
    on = panel.onsale
    keys = sorted(panel.series[by].unique())
    rate = {}
    for k in keys:
        idx = np.where(panel.series[by].to_numpy() == k)[0]
        rate[k] = panel.units[idx].sum(axis=0) / np.maximum(on[idx].sum(axis=0), 1)
    return pd.DataFrame(rate, index=panel.weeks["week_idx"]).T


def seasonality_index(panel, by="dept_id"):
    """
    Seasonal index by group x calendar month, from COMPLETE years only.
    For each year: month's average weekly rate / that year's average weekly rate; then average over the years.
    1.20 = 20% above a normal month.
    """
    rate = group_rate_by_week(panel, by)
    w = panel.weeks.set_index("week_idx")
    years = complete_years(panel.weeks)
    out = {}
    for k, row in rate.iterrows():
        df = pd.DataFrame({"rate": row, "year": w["year"], "month": w["month"]})
        df = df[df["year"].isin(years)]
        m = df.groupby(["year", "month"])["rate"].mean().unstack("month")
        out[k] = m.div(m.mean(axis=1), axis=0).mean(axis=0)
    return pd.DataFrame(out).T


def weekday_index(daily):
    """Weekday units relative to the average day, by category (from the daily store x dept table)."""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["category"] = d["dept_id"].str.split("_").str[0]
    d["weekday"] = d["date"].dt.day_name()
    day = d.groupby(["category", "date", "weekday"], as_index=False)["units"].sum()
    m = day.groupby(["category", "weekday"])["units"].mean().unstack("weekday")
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    m = m[order]
    return m.div(m.mean(axis=1), axis=0)


def price_cut_uplift(units, price, k=cfg.EVENT_WINDOW_WEEKS, cut_ratio=cfg.PRICE_CUT_RATIO):
    """
    Item x state weekly matrices -> table: how do units in a price-cut week compare with the item's previous k weeks?
        price ratio = price / mean price of previous k weeks      (<= 0.90 = a price-cut week)
        unit ratio  = units / mean units of previous k weeks
    This is an ASSOCIATION (cuts may be timed with seasons or events), not a causal elasticity.
    """
    p_prev = baselines.moving_average(price, k)
    u_prev = baselines.moving_average(units, k)
    with np.errstate(invalid="ignore", divide="ignore"):
        pr = price / p_prev
        ur = units / u_prev
    ok = np.isfinite(pr) & np.isfinite(ur) & (u_prev > 0)
    cut = ok & (pr <= cut_ratio)
    cut_prev = np.zeros_like(cut)
    cut_prev[:, 1:] = cut[:, :-1]
    post = ok & ~cut & cut_prev
    normal = ok & ~cut & ~cut_prev
    rows = []
    for name, m in (("price-cut week", cut), ("week after a price cut", post), ("normal week", normal)):
        rows.append(dict(week_type=name, n_item_state_weeks=int(m.sum()), share_of_weeks=float(m.sum() / ok.sum()),
                         median_unit_ratio=float(np.median(ur[m])), mean_unit_ratio=float(ur[m].mean())))
    return pd.DataFrame(rows)

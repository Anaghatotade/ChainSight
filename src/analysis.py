"""analysis.py - small demand-analysis helpers (trend, seasonality, region mix, promo uplift)."""
import numpy as np
import pandas as pd


def seasonality_index(demand_daily, products):
    """
    Seasonal index by category x calendar month.
    For each year, month demand / average month demand of that year; then average over the years.
    1.20 = 20% above a normal month. (Trend is only partly removed - fine for an EDA view.)
    """
    d = demand_daily.merge(products[["sku", "category"]], on="sku")
    d["year"], d["month"] = d["date"].dt.year, d["date"].dt.month
    m = d.groupby(["category", "year", "month"], as_index=False)["units_demanded"].sum()
    m["idx"] = m["units_demanded"] / m.groupby(["category", "year"])["units_demanded"].transform("mean")
    return m.groupby(["category", "month"])["idx"].mean().unstack("month")


def weekly_trend_pct_per_year(weekly_totals):
    """Straight-line trend of a weekly series, expressed as % change per year of the average level."""
    y = np.asarray(weekly_totals, dtype=float)
    slope = np.polyfit(np.arange(len(y)), y, 1)[0]
    return float(slope * 52 / y.mean())


def category_trends(weekly, products):
    w = weekly.merge(products[["sku", "category"]], on="sku")
    tot = w.groupby(["category", "week_idx"])["units_demanded"].sum().reset_index()
    rows = [dict(category=c, trend_pct_per_year=weekly_trend_pct_per_year(g.sort_values("week_idx")["units_demanded"]))
            for c, g in tot.groupby("category")]
    return pd.DataFrame(rows).sort_values("trend_pct_per_year", ascending=False).reset_index(drop=True)


def region_mix(demand_daily, warehouses):
    d = demand_daily.merge(warehouses[["warehouse_code", "region"]], on="warehouse_code")
    out = d.groupby("region")["units_demanded"].sum().rename("units_demanded").reset_index()
    out["share"] = out["units_demanded"] / out["units_demanded"].sum()
    return out.sort_values("units_demanded", ascending=False).reset_index(drop=True)


def promo_uplift(weekly):
    """
    How much higher is demand in a promo week than in the weeks before it?
    ratio = demand this week / average demand of the previous 8 weeks (per SKU), compared for promo vs normal weeks.
    """
    w = weekly.sort_values(["sku", "week_idx"]).copy()
    prev8 = w.groupby("sku")["units_demanded"].transform(lambda s: s.shift(1).rolling(8).mean())
    w["ratio"] = w["units_demanded"] / prev8
    w = w.dropna(subset=["ratio"])
    return w.groupby("promo_flag")["ratio"].agg(median_ratio="median", mean_ratio="mean", n_weeks="size").reset_index()

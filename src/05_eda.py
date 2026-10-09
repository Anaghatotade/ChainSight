"""
Step 5 - Exploratory Data Analysis: trend, seasonality, region/category/SKU cuts, promo effect.

Reads  data/processed/*.csv
Writes outputs/charts/eda_*.png, outputs/tables/eda_*.csv, adds numbers to outputs/tables/key_numbers.json

Every chart ends with a "so what" in the README - the numbers for it are saved to key_numbers.json.

Run:  python src/05_eda.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import analysis
import config as cfg
import keynums as nums
import kpis
import viz

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def main():
    cfg.ensure_dirs()
    viz.setup()
    t = kpis.load_clean()
    weekly = kpis.weekly_demand(t)
    prod, wh = t["products"], t["warehouses"]
    N = {}

    # ---------------------------------------------------------------- 1. overall weekly trend
    total = weekly.groupby("week_start")["units_demanded"].sum().sort_index()
    ma = total.rolling(4).mean()
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(total.index, total.values, color=viz.PALETTE["grey"], alpha=0.6, label="Weekly demand (units)")
    ax.plot(ma.index, ma.values, color=viz.PALETTE["main"], lw=2.5, label="4-week moving average")
    ax.set_title("Total weekly demand - all SKUs")
    ax.set_ylabel("Units demanded"); ax.legend()
    viz.save(fig, "eda_01_weekly_demand_trend")
    N["eda_trend_total_pct_per_year"] = analysis.weekly_trend_pct_per_year(total.values)
    N["eda_weekly_demand_peak_units"] = total.max()
    N["eda_weekly_demand_peak_week"] = str(total.idxmax().date())
    first_half, second_half = total.iloc[:52].sum(), total.iloc[52:].sum()
    N["eda_yoy_growth_total"] = second_half / first_half - 1

    # ---------------------------------------------------------------- 2. category trends
    trends = analysis.category_trends(weekly, prod)
    trends.to_csv(cfg.TABLES / "eda_category_trends.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = [viz.PALETTE["good"] if v >= 0 else viz.PALETTE["bad"] for v in trends["trend_pct_per_year"]]
    ax.barh(trends["category"], trends["trend_pct_per_year"], color=colors)
    ax.invert_yaxis(); viz.pct_axis(ax, "x")
    ax.set_title("Demand trend by category (% change per year)")
    viz.save(fig, "eda_02_category_trend")
    N["eda_fastest_growing_category"] = trends.iloc[0]["category"]
    N["eda_fastest_growing_pct"] = trends.iloc[0]["trend_pct_per_year"]
    N["eda_slowest_category"] = trends.iloc[-1]["category"]
    N["eda_slowest_pct"] = trends.iloc[-1]["trend_pct_per_year"]

    # ---------------------------------------------------------------- 3. seasonality heatmap
    seas = analysis.seasonality_index(t["demand_daily"], prod)
    seas.columns = MONTHS
    seas.round(3).to_csv(cfg.TABLES / "eda_seasonality_index.csv")
    fig, ax = plt.subplots(figsize=(11, 4.2))
    sns.heatmap(seas, annot=True, fmt=".2f", cmap="RdYlGn", center=1.0, ax=ax, cbar_kws={"label": "Seasonal index (1.0 = normal month)"})
    ax.set_title("Seasonality by category: demand index per calendar month"); ax.set_ylabel("")
    viz.save(fig, "eda_03_seasonality_heatmap")
    peak = seas.idxmax(axis=1)
    N["eda_seasonality_peak_months"] = "; ".join(f"{c}: {m}" for c, m in peak.items())
    amp = (seas.max(axis=1) - seas.min(axis=1)).sort_values(ascending=False)
    N["eda_most_seasonal_category"] = amp.index[0]
    N["eda_most_seasonal_swing"] = amp.iloc[0]
    N["eda_least_seasonal_category"] = amp.index[-1]
    N["eda_least_seasonal_swing"] = amp.iloc[-1]

    # ---------------------------------------------------------------- 4. region / warehouse cut
    region = analysis.region_mix(t["demand_daily"], wh)
    region.to_csv(cfg.TABLES / "eda_region_mix.csv", index=False)
    d = t["demand_daily"].merge(wh[["warehouse_code", "region"]], on="warehouse_code")
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    pivot = d.pivot_table(index="month", columns="region", values="units_demanded", aggfunc="sum")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    pivot.plot.area(ax=ax, alpha=0.85, linewidth=0)
    ax.set_title("Monthly demand by warehouse region"); ax.set_ylabel("Units demanded"); ax.set_xlabel("")
    viz.save(fig, "eda_04_demand_by_region")
    N["eda_top_region"] = region.iloc[0]["region"]
    N["eda_top_region_share"] = region.iloc[0]["share"]

    # ---------------------------------------------------------------- 5. SKU profile: volume vs variability
    sku = kpis.build_sku_kpis(t)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].hist(np.log10(sku["avg_daily_demand"]), bins=20, color=viz.PALETTE["main"])
    axes[0].set_xlabel("log10(average daily demand per SKU)"); axes[0].set_ylabel("Number of SKUs")
    axes[0].set_title("SKU volumes are very uneven")
    for band, c in zip(["Low", "Medium", "High"], [viz.PALETTE["good"], viz.PALETTE["accent"], viz.PALETTE["bad"]]):
        s = sku[sku["cv_band"] == band]
        axes[1].scatter(s["avg_daily_demand"], s["demand_cv"], label=f"{band} CV ({len(s)})", color=c, alpha=0.8)
    axes[1].set_xscale("log"); axes[1].set_xlabel("Average daily demand (log scale)"); axes[1].set_ylabel("Demand CV (std / mean)")
    axes[1].set_title("Variability vs volume"); axes[1].legend()
    viz.save(fig, "eda_05_sku_volume_vs_cv")
    N["eda_sku_median_daily_demand"] = sku["avg_daily_demand"].median()
    N["eda_sku_max_over_min_volume"] = sku["avg_daily_demand"].max() / sku["avg_daily_demand"].min()
    N["eda_cv_median"] = sku["demand_cv"].median()
    N["eda_cv_high_count"] = int((sku["cv_band"] == "High").sum())
    N["eda_cv_medium_count"] = int((sku["cv_band"] == "Medium").sum())
    N["eda_cv_low_count"] = int((sku["cv_band"] == "Low").sum())

    # ---------------------------------------------------------------- 6. promo effect
    up = analysis.promo_uplift(weekly)
    up.to_csv(cfg.TABLES / "eda_promo_uplift.csv", index=False)
    r_promo = float(up.loc[up["promo_flag"] == 1, "median_ratio"].iloc[0])
    r_norm = float(up.loc[up["promo_flag"] == 0, "median_ratio"].iloc[0])
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["Normal weeks", "Promo weeks"], [r_norm, r_promo], color=[viz.PALETTE["grey"], viz.PALETTE["accent"]])
    ax.axhline(1.0, color="black", lw=1, ls="--")
    ax.set_ylabel("Demand / average of previous 8 weeks (median)")
    ax.set_title("Promotions lift weekly demand")
    for i, v in enumerate([r_norm, r_promo]):
        ax.text(i, v + 0.01, f"{v:.2f}x", ha="center")
    viz.save(fig, "eda_06_promo_uplift")
    N["eda_promo_ratio"] = r_promo
    N["eda_normal_ratio"] = r_norm
    N["eda_promo_week_share"] = weekly["promo_flag"].mean()

    # ---------------------------------------------------------------- 7. demand concentration
    N["eda_n_weeks"] = int(weekly["week_idx"].nunique())
    N["eda_total_units_demanded"] = int(weekly["units_demanded"].sum())
    sku[["sku", "product_name", "category", "avg_daily_demand", "demand_cv", "cv_band", "revenue", "abc_class"]].to_csv(
        cfg.TABLES / "eda_sku_profile.csv", index=False)

    nums.save(N)
    for k, v in N.items():
        print(f"{k:<34} {v}")


if __name__ == "__main__":
    main()

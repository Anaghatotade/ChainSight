"""
kpis.py - KPI formulas (pure functions, easy to test) and builders that apply them to the real M5 panel.

WHAT THE DATA CAN AND CANNOT GIVE US
  REAL (measured from the data):  units, revenue (units x price), average price, ABC class, weekly demand CV,
                                  intermittency (share of on-sale weeks with zero units), demand class, seasonality, growth.
  ASSUMED (clearly labelled):     safety stock / reorder point / order-up-to level. They need a lead time, which M5 does not
                                  contain, so config.ASSUMED_LEAD_TIME_WEEKS is an assumption applied on top of REAL demand variability.
  NOT AVAILABLE:                  fill rate, stockout rate, inventory turnover, days of inventory, supplier lead-time reliability.
                                  (M5 has no stock levels, so a week with zero sales cannot be told apart from a stockout.)
"""
import numpy as np
import pandas as pd

import config as cfg


# ------------------------------------------------------------------ pure formulas
def demand_cv(x):
    """Coefficient of variation = std / mean (population std). NaN if the mean is zero."""
    x = np.asarray(x, dtype=float)
    m = x.mean()
    return float(x.std() / m) if m > 0 else np.nan


def cv_band(cv):
    """stable < 0.5 <= variable < 1.0 <= erratic (weekly CV, item x state level)."""
    if pd.isna(cv):
        return np.nan
    return "stable" if cv < cfg.CV_LOW else ("variable" if cv < cfg.CV_HIGH else "erratic")


def demand_class(adi, cv2):
    """Syntetos-Boylan classes: ADI = average weeks between demands, CV2 = squared CV of the non-zero weeks."""
    if pd.isna(adi) or pd.isna(cv2):
        return np.nan
    if adi < cfg.ADI_CUTOFF:
        return "smooth" if cv2 < cfg.CV2_CUTOFF else "erratic"
    return "intermittent" if cv2 < cfg.CV2_CUTOFF else "lumpy"


def safety_stock(sigma_weekly, lead_time_weeks=None, review_weeks=None, z=None):
    """SS = z x sigma_weekly x sqrt(lead time + review period). Lead time is an ASSUMPTION (see config)."""
    lt = cfg.ASSUMED_LEAD_TIME_WEEKS if lead_time_weeks is None else lead_time_weeks
    rp = cfg.REVIEW_PERIOD_WEEKS if review_weeks is None else review_weeks
    zz = cfg.SERVICE_Z if z is None else z
    return zz * np.asarray(sigma_weekly, dtype=float) * np.sqrt(lt + rp)


def reorder_point(mean_weekly, ss, lead_time_weeks=None):
    """ROP = demand during the lead time + safety stock."""
    lt = cfg.ASSUMED_LEAD_TIME_WEEKS if lead_time_weeks is None else lead_time_weeks
    return np.asarray(mean_weekly, dtype=float) * lt + ss


def order_up_to(mean_weekly, ss, lead_time_weeks=None, review_weeks=None):
    """S = demand during (lead time + review period) + safety stock (periodic-review policy)."""
    lt = cfg.ASSUMED_LEAD_TIME_WEEKS if lead_time_weeks is None else lead_time_weeks
    rp = cfg.REVIEW_PERIOD_WEEKS if review_weeks is None else review_weeks
    return np.asarray(mean_weekly, dtype=float) * (lt + rp) + ss


def abc_classify(revenue):
    """
    ABC by cumulative revenue share. Input: Series indexed by item. Output: Series of 'A'/'B'/'C' on the same index.
    Sort by revenue (ties by index so the result is repeatable); the cumulative share BEFORE an item decides its class,
    so the item that crosses the 80% line is still an A (same rule as sql/03_abc_analysis.sql).
    """
    r = revenue.rename("rev").to_frame()
    r["key"] = r.index.astype(str)
    r = r.sort_values(["rev", "key"], ascending=[False, True])
    before = (r["rev"].cumsum() - r["rev"]) / r["rev"].sum()
    cls = np.where(before < cfg.ABC_A_CUTOFF, "A", np.where(before < cfg.ABC_B_CUTOFF, "B", "C"))
    return pd.Series(cls, index=r.index).reindex(revenue.index)


# ------------------------------------------------------------------ aggregation helpers
def item_state_index(panel):
    """Series -> (item, state) group number. Returns the group table and the group id of every series."""
    g = panel.series.drop_duplicates(["item_id", "state_id"])[["item_id", "state_id", "dept_id", "cat_id"]]
    g = g.sort_values(["item_id", "state_id"]).reset_index(drop=True)
    key = pd.MultiIndex.from_frame(g[["item_id", "state_id"]])
    gid = key.get_indexer(pd.MultiIndex.from_frame(panel.series[["item_id", "state_id"]]))
    return g, gid


def aggregate_item_state(panel):
    """
    Weekly series at ITEM x STATE level (what a regional distribution centre plans):
      units  [G, W]  sum over the state's stores            (NaN = no store of the state had the item on sale)
      price  [G, W]  mean price over the on-sale stores     (NaN when not on sale)
      stores [G, W]  number of stores selling the item that week
    """
    g, gid = item_state_index(panel)
    on = panel.onsale
    G, W = len(g), panel.n_weeks
    units = np.zeros((G, W)); psum = np.zeros((G, W)); cnt = np.zeros((G, W))
    np.add.at(units, gid, panel.units * on)
    np.add.at(psum, gid, np.nan_to_num(panel.price))
    np.add.at(cnt, gid, on.astype(float))
    price = np.where(cnt > 0, psum / np.maximum(cnt, 1), np.nan)
    units = np.where(cnt > 0, units, np.nan)
    return g, units, price, cnt


# ------------------------------------------------------------------ builders (DataFrames)
def weekly_totals(panel):
    """One row per week: units, revenue, number of on-sale item-store series."""
    w = panel.weeks.copy()
    w["units"] = panel.units.sum(axis=0)
    w["revenue"] = panel.revenue().sum(axis=0)
    w["n_series_on_sale"] = panel.onsale.sum(axis=0)
    return w


def build_overall_kpis(panel):
    on = panel.onsale
    rev = panel.revenue()
    return {
        "n_items": panel.series["item_id"].nunique(), "n_stores": panel.series["store_id"].nunique(), "n_weeks": panel.n_weeks,
        "on_sale_series_weeks": int(on.sum()), "total_units": int(panel.units.sum()), "total_revenue": float(rev.sum()),
        "avg_selling_price": float(rev.sum() / panel.units.sum()),
        "zero_sales_week_pct": float(100.0 * ((panel.units == 0) & on).sum() / on.sum()),
    }


def build_cut_kpis(panel, by):
    """Units / revenue / price / items for one grouping column of `series` (cat_id, dept_id, store_id, state_id)."""
    rev, on = panel.revenue(), panel.onsale
    df = pd.DataFrame({by: panel.series[by], "units": panel.units.sum(axis=1), "revenue": rev.sum(axis=1),
                       "on_sale_weeks": on.sum(axis=1), "zero_weeks": ((panel.units == 0) & on).sum(axis=1)})
    g = df.groupby(by).agg(units=("units", "sum"), revenue=("revenue", "sum"), on_sale_weeks=("on_sale_weeks", "sum"),
                           zero_weeks=("zero_weeks", "sum"))
    g["n_items"] = panel.series.groupby(by)["item_id"].nunique()
    g["revenue_share"] = g["revenue"] / g["revenue"].sum()
    g["avg_selling_price"] = g["revenue"] / g["units"]
    g["revenue_per_on_sale_week"] = g["revenue"] / g["on_sale_weeks"]
    g["zero_week_share"] = g["zero_weeks"] / g["on_sale_weeks"]
    return g.sort_values("revenue", ascending=False).reset_index()


def build_monthly_kpis(panel):
    w = weekly_totals(panel)
    m = w.groupby(["year", "month"]).agg(n_weeks=("week_idx", "size"), units=("units", "sum"), revenue=("revenue", "sum")).reset_index()
    m["revenue_per_week"] = m["revenue"] / m["n_weeks"]
    return m


def build_item_kpis(panel):
    """One row per item (all stores together): volume, revenue, ABC class, weekly CV, intermittency."""
    rev, on = panel.revenue(), panel.onsale
    s = panel.series
    item = s["item_id"].to_numpy()
    df = pd.DataFrame({"item_id": item, "units": panel.units.sum(axis=1), "revenue": rev.sum(axis=1),
                       "on_sale_weeks": on.sum(axis=1), "zero_weeks": ((panel.units == 0) & on).sum(axis=1)})
    out = df.groupby("item_id").sum()
    out = out.join(s.drop_duplicates("item_id").set_index("item_id")[["dept_id", "cat_id"]])
    out["avg_selling_price"] = out["revenue"] / out["units"]
    out["zero_week_share"] = out["zero_weeks"] / out["on_sale_weeks"]
    out["abc_class"] = abc_classify(out["revenue"])
    out = out.sort_values("revenue", ascending=False)
    out["revenue_share"] = out["revenue"] / out["revenue"].sum()
    out["cum_revenue_share"] = out["revenue_share"].cumsum()
    return out.reset_index()


def build_item_state_kpis(panel, item_kpis):
    """
    One row per item x state: weekly mean / std / CV, intermittency (ADI, CV2), demand class, ABC class of the item,
    and the ASSUMPTION-based inventory policy (safety stock, reorder point, order-up-to) from the last 52 on-sale weeks.
    """
    g, units, price, _ = aggregate_item_state(panel)
    _, gid = item_state_index(panel)
    W = units.shape[1]
    last = slice(W - 52, W)
    on_any = ~np.isnan(units)
    mean = np.nanmean(units, axis=1)
    std = np.nanstd(units, axis=1)
    weeks_on = on_any.sum(axis=1)
    zero_share = np.nansum(units == 0, axis=1) / np.maximum(weeks_on, 1)
    nz = np.where(units > 0, units, np.nan)
    n_nz = (units > 0).sum(axis=1)
    adi = np.where(n_nz > 0, weeks_on / np.maximum(n_nz, 1), np.nan)
    cv2_nz = (np.nanstd(nz, axis=1) / np.nanmean(nz, axis=1)) ** 2
    u52, p52 = units[:, last], price[:, last]
    weeks52 = (~np.isnan(u52)).sum(axis=1)
    mean52 = np.where(weeks52 >= 26, np.nanmean(u52, axis=1), np.nan)
    std52 = np.where(weeks52 >= 26, np.nanstd(u52, axis=1), np.nan)
    price_last = np.nanmean(p52[:, -4:], axis=1)
    rev = np.zeros(len(g))
    np.add.at(rev, gid, panel.revenue().sum(axis=1))          # exact revenue (sum of the stores' own revenue)
    df = g.copy()
    df["weeks_on_sale"], df["mean_weekly_units"], df["std_weekly_units"] = weeks_on, mean, std
    df["cv"] = np.where(mean > 0, std / np.where(mean > 0, mean, 1), np.nan)
    df["cv_band"] = df["cv"].map(cv_band)
    df["zero_week_share"], df["adi"], df["cv2_nonzero"] = zero_share, adi, cv2_nz
    df["demand_class"] = [demand_class(a, c) for a, c in zip(adi, cv2_nz)]
    df["revenue"] = rev
    df = df.merge(item_kpis[["item_id", "abc_class"]], on="item_id", how="left")
    df["mean_units_last52"], df["std_units_last52"], df["weeks_on_sale_last52"] = mean52, std52, weeks52
    df["price_latest"] = price_last
    ss = safety_stock(std52)
    df["safety_stock_units"] = ss
    df["reorder_point_units"] = reorder_point(mean52, ss)
    df["order_up_to_units"] = order_up_to(mean52, ss)
    df["safety_stock_retail_value"] = df["safety_stock_units"] * df["price_latest"]
    df["safety_stock_weeks_of_cover"] = np.where(mean52 > 0, ss / np.where(mean52 > 0, mean52, 1), np.nan)
    return df

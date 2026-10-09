"""
kpis.py - supply-chain KPI formulas and the tables built from them.

Part 1: tiny, pure formula functions (easy to unit-test and easy to explain).
Part 2: build_* functions that apply the formulas to the cleaned tables.

KPI definitions used everywhere in this project
------------------------------------------------
fill rate            = units fulfilled / units demanded
stockout rate        = share of SKU-warehouse-days where demand was NOT fully met
inventory turnover   = annualised COGS / average inventory value      (COGS = fulfilled units x unit cost)
days of inventory    = average units on hand / average daily units sold
safety stock         = z x sqrt( (LT + R) x sigma_d^2  +  mean_d^2 x sigma_LT^2 )
reorder point        = mean daily demand x mean lead time + safety stock
demand CV            = standard deviation of daily demand / mean daily demand
ABC class            = by cumulative share of revenue (A = first 80%, B = next 15%, C = last 5%)
"""
import numpy as np
import pandas as pd

import config as cfg


# =============================================================================
# PART 1 - formulas
# =============================================================================
def fill_rate(units_demanded, units_fulfilled):
    """Share of demanded units that were actually delivered. Returns NaN if nothing was demanded."""
    demanded = float(np.sum(units_demanded))
    return float(np.sum(units_fulfilled)) / demanded if demanded > 0 else np.nan


def stockout_rate(stockout_flags):
    """Share of observation-days (rows) flagged as a stockout."""
    flags = np.asarray(stockout_flags)
    return float(flags.mean()) if len(flags) else np.nan


def inventory_turnover(cogs, avg_inventory_value, n_days):
    """Annualised turnover: how many times per year the average inventory is 'sold through'."""
    if avg_inventory_value is None or avg_inventory_value <= 0:
        return np.nan
    return float(cogs) * (365.0 / n_days) / float(avg_inventory_value)


def days_of_inventory(avg_units_on_hand, avg_daily_units_sold):
    """How many days the average stock would last at the average selling rate."""
    return float(avg_units_on_hand) / float(avg_daily_units_sold) if avg_daily_units_sold > 0 else np.nan


def demand_cv(daily_demand):
    """Coefficient of variation = std / mean. Unit-free, so SKUs of different sizes are comparable."""
    x = np.asarray(daily_demand, dtype=float)
    return float(x.std(ddof=1) / x.mean()) if len(x) > 1 and x.mean() > 0 else np.nan


def safety_stock(z, sigma_daily, lead_time_days, review_days=0.0, lead_time_std_days=0.0, mean_daily=0.0):
    """
    Safety stock covering BOTH demand variability and lead-time variability:
        z * sqrt( (LT + R) * sigma_d^2 + mean_d^2 * sigma_LT^2 )
    With review_days=0 and lead_time_std_days=0 it reduces to the textbook z * sigma_d * sqrt(LT).
    """
    variance = (lead_time_days + review_days) * sigma_daily ** 2 + (mean_daily ** 2) * lead_time_std_days ** 2
    return float(z * np.sqrt(variance))


def reorder_point(mean_daily, lead_time_days, safety_stock_units):
    """Order when stock position falls to: demand during lead time + safety stock."""
    return float(mean_daily * lead_time_days + safety_stock_units)


def abc_classify(revenue, a_cut=cfg.ABC_A_CUTOFF, b_cut=cfg.ABC_B_CUTOFF):
    """
    ABC classes from a revenue Series (index = SKU).
    Sort by revenue (high -> low), look at the cumulative share of revenue BEFORE each item:
    if the items before it have not yet reached 80% of revenue, the item is A (so the item that
    crosses the 80% line is still an A). Ties are broken by index so the result is deterministic.
    """
    rev = revenue.fillna(0).sort_index(kind="mergesort").sort_values(ascending=False, kind="mergesort")
    total = rev.sum()
    share_before = (rev.cumsum() - rev) / total if total > 0 else rev * 0
    cls = np.where(share_before < a_cut, "A", np.where(share_before < b_cut, "B", "C"))
    return pd.Series(cls, index=rev.index, name="abc_class")


def cv_band(cv, low=cfg.CV_LOW, high=cfg.CV_HIGH):
    """Label demand variability: Low / Medium / High."""
    if pd.isna(cv):
        return "Unknown"
    return "Low" if cv < low else ("Medium" if cv < high else "High")


# =============================================================================
# PART 2 - KPI tables from the cleaned data
# =============================================================================
def load_clean():
    """Read the cleaned CSVs from data/processed."""
    dates = {"demand_daily": ["date"], "inventory_daily": ["date"], "inventory_policy": ["policy_set_date"],
             "purchase_orders": ["order_date", "promised_delivery_date", "actual_delivery_date"]}
    names = ["warehouses", "products", "suppliers", "demand_daily", "inventory_daily", "inventory_policy",
             "purchase_orders"]
    return {n: pd.read_csv(cfg.DATA_PROCESSED / f"{n}.csv", parse_dates=dates.get(n, [])) for n in names}


def build_sku_kpis(t):
    """One row per SKU (all warehouses combined): the master KPI table."""
    d, inv, prod = t["demand_daily"], t["inventory_daily"], t["products"].set_index("sku")
    n_days = d["date"].nunique()

    sku_day = d.groupby(["sku", "date"], as_index=False)[["units_demanded", "units_fulfilled"]].sum()
    g = sku_day.groupby("sku")
    out = pd.DataFrame({
        "units_demanded": g["units_demanded"].sum(),
        "units_fulfilled": g["units_fulfilled"].sum(),
        "avg_daily_demand": g["units_demanded"].mean(),
        "demand_cv": g["units_demanded"].apply(demand_cv),
    })
    out["fill_rate"] = out["units_fulfilled"] / out["units_demanded"]
    out["stockout_rate"] = d.groupby("sku")["stockout_flag"].mean()          # SKU-warehouse-day basis
    out["lost_units"] = out["units_demanded"] - out["units_fulfilled"]

    out = out.join(prod[["product_name", "category", "sub_category", "unit_cost", "unit_price", "supplier_code"]])
    out["revenue"] = out["units_fulfilled"] * out["unit_price"]
    out["lost_revenue"] = out["lost_units"] * out["unit_price"]
    out["cogs"] = out["units_fulfilled"] * out["unit_cost"]

    stock_day = inv.groupby(["sku", "date"], as_index=False)["on_hand_units"].sum()
    out["avg_inventory_units"] = stock_day.groupby("sku")["on_hand_units"].mean()
    out["avg_inventory_value"] = out["avg_inventory_units"] * out["unit_cost"]
    out["inventory_turnover"] = [inventory_turnover(c, v, n_days) for c, v in zip(out["cogs"], out["avg_inventory_value"])]
    out["days_of_inventory"] = [days_of_inventory(u, f / n_days) for u, f in zip(out["avg_inventory_units"], out["units_fulfilled"])]

    out["abc_class"] = abc_classify(out["revenue"])
    out["cv_band"] = out["demand_cv"].apply(cv_band)
    out["revenue_share"] = out["revenue"] / out["revenue"].sum()
    return out.reset_index().sort_values("revenue", ascending=False).reset_index(drop=True)


def _group_kpis(d, inv_value_by_day, n_days):
    """Fill rate / stockout / turnover for any slice of demand rows (helper for category, warehouse, month)."""
    cogs = d["cogs"].sum()
    avg_inv = inv_value_by_day.mean() if len(inv_value_by_day) else np.nan
    return pd.Series({
        "units_demanded": d["units_demanded"].sum(),
        "revenue": d["revenue"].sum(),
        "lost_revenue": d["lost_revenue"].sum(),
        "fill_rate": fill_rate(d["units_demanded"], d["units_fulfilled"]),
        "stockout_rate": stockout_rate(d["stockout_flag"]),
        "avg_inventory_value": avg_inv,
        "inventory_turnover": inventory_turnover(cogs, avg_inv, n_days),
    })


def _enrich(t):
    """Attach prices/costs/category to demand and inventory rows once, so every cut is a one-liner."""
    prod = t["products"][["sku", "category", "unit_cost", "unit_price"]]
    wh = t["warehouses"][["warehouse_code", "region"]].rename(columns={"region": "wh_region"})
    d = t["demand_daily"].merge(prod, on="sku").merge(wh, on="warehouse_code")
    d["revenue"] = d["units_fulfilled"] * d["unit_price"]
    d["cogs"] = d["units_fulfilled"] * d["unit_cost"]
    d["lost_revenue"] = (d["units_demanded"] - d["units_fulfilled"]) * d["unit_price"]
    inv = t["inventory_daily"].merge(prod, on="sku").merge(wh, on="warehouse_code")
    inv["inv_value"] = inv["on_hand_units"] * inv["unit_cost"]
    return d, inv


def build_cut_kpis(t, by):
    """KPIs by 'category', 'warehouse_code' or 'wh_region'."""
    d, inv = _enrich(t)
    n_days = d["date"].nunique()
    rows = []
    for key, part in d.groupby(by):
        inv_by_day = inv[inv[by] == key].groupby("date")["inv_value"].sum()
        s = _group_kpis(part, inv_by_day, n_days)
        s[by] = key
        rows.append(s)
    return pd.DataFrame(rows).set_index(by).reset_index()


def build_monthly_kpis(t):
    """Company-level KPIs per calendar month (turnover annualised using that month's days)."""
    d, inv = _enrich(t)
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    inv["month"] = inv["date"].dt.to_period("M").dt.to_timestamp()
    rows = []
    for m, part in d.groupby("month"):
        inv_by_day = inv[inv["month"] == m].groupby("date")["inv_value"].sum()
        s = _group_kpis(part, inv_by_day, part["date"].nunique())
        s["month"] = m
        rows.append(s)
    return pd.DataFrame(rows).reset_index(drop=True)


def build_overall_kpis(t):
    """Headline numbers for the whole business (these feed the README)."""
    d, inv = _enrich(t)
    n_days = d["date"].nunique()
    s = _group_kpis(d, inv.groupby("date")["inv_value"].sum(), n_days)
    s["days_of_inventory"] = days_of_inventory(inv.groupby("date")["on_hand_units"].sum().mean(),
                                               d["units_fulfilled"].sum() / n_days)
    s["n_skus"] = d["sku"].nunique()
    s["n_days"] = n_days
    return s


def build_abc_summary(sku_kpis, n_days):
    """What each ABC class contributes and how it is served."""
    g = sku_kpis.groupby("abc_class")
    out = pd.DataFrame({
        "n_skus": g.size(),
        "revenue": g["revenue"].sum(),
        "avg_inventory_value": g["avg_inventory_value"].sum(),
        "lost_revenue": g["lost_revenue"].sum(),
        "units_demanded": g["units_demanded"].sum(),
        "units_fulfilled": g["units_fulfilled"].sum(),
        "cogs": g["cogs"].sum(),
    })
    out["revenue_share"] = out["revenue"] / out["revenue"].sum()
    out["inventory_share"] = out["avg_inventory_value"] / out["avg_inventory_value"].sum()
    out["fill_rate"] = out["units_fulfilled"] / out["units_demanded"]
    out["inventory_turnover"] = out["cogs"] / out["avg_inventory_value"] * (365.0 / n_days)
    return out.reset_index().drop(columns=["units_demanded", "units_fulfilled", "cogs"])


# ---------------------------------------------------------------- lead time
def delivered_pos(po):
    """POs with a valid delivery date (the only ones that can be used for lead-time statistics)."""
    return po[po["actual_lead_days"].notna()].copy()


def build_lead_time_by(t, by):
    """Lead-time statistics by 'supplier_code', 'ship_mode' or 'supplier_region'."""
    po = delivered_pos(t["purchase_orders"])
    sup = t["suppliers"][["supplier_code", "supplier_name", "region"]].rename(columns={"region": "supplier_region"})
    po = po.merge(sup, on="supplier_code")
    g = po.groupby(by)
    out = pd.DataFrame({
        "n_pos": g.size(),
        "avg_promised_days": g["promised_lead_days"].mean(),
        "avg_actual_days": g["actual_lead_days"].mean(),
        "std_actual_days": g["actual_lead_days"].std(),
        "p90_actual_days": g["actual_lead_days"].quantile(0.9),
        "on_time_rate": g["on_time_flag"].mean(),
        "avg_delay_days": g["delay_days"].mean(),
        "po_value": g["po_value"].sum(),
        "freight_cost": g["freight_cost"].sum(),
    })
    out["lead_time_cv"] = out["std_actual_days"] / out["avg_actual_days"]
    out["freight_pct_of_value"] = out["freight_cost"] / out["po_value"]
    out["avg_delay_when_late"] = po[po["delay_days"] > 0].groupby(by)["delay_days"].mean()
    out = out.reset_index()
    if by == "supplier_code":
        out = out.merge(sup.drop_duplicates("supplier_code"), on="supplier_code")
    return out.sort_values("on_time_rate").reset_index(drop=True)


# ---------------------------------------------------------------- policy check
def build_policy_check(t, recent_days=91):
    """
    Compare the CURRENT reorder policy (set in the first 13 weeks) with what the standard formulas
    recommend using the MOST RECENT 13 weeks of demand and the supplier's ACTUAL lead times.
    One row per SKU-warehouse.
    """
    d, pol, prod = t["demand_daily"], t["inventory_policy"], t["products"].set_index("sku")
    last = d["date"].max()
    recent = d[d["date"] > last - pd.Timedelta(days=recent_days)]
    stats = recent.groupby(["sku", "warehouse_code"])["units_demanded"].agg(mean_daily="mean", sigma_daily="std").reset_index()
    stock_rate = recent.groupby(["sku", "warehouse_code"])["stockout_flag"].mean().rename("recent_stockout_rate").reset_index()
    price = prod["unit_price"]
    lost = recent.assign(lost=(recent["units_demanded"] - recent["units_fulfilled"]) * recent["sku"].map(price))
    lost = lost.groupby(["sku", "warehouse_code"])["lost"].sum().rename("recent_lost_revenue").reset_index()
    stock_rate = stock_rate.merge(lost, on=["sku", "warehouse_code"])

    po = delivered_pos(t["purchase_orders"])
    # lead-time mean per supplier; variability = WITHIN-ship-mode spread (planners know the mode when they order,
    # so the difference between ocean and air is a decision, not randomness)
    lt = po.groupby("supplier_code")["actual_lead_days"].mean().rename("lead_mean").reset_index()
    within = po.groupby(["supplier_code", "ship_mode"])["actual_lead_days"].agg(var="var", n="size").dropna().reset_index()
    within["w_var"] = within["var"] * within["n"]
    pooled = within.groupby("supplier_code").apply(lambda g: np.sqrt(g["w_var"].sum() / g["n"].sum()), include_groups=False)
    lt = lt.merge(pooled.rename("lead_std").reset_index(), on="supplier_code")

    df = pol.merge(stats, on=["sku", "warehouse_code"]).merge(stock_rate, on=["sku", "warehouse_code"])
    df = df.merge(prod[["supplier_code", "category", "unit_cost"]].reset_index(), on="sku").merge(lt, on="supplier_code")
    df["rec_safety_stock"] = [
        safety_stock(cfg.SERVICE_Z, s, m, cfg.REVIEW_PERIOD_DAYS, ls, md)
        for s, m, ls, md in zip(df["sigma_daily"], df["lead_mean"], df["lead_std"], df["mean_daily"])]
    df["rec_reorder_point"] = [reorder_point(md, m, ss) for md, m, ss in zip(df["mean_daily"], df["lead_mean"], df["rec_safety_stock"])]
    df["rop_gap_units"] = df["rec_reorder_point"] - df["reorder_point_units"]       # >0 : current ROP too low
    df["rop_gap_pct"] = df["rop_gap_units"] / df["rec_reorder_point"]
    df["under_protected"] = (df["rop_gap_units"] > 0).astype(int)
    # extra STOCK we would hold = extra safety stock only (a higher lead-time-demand part of the ROP is not held stock)
    df["ss_gap_units"] = df["rec_safety_stock"] - df["safety_stock_units"]
    df["extra_inventory_value_needed"] = df["ss_gap_units"].clip(lower=0) * df["unit_cost"]
    return df


# ---------------------------------------------------------------- weekly demand (used by EDA + forecasting)
def weekly_demand(t):
    """SKU-level weekly table: demand, sales, promo days. Week starts on Monday (data starts on a Monday)."""
    d = t["demand_daily"].copy()
    start = d["date"].min()
    d["week_idx"] = ((d["date"] - start).dt.days // 7).astype(int)
    g = d.groupby(["sku", "week_idx"])
    w = g.agg(units_demanded=("units_demanded", "sum"), units_fulfilled=("units_fulfilled", "sum"),
              promo_days=("promo_flag", "max")).reset_index()
    # promo_flag is per-SKU-day (same in every warehouse) -> count distinct promo days
    promo_days = (d[d["promo_flag"] == 1].drop_duplicates(["sku", "date"]).groupby(["sku", "week_idx"]).size().rename("promo_days_n"))
    w = w.drop(columns="promo_days").merge(promo_days.reset_index(), on=["sku", "week_idx"], how="left")
    w["promo_days_n"] = w["promo_days_n"].fillna(0).astype(int)
    w["promo_flag"] = (w["promo_days_n"] > 0).astype(int)
    w["week_start"] = start + pd.to_timedelta(w["week_idx"] * 7, unit="D")
    w["month"] = w["week_start"].dt.month
    return w.sort_values(["sku", "week_idx"]).reset_index(drop=True)

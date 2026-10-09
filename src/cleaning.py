"""
cleaning.py - data cleaning rules, one function per table.

Design (easy to explain in an interview):
  * every rule is a few lines of pandas
  * every rule writes a row to a CleaningLog: table, issue, rule, rows affected, action
  * the log is saved as outputs/tables/cleaning_log.csv  ->  nothing is changed silently
  * order matters: (1) fix keys/types  (2) drop duplicates  (3) fix impossible values  (4) fill missing values
"""
import numpy as np
import pandas as pd

OUTLIER_MULTIPLE = 20      # daily demand above 20x the SKU-warehouse median is treated as a typo


class CleaningLog:
    """Collects one record per cleaning rule so the final report shows exactly what happened."""

    def __init__(self):
        self.rows = []

    def add(self, table, issue, rule, n_rows, action):
        self.rows.append(dict(table=table, issue=issue, rule=rule, rows_affected=int(n_rows), action=action))

    def to_frame(self):
        return pd.DataFrame(self.rows, columns=["table", "issue", "rule", "rows_affected", "action"])


# ----------------------------------------------------------------------------- helpers
def standardize_code(series):
    """' sku-00012 ' -> 'SKU-00012'. Returns the cleaned series and how many values changed."""
    cleaned = series.astype(str).str.strip().str.upper()
    return cleaned, int((cleaned != series.astype(str)).sum())


def parse_mixed_dates(series):
    """
    Dates arrive as '2024-03-05' (ISO) or '05-Mar-2024'. Parse both explicitly
    (never let pandas guess - '05/03/2024' would be ambiguous).
    Returns (parsed datetimes, number of rows that were NOT in ISO format).
    """
    s = series.astype("string")
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    other = pd.to_datetime(s.where(iso.isna()), format="%d-%b-%Y", errors="coerce")
    parsed = iso.fillna(other)
    return parsed, int(iso.isna().sum() - parsed.isna().sum())


def title_case_clean(series):
    cleaned = series.astype(str).str.strip().str.title()
    return cleaned, int((cleaned != series.astype(str)).sum())


# ----------------------------------------------------------------------------- demand
def clean_demand(df, log):
    t = "demand_daily"
    df = df.copy()
    df["sku"], n = standardize_code(df["sku"])
    log.add(t, "SKU code has lowercase/extra spaces", "strip + upper-case", n, "standardised")
    df["warehouse_code"], n = standardize_code(df["warehouse_code"])
    log.add(t, "Warehouse code has lowercase/extra spaces", "strip + upper-case", n, "standardised")
    df["date"], n = parse_mixed_dates(df["date"])
    log.add(t, "Dates in a second format (dd-Mon-yyyy)", "explicit format parsing", n, "converted to ISO dates")
    n_bad = int(df["date"].isna().sum())
    df = df.dropna(subset=["date"])
    log.add(t, "Unparseable dates", "drop row", n_bad, "dropped")

    before = len(df)
    df = df.drop_duplicates(subset=["sku", "warehouse_code", "date"], keep="first")
    log.add(t, "Duplicate sku-warehouse-day rows", "drop_duplicates on the business key", before - len(df), "dropped")

    neg = df["units_demanded"] < 0
    df.loc[neg, "units_demanded"] = df.loc[neg, "units_demanded"].abs()
    log.add(t, "Negative demand (sign error)", "take absolute value", neg.sum(), "corrected")

    miss = df["units_demanded"].isna()
    df.loc[miss, "units_demanded"] = df.loc[miss, "units_fulfilled"]
    log.add(t, "Missing units_demanded", "fill with units_fulfilled (lower bound of true demand)", miss.sum(),
            "imputed")

    # typo detection: compare each day with the median of the SAME sku + warehouse
    median = df.groupby(["sku", "warehouse_code"])["units_demanded"].transform("median")
    outlier = (df["units_demanded"] > OUTLIER_MULTIPLE * median.clip(lower=1)) & (df["units_demanded"] > 50)
    df.loc[outlier, "units_demanded"] = median[outlier].round()
    log.add(t, f"Demand > {OUTLIER_MULTIPLE}x the sku-warehouse median (extra-zero typo)",
            "replace with sku-warehouse median", outlier.sum(), "corrected")

    imp = df["units_fulfilled"] > df["units_demanded"]
    df.loc[imp, "units_fulfilled"] = df.loc[imp, "units_demanded"]
    log.add(t, "units_fulfilled > units_demanded (impossible)", "cap fulfilled at demanded", imp.sum(), "corrected")

    df["units_demanded"] = df["units_demanded"].astype(int)
    df["units_fulfilled"] = df["units_fulfilled"].astype(int)
    df["promo_flag"] = df["promo_flag"].astype(int)
    df["stockout_flag"] = (df["units_fulfilled"] < df["units_demanded"]).astype(int)   # demand not fully met
    return df.sort_values(["sku", "warehouse_code", "date"]).reset_index(drop=True)


# ----------------------------------------------------------------------------- inventory
def clean_inventory(df, log):
    t = "inventory_daily"
    df = df.copy()
    df["sku"], n = standardize_code(df["sku"])
    df["warehouse_code"], n2 = standardize_code(df["warehouse_code"])
    log.add(t, "SKU / warehouse code formatting", "strip + upper-case", n + n2, "standardised")
    df["date"], n = parse_mixed_dates(df["date"])
    log.add(t, "Dates in a second format", "explicit format parsing", n, "converted")

    before = len(df)
    df = df.drop_duplicates(subset=["sku", "warehouse_code", "date"], keep="first")
    log.add(t, "Duplicate sku-warehouse-day rows", "drop_duplicates on the business key", before - len(df), "dropped")

    df = df.sort_values(["sku", "warehouse_code", "date"])
    neg = df["on_hand_units"] < 0
    df.loc[neg, "on_hand_units"] = 0
    log.add(t, "Negative stock on hand", "set to 0 (physical stock cannot be negative)", neg.sum(), "corrected")

    miss = df["on_hand_units"].isna()
    df["on_hand_units"] = df.groupby(["sku", "warehouse_code"])["on_hand_units"].ffill()
    df["on_hand_units"] = df["on_hand_units"].fillna(0)
    log.add(t, "Missing on_hand_units", "carry forward last known stock level (stock is a level, not a flow)",
            miss.sum(), "imputed")
    df["on_hand_units"] = df["on_hand_units"].astype(int)
    df["in_transit_units"] = df["in_transit_units"].astype(int)
    return df.reset_index(drop=True)


# ----------------------------------------------------------------------------- purchase orders
def clean_purchase_orders(df, log):
    t = "purchase_orders"
    df = df.copy()
    before = len(df)
    df = df.drop_duplicates(subset=["po_number"], keep="first")
    log.add(t, "Duplicate PO numbers", "drop_duplicates on po_number", before - len(df), "dropped")

    for c in ("order_date", "promised_delivery_date", "actual_delivery_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    mode = df["ship_mode"].astype(str).str.strip().str.lower()
    log.add(t, "ship_mode in mixed case", "lower-case", (mode != df["ship_mode"]).sum(), "standardised ('AIR' -> 'air')")
    df["ship_mode"] = mode

    neg = df["quantity"] < 0
    df.loc[neg, "quantity"] = df.loc[neg, "quantity"].abs()
    log.add(t, "Negative order quantity", "take absolute value", neg.sum(), "corrected")
    df["quantity"] = df["quantity"].astype(int)

    # delivered BEFORE it was ordered is impossible -> keep the PO, but null the delivery date
    bad = df["actual_delivery_date"] < df["order_date"]
    df["delivery_date_invalid"] = bad.astype(int)
    df.loc[bad, "actual_delivery_date"] = pd.NaT
    log.add(t, "Delivery date earlier than order date", "set date to NULL + flag delivery_date_invalid=1 "
            "(excluded from lead-time KPIs)", bad.sum(), "flagged")

    # missing freight cost -> typical freight rate of that ship mode x PO value
    value = df["quantity"] * df["unit_cost"]
    rate = (df["freight_cost"] / value).groupby(df["ship_mode"]).transform("median")
    miss = df["freight_cost"].isna()
    df.loc[miss, "freight_cost"] = (rate * value)[miss].round(2)
    log.add(t, "Missing freight_cost", "median freight-rate of the same ship_mode x PO value", miss.sum(), "imputed")

    # derived lead-time columns used by the lead-time analysis
    df["po_value"] = (df["quantity"] * df["unit_cost"]).round(2)
    df["promised_lead_days"] = (df["promised_delivery_date"] - df["order_date"]).dt.days
    df["actual_lead_days"] = (df["actual_delivery_date"] - df["order_date"]).dt.days
    df["delay_days"] = df["actual_lead_days"] - df["promised_lead_days"]
    df["on_time_flag"] = np.where(df["actual_lead_days"].isna(), np.nan, (df["delay_days"] <= 0).astype(float))
    return df.sort_values("po_number").reset_index(drop=True)


# ----------------------------------------------------------------------------- products & suppliers
def clean_products(df, purchase_orders, log):
    t = "products"
    df = df.copy()
    before = len(df)
    df = df.drop_duplicates(subset=["sku"], keep="first")
    log.add(t, "Duplicate SKU rows in master data", "drop_duplicates on sku", before - len(df), "dropped")
    df["sku"], _ = standardize_code(df["sku"])
    df["category"], n = title_case_clean(df["category"])
    log.add(t, "Category text inconsistent ('ELECTRONICS ', 'electronics')", "strip + title-case", n, "standardised")

    miss = df["unit_cost"].isna()
    po_cost = purchase_orders.groupby("sku")["unit_cost"].mean()      # PO price already includes supplier cost index
    fill_po = df.loc[miss, "sku"].map(po_cost)
    df.loc[miss, "unit_cost"] = fill_po
    still = df["unit_cost"].isna()
    df.loc[still, "unit_cost"] = df.groupby("category")["unit_cost"].transform("median")[still]
    log.add(t, "Missing unit_cost", "average PO unit cost of that SKU (fallback: category median)", miss.sum(), "imputed")
    df["unit_cost"] = df["unit_cost"].round(2)

    bad_margin = df["unit_price"] < df["unit_cost"]
    log.add(t, "unit_price below unit_cost (check only)", "report, no change", bad_margin.sum(), "reported")
    return df.sort_values("sku").reset_index(drop=True)


def clean_suppliers(df, purchase_orders, log):
    t = "suppliers"
    df = df.copy()
    df["region"], n = title_case_clean(df["region"])
    log.add(t, "Region text inconsistent ('EUROPE ')", "strip + title-case", n, "standardised")
    miss = df["quoted_lead_time_days"].isna()
    po_lead = purchase_orders.groupby("supplier_code")["promised_lead_days"].mean()
    df.loc[miss, "quoted_lead_time_days"] = df.loc[miss, "supplier_code"].map(po_lead).round()
    df["quoted_lead_time_days"] = df["quoted_lead_time_days"].fillna(df["quoted_lead_time_days"].median()).astype(int)
    log.add(t, "Missing quoted_lead_time_days", "average promised lead time on that supplier's POs", miss.sum(),
            "imputed")
    return df


# ----------------------------------------------------------------------------- integrity checks
def referential_checks(tables, log):
    """Orphan keys would silently drop rows in SQL joins, so we count them (they should be 0)."""
    skus = set(tables["products"]["sku"])
    sups = set(tables["suppliers"]["supplier_code"])
    whs = set(tables["warehouses"]["warehouse_code"])
    for name in ("demand_daily", "inventory_daily"):
        n = int((~tables[name]["sku"].isin(skus)).sum() + (~tables[name]["warehouse_code"].isin(whs)).sum())
        log.add(name, "Orphan sku / warehouse codes (integrity check)", "compare to master tables", n,
                "none found" if n == 0 else "REVIEW")
    n = int((~tables["products"]["supplier_code"].isin(sups)).sum())
    log.add("products", "Orphan supplier codes (integrity check)", "compare to suppliers", n,
            "none found" if n == 0 else "REVIEW")


def data_quality_summary(raw, clean):
    """Rows and total NULL cells before vs after cleaning, per table."""
    rows = []
    for name in clean:
        rows.append(dict(table=name, rows_raw=len(raw[name]), rows_clean=len(clean[name]),
                         null_cells_raw=int(raw[name].isna().sum().sum()),
                         null_cells_clean=int(clean[name].isna().sum().sum())))
    return pd.DataFrame(rows)


def clean_all(raw):
    """Run every cleaning function in the right order. Returns (clean_tables, log_frame)."""
    log = CleaningLog()
    po = clean_purchase_orders(raw["purchase_orders"], log)
    out = dict(
        warehouses=raw["warehouses"].copy(),
        purchase_orders=po,
        products=clean_products(raw["products"], po, log),
        suppliers=clean_suppliers(raw["suppliers"], po, log),
        demand_daily=clean_demand(raw["demand_daily"], log),
        inventory_daily=clean_inventory(raw["inventory_daily"], log),
        inventory_policy=raw["inventory_policy"].copy(),
    )
    out["inventory_policy"]["policy_set_date"] = pd.to_datetime(out["inventory_policy"]["policy_set_date"])
    referential_checks(out, log)
    return out, log.to_frame()

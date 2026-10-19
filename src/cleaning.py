"""
cleaning.py - validate and tidy the raw M5 files, and build the weekly panel.

Honest note: the real M5 data is much cleaner than the synthetic data this project used before. There are no
duplicates, no negative numbers and no missing values to "fix". The cleaning work here is STRUCTURAL:

  * check the data really is what the documentation says (IDs, hierarchy, calendar, prices)
  * a zero before an item's first price listing is NOT zero demand - the item was not on sale yet -> mask it
  * the last 2 days of the file do not make a full week -> drop them so every week has 7 days
  * flag (never silently delete) price jumps and demand spikes so a reader can see how many there are

Every rule is written to the cleaning log (rule, rows affected, action) - nothing is changed silently.
"""
import numpy as np
import pandas as pd

import config as cfg
import panel as pn


class CleaningLog:
    def __init__(self):
        self.rows = []

    def add(self, rule, table, affected, action, detail=""):
        self.rows.append(dict(rule=rule, table=table, rows_affected=int(affected), action=action, detail=detail))

    def to_frame(self):
        return pd.DataFrame(self.rows, columns=["rule", "table", "rows_affected", "action", "detail"])


def _day_columns(sales):
    cols = [c for c in sales.columns if c.startswith("d_")]
    return sorted(cols, key=lambda c: int(c[2:]))


def build_weeks(cal_n, n_full_weeks):
    """One row per full week from the calendar rows that belong to the sales window."""
    c = cal_n.iloc[:7 * n_full_weeks].copy()
    c["week_idx"] = np.arange(len(c)) // 7
    c["date"] = pd.to_datetime(c["date"])
    g = c.groupby("week_idx")
    weeks = pd.DataFrame({
        "week_idx": g.size().index,
        "wm_yr_wk": g["wm_yr_wk"].first().to_numpy(),
        "week_start": g["date"].min().to_numpy(),
        "month": (g["date"].min() + pd.Timedelta(days=3)).dt.month.to_numpy(),      # month of the middle of the week
        "year": (g["date"].min() + pd.Timedelta(days=3)).dt.year.to_numpy(),
        "snap_days_CA": g["snap_CA"].sum().to_numpy(), "snap_days_TX": g["snap_TX"].sum().to_numpy(),
        "snap_days_WI": g["snap_WI"].sum().to_numpy(),
        "event_days": g["event_name_1"].apply(lambda s: int(s.notna().sum())).to_numpy(),
    })
    return weeks


def clean_all(raw):
    """raw = dict(calendar, sales, prices) -> (panel, daily_store_dept DataFrame, dim_date DataFrame, log)."""
    log = CleaningLog()
    sales, cal, prices = raw["sales"], raw["calendar"], raw["prices"]
    dcols = _day_columns(sales)
    n_days = len(dcols)

    # ---- 1. structure checks (these should find nothing; the log proves it)
    dup_ids = int(sales["id"].duplicated().sum())
    log.add("unique series id", "sales", dup_ids, "none needed" if dup_ids == 0 else "dropped duplicates")
    sales = sales.drop_duplicates("id").reset_index(drop=True)

    bad_h = int((sales.groupby("item_id")[["dept_id", "cat_id"]].nunique() > 1).any(axis=1).sum()) \
        + int((sales.groupby("store_id")["state_id"].nunique() > 1).sum())
    log.add("hierarchy consistent (item -> dept -> category, store -> state)", "sales", bad_h, "none needed" if bad_h == 0 else "flagged")

    cal_ok = bool((cal["d"].iloc[:n_days].to_numpy() == np.array(dcols)).all())
    dates = pd.to_datetime(cal["date"])
    contiguous = bool((dates.diff().dropna() == pd.Timedelta(days=1)).all())
    log.add("calendar days match sales columns and are contiguous", "calendar", 0 if (cal_ok and contiguous) else 1,
            "none needed" if (cal_ok and contiguous) else "ERROR", f"{n_days} sales days, calendar has {len(cal)} days (extra days = future, no sales)")
    if not (cal_ok and contiguous):
        raise ValueError("calendar does not line up with the sales columns")

    # ---- 2. value checks on the daily matrix
    units_d = sales[dcols].to_numpy()
    n_missing = int(pd.isna(units_d).sum())
    n_neg = int((units_d < 0).sum())
    n_frac = int((np.nan_to_num(units_d) % 1 != 0).sum())
    log.add("missing daily sales", "sales", n_missing, "none needed" if n_missing == 0 else "treated as 0")
    log.add("negative daily sales", "sales", n_neg, "none needed" if n_neg == 0 else "set to 0")
    log.add("non-integer unit counts", "sales", n_frac, "none needed" if n_frac == 0 else "rounded")
    units_d = np.nan_to_num(units_d).clip(min=0).round().astype(np.int16)

    # ---- 3. weekly window: drop the trailing partial week
    n_weeks = n_days // 7
    n_dropped_days = n_days - 7 * n_weeks
    units_dropped = int(units_d[:, 7 * n_weeks:].sum())
    log.add("trailing partial week", "sales", n_dropped_days * len(sales), "dropped last days so every week has 7 days",
            f"{n_dropped_days} days / {units_dropped:,} units dropped")
    units_d = units_d[:, :7 * n_weeks]
    weeks = build_weeks(cal.iloc[:n_days], n_weeks)
    S = len(sales)
    units_w = units_d.reshape(S, n_weeks, 7).sum(axis=2).astype(np.int32)

    # ---- 4. prices -> matrix [series, week]
    dup_p = int(prices.duplicated(["store_id", "item_id", "wm_yr_wk"]).sum())
    log.add("duplicate price rows", "sell_prices", dup_p, "none needed" if dup_p == 0 else "dropped")
    prices = prices.drop_duplicates(["store_id", "item_id", "wm_yr_wk"])
    bad_price = int((prices["sell_price"] <= 0).sum() + prices["sell_price"].isna().sum())
    log.add("non-positive or missing price", "sell_prices", bad_price, "none needed" if bad_price == 0 else "dropped")
    prices = prices[prices["sell_price"] > 0]

    week_of = pd.Series(weeks["week_idx"].to_numpy(), index=weeks["wm_yr_wk"].to_numpy())
    wk = prices["wm_yr_wk"].map(week_of)
    outside = int(wk.isna().sum())
    log.add("price rows outside the sales window", "sell_prices", outside, "dropped (weeks after the last full sales week)")
    prices = prices[wk.notna()]
    wk = wk.dropna().astype(int).to_numpy()

    items = pd.Index(sorted(sales["item_id"].unique()))
    stores = pd.Index(sorted(sales["store_id"].unique()))
    row_of = np.full((len(items), len(stores)), -1, dtype=np.int64)
    row_of[items.get_indexer(sales["item_id"]), stores.get_indexer(sales["store_id"])] = np.arange(S)
    rows = row_of[items.get_indexer(prices["item_id"]), stores.get_indexer(prices["store_id"])]
    orphan = int((rows < 0).sum())
    log.add("price rows for an item-store with no sales row", "sell_prices", orphan, "none needed" if orphan == 0 else "dropped")
    ok = rows >= 0
    price_w = np.full((S, n_weeks), np.nan, dtype=np.float32)
    price_w[rows[ok], wk[ok]] = prices["sell_price"].to_numpy(dtype=np.float32)[ok]

    # ---- 5. the key real-data rule: no price listing = not on sale, so zeros there are NOT demand
    not_on_sale = np.isnan(price_w)
    log.add("series-weeks with no price listing (item not on sale yet / delisted)", "sales x prices", not_on_sale.sum(),
            "masked as 'not on sale' - excluded from KPIs and forecasting instead of counting as zero demand",
            f"{not_on_sale.mean():.1%} of all series-weeks")
    units_no_price = int(((units_w > 0) & not_on_sale).sum())
    log.add("sales recorded in a week with no price", "sales x prices", units_no_price,
            "none needed" if units_no_price == 0 else "price filled from the nearest listed week")
    if units_no_price:
        filled = pd.DataFrame(price_w).T.ffill().bfill().T.to_numpy(dtype=np.float32)
        fix = (units_w > 0) & not_on_sale
        price_w[fix] = filled[fix]
        not_on_sale = np.isnan(price_w)
    units_w = np.where(not_on_sale, 0, units_w).astype(np.int32)

    last = price_w[:, -cfg.DELIST_WEEKS:]
    delisted = np.isnan(last).all(axis=1) & ~np.isnan(price_w).all(axis=1)
    log.add(f"delisted series (no price in the last {cfg.DELIST_WEEKS} weeks)", "prices", delisted.sum(),
            "kept; their off-sale weeks are masked, earlier history stays")
    never = int(np.isnan(price_w).all(axis=1).sum())
    log.add("series that were never on sale in the window", "prices", never, "none needed" if never == 0 else "kept as all-masked")

    # ---- 6. flags only (we never delete real observations)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = price_w[:, 1:] / price_w[:, :-1]
    jumps = int(((ratio > cfg.PRICE_JUMP) | (ratio < 1 / cfg.PRICE_JUMP)).sum())
    log.add(f"week-to-week price change by more than {cfg.PRICE_JUMP:.0f}x", "sell_prices", jumps, "flagged only (kept)")
    masked = np.where(np.isnan(price_w), np.nan, units_w.astype(float))
    med = np.nanmedian(np.where(masked > 0, masked, np.nan), axis=1)
    spikes = int((units_w > cfg.SPIKE_MULT * np.nan_to_num(med, nan=np.inf)[:, None]).sum())
    log.add(f"weekly units above {cfg.SPIKE_MULT}x the series' median selling week", "sales", spikes,
            "flagged only (kept: real demand peaks such as holidays are exactly what we want to forecast)")
    ev2 = int(cal["event_name_2"].notna().sum())
    log.add("days with two events at once", "calendar", ev2, "kept (event_name_1 is used; the second event is rare)")

    # ---- 7. daily aggregate store x dept (small, used for weekday / SNAP / event analysis and SQL)
    day_week = np.arange(7 * n_weeks) // 7
    day_dates = pd.to_datetime(cal["date"].iloc[:7 * n_weeks]).to_numpy()
    parts = []
    for (store, dept), idx in sales.groupby(["store_id", "dept_id"]).indices.items():
        u = units_d[idx].astype(np.float64)                                      # float64 + cent rounding: daily revenue must
        p = np.round(np.nan_to_num(price_w[idx][:, day_week].astype(np.float64)), 2)   # add up to the weekly revenue exactly
        parts.append(pd.DataFrame({"date": day_dates, "store_id": store, "dept_id": dept,
                                   "units": u.sum(axis=0).astype(np.int64), "revenue": (u * p).sum(axis=0).round(2)}))
    daily = pd.concat(parts, ignore_index=True).sort_values(["date", "store_id", "dept_id"]).reset_index(drop=True)

    dim_date = cal.iloc[:7 * n_weeks].copy()
    dim_date["date"] = pd.to_datetime(dim_date["date"]).dt.strftime("%Y-%m-%d")
    dim_date["week_idx"] = np.arange(len(dim_date)) // 7
    dim_date = dim_date.drop(columns=["d"])

    series = sales[["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]].rename(columns={"id": "series_id"})
    series["series_id"] = series["series_id"].str.replace("_validation", "", regex=False).str.replace("_evaluation", "", regex=False)
    return pn.Panel(series, weeks, units_w, price_w), daily, dim_date, log.to_frame()


def data_quality_summary(raw, panel, daily):
    """Raw vs analysis-ready, one row per table (all counts come from the data)."""
    sales = raw["sales"]
    dcols = _day_columns(sales)
    raw_units = int(sales[dcols].to_numpy().sum())
    on = panel.onsale
    return pd.DataFrame([
        dict(table="sales (item-store x day)", rows_raw=len(sales), cols_raw=len(dcols), rows_clean=panel.n_series,
             note=f"{raw_units:,} units in the file; {int(panel.units.sum()):,} in the {panel.n_weeks} full weeks used"),
        dict(table="sell_prices (item-store x week)", rows_raw=len(raw["prices"]), cols_raw=4, rows_clean=int(on.sum()),
             note="rows inside the analysis window = on-sale series-weeks"),
        dict(table="calendar", rows_raw=len(raw["calendar"]), cols_raw=raw["calendar"].shape[1], rows_clean=len(panel.weeks) * 7,
             note="days inside the analysis window"),
        dict(table="daily store x dept (derived)", rows_raw=0, cols_raw=0, rows_clean=len(daily), note="aggregate used for weekday / SNAP / events"),
    ])

"""
Shared fixtures: a TINY hand-made dataset in the exact M5 file format, so the tests run in seconds and do not need the
Kaggle download. It is only used to test code - no result in the README comes from it.

  4 items x 2 stores, 70 full weeks (+2 trailing days that do not make a week), 28 future calendar days.
  One item (HOBBIES_1_001) is launched in week 5: no price before that, sales are 0 there (like real M5 pre-launch zeros).
"""
import numpy as np
import pandas as pd
import pytest

import cleaning

N_WEEKS = 70
EXTRA_DAYS = 2            # trailing partial week in the sales file
FUTURE_DAYS = 28          # calendar rows beyond the sales window (M5 has these too)
LAUNCH_WEEK = 5
ITEMS = [("FOODS_1_001", "FOODS_1", "FOODS"), ("FOODS_1_002", "FOODS_1", "FOODS"),
         ("HOBBIES_1_001", "HOBBIES_1", "HOBBIES"), ("HOUSEHOLD_1_001", "HOUSEHOLD_1", "HOUSEHOLD")]
STORES = [("CA_1", "CA"), ("TX_1", "TX")]


def make_raw(seed=0):
    rng = np.random.default_rng(seed)
    n_sales_days = 7 * N_WEEKS + EXTRA_DAYS
    n_cal = n_sales_days + FUTURE_DAYS
    dates = pd.date_range("2011-01-29", periods=n_cal, freq="D")          # 2011-01-29 is a Saturday, like M5
    events = np.full(n_cal, None, dtype=object)
    events[[10, 40, 100]] = ["SuperBowl", "Easter", "Thanksgiving"]
    cal = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"), "wm_yr_wk": 11101 + np.arange(n_cal) // 7, "weekday": dates.day_name(),
        "wday": (np.arange(n_cal) % 7) + 1, "month": dates.month, "year": dates.year, "d": [f"d_{i + 1}" for i in range(n_cal)],
        "event_name_1": events, "event_type_1": np.where(pd.isna(events), None, "National"), "event_name_2": None, "event_type_2": None,
        "snap_CA": (dates.day <= 10).astype(int), "snap_TX": (dates.day % 2 == 0).astype(int), "snap_WI": (dates.day >= 20).astype(int)})
    rows, price_rows = [], []
    for item, dept, cat in ITEMS:
        for store, state in STORES:
            base = rng.uniform(2, 20)
            units = rng.poisson(base, size=n_sales_days)
            first_week = LAUNCH_WEEK if item == "HOBBIES_1_001" else 0
            units[: 7 * first_week] = 0                                        # not on sale yet -> zero sales
            rows.append({"id": f"{item}_{store}_validation", "item_id": item, "dept_id": dept, "cat_id": cat, "store_id": store,
                         "state_id": state, **{f"d_{i + 1}": int(u) for i, u in enumerate(units)}})
            for w in range(first_week, N_WEEKS + 6):                           # prices also for a few weeks after the window
                price = round(2.0 + 0.5 * (sum(map(ord, item)) % 5) + (0.5 if w % 17 == 3 else 0.0), 2)
                price_rows.append({"store_id": store, "item_id": item, "wm_yr_wk": 11101 + w, "sell_price": price})
    return {"calendar": cal, "sales": pd.DataFrame(rows), "prices": pd.DataFrame(price_rows)}


@pytest.fixture(scope="session")
def mini_raw():
    return make_raw()


@pytest.fixture(scope="session")
def mini_clean(mini_raw):
    panel, daily, dim_date, log = cleaning.clean_all(mini_raw)
    return panel, daily, dim_date, log

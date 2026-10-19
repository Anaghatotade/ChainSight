"""
panel.py - load the raw M5 files and hold the cleaned weekly "panel" in memory.

The M5 sales file is WIDE (one row per item-store, one column per day: d_1 ... d_1913). The panel keeps it as
NumPy matrices because 30,490 series x 273 weeks is only 8.3 million numbers - tiny for NumPy, slow for row-by-row Python.

  series   one row per item x store  (item_id, dept_id, cat_id, store_id, state_id)
  weeks    one row per full week     (week_idx, wm_yr_wk, week_start, month, year, SNAP days, event days)
  units    matrix [n_series, n_weeks]  units sold in the week
  price    matrix [n_series, n_weeks]  sell price that week; NaN = the item was NOT on sale in that store that week
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as cfg


def find_raw(key, raw_dir=None):
    """Return the path of a raw file (accepts '<name>.csv' or '<name>.csv.gz')."""
    raw_dir = raw_dir or cfg.DATA_RAW
    base = raw_dir / cfg.RAW_FILES[key]
    for p in (base, base.with_name(base.name + ".gz")):
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Missing {base.name} (or .gz) in {raw_dir}. Download the M5 Forecasting - Accuracy files from Kaggle "
        f"(calendar.csv, sales_train_validation.csv, sell_prices.csv) - see README_SETUP.md.")


def load_raw(raw_dir=None):
    """Read the three raw files exactly as downloaded -> dict of DataFrames."""
    return {key: pd.read_csv(find_raw(key, raw_dir)) for key in cfg.RAW_FILES}


@dataclass
class Panel:
    series: pd.DataFrame
    weeks: pd.DataFrame
    units: np.ndarray       # int32  [S, W]
    price: np.ndarray       # float32 [S, W], NaN = not on sale

    @property
    def onsale(self):
        return ~np.isnan(self.price)

    @property
    def n_series(self):
        return self.units.shape[0]

    @property
    def n_weeks(self):
        return self.units.shape[1]

    def revenue(self):
        """Weekly revenue per series (units x price, rounded to cents like the SQL table; 0 when not on sale)."""
        price = np.round(np.nan_to_num(self.price.astype(np.float64)), 2)
        return np.round(self.units * price, 2)


def save_panel(panel, directory=None):
    d = directory or cfg.DATA_PROCESSED
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "panel.npz", units=panel.units, price=panel.price)
    panel.series.to_csv(d / "series.csv", index=False)
    panel.weeks.to_csv(d / "weeks.csv", index=False)


def load_panel(directory=None):
    d = directory or cfg.DATA_PROCESSED
    if not (d / "panel.npz").exists():
        raise FileNotFoundError("data/processed/panel.npz not found - run steps 01 and 02 first.")
    z = np.load(d / "panel.npz")
    return Panel(pd.read_csv(d / "series.csv"), pd.read_csv(d / "weeks.csv", parse_dates=["week_start"]), z["units"], z["price"])

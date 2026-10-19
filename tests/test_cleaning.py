import numpy as np
import pandas as pd
import pytest

import cleaning
import config as cfg
import panel as pn
from conftest import EXTRA_DAYS, LAUNCH_WEEK, N_WEEKS, make_raw


def test_panel_shape_and_trailing_partial_week_dropped(mini_clean):
    panel, _, _, log = mini_clean
    assert panel.units.shape == (8, N_WEEKS)                      # 4 items x 2 stores, 70 FULL weeks
    assert len(panel.weeks) == N_WEEKS
    row = log.set_index("rule").loc["trailing partial week"]
    assert row["rows_affected"] == EXTRA_DAYS * 8                 # 2 days x 8 series dropped, and logged


def test_weekly_units_equal_the_sum_of_the_seven_days(mini_raw, mini_clean):
    panel, _, _, _ = mini_clean
    sales = mini_raw["sales"]
    r = sales[sales["id"] == "FOODS_1_001_CA_1_validation"].iloc[0]
    daily = np.array([r[f"d_{i}"] for i in range(1, 7 * N_WEEKS + 1)])
    series = panel.series.reset_index(drop=True)
    idx = series.index[series["series_id"] == "FOODS_1_001_CA_1"][0]
    assert panel.units[idx].tolist() == daily.reshape(N_WEEKS, 7).sum(axis=1).tolist()


def test_zeros_before_launch_are_masked_not_counted_as_demand(mini_clean):
    panel, _, _, log = mini_clean
    series = panel.series.reset_index(drop=True)
    idx = series.index[series["item_id"] == "HOBBIES_1_001"]
    assert np.isnan(panel.price[idx, :LAUNCH_WEEK]).all()          # no price = not on sale
    assert (panel.units[idx, :LAUNCH_WEEK] == 0).all()
    assert panel.onsale[idx, LAUNCH_WEEK:].all()
    assert log.set_index("rule").loc["series-weeks with no price listing (item not on sale yet / delisted)", "rows_affected"] == 2 * LAUNCH_WEEK


def test_prices_outside_the_sales_window_are_dropped_and_logged(mini_clean):
    _, _, _, log = mini_clean
    assert log.set_index("rule").loc["price rows outside the sales window", "rows_affected"] > 0


def test_total_units_are_conserved_except_dropped_days(mini_raw, mini_clean):
    panel, _, _, _ = mini_clean
    dcols = [f"d_{i}" for i in range(1, 7 * N_WEEKS + 1)]
    assert panel.units.sum() == mini_raw["sales"][dcols].to_numpy().sum()


def test_daily_revenue_adds_up_to_weekly_revenue_exactly(mini_clean):
    """Regression test for the float32 rounding bug: the two aggregates must tie to the cent."""
    panel, daily, _, _ = mini_clean
    assert daily["revenue"].sum() == pytest.approx(panel.revenue().sum(), abs=1e-6)
    assert daily["units"].sum() == panel.units.sum()


def test_sales_in_a_week_without_price_get_a_price_and_are_logged():
    raw = make_raw()
    mask = (raw["prices"]["item_id"] == "FOODS_1_001") & (raw["prices"]["store_id"] == "CA_1") & (raw["prices"]["wm_yr_wk"] == 11101 + 10)
    raw["prices"] = raw["prices"][~mask]                           # remove one price listing although the item sold that week
    panel, _, _, log = cleaning.clean_all(raw)
    assert log.set_index("rule").loc["sales recorded in a week with no price", "rows_affected"] >= 1
    series = panel.series.reset_index(drop=True)
    idx = series.index[series["series_id"] == "FOODS_1_001_CA_1"][0]
    assert not np.isnan(panel.price[idx, 10])                      # filled from the nearest listed week


def test_negative_and_duplicate_inputs_are_handled_and_logged():
    raw = make_raw()
    raw["sales"].loc[0, "d_5"] = -3                                # impossible negative sale
    raw["sales"] = pd.concat([raw["sales"], raw["sales"].iloc[[1]]], ignore_index=True)     # duplicate series id
    panel, _, _, log = cleaning.clean_all(raw)
    L = log.set_index("rule")["rows_affected"]
    assert L["negative daily sales"] == 1 and L["unique series id"] == 1
    assert panel.n_series == 8 and (panel.units >= 0).all()


def test_calendar_that_does_not_match_sales_is_rejected():
    raw = make_raw()
    raw["calendar"].loc[3, "d"] = "d_999"
    with pytest.raises(ValueError):
        cleaning.clean_all(raw)


def test_price_jumps_and_spikes_are_flagged_not_deleted():
    raw = make_raw()
    before = raw["sales"][[f"d_{i}" for i in range(1, 7 * N_WEEKS + 1)]].to_numpy().sum()
    raw["sales"].loc[2, [f"d_{i}" for i in range(100, 107)]] = 5000        # a huge demand spike in one week
    panel, _, _, log = cleaning.clean_all(raw)
    rule = [r for r in log["rule"] if "above" in r and "median" in r][0]
    assert log.set_index("rule").loc[rule, "rows_affected"] >= 1
    assert panel.units.sum() > before                              # nothing was removed


def test_cleaning_log_has_the_expected_columns(mini_clean):
    _, _, _, log = mini_clean
    assert list(log.columns) == ["rule", "table", "rows_affected", "action", "detail"]
    assert len(log) >= 15


def test_find_raw_accepts_csv_and_gz(tmp_path):
    (tmp_path / "calendar.csv").write_text("a\n1\n")
    (tmp_path / "sales_train_validation.csv.gz").write_bytes(b"x")
    assert pn.find_raw("calendar", tmp_path).name == "calendar.csv"
    assert pn.find_raw("sales", tmp_path).name == "sales_train_validation.csv.gz"
    with pytest.raises(FileNotFoundError):
        pn.find_raw("prices", tmp_path)


def test_data_quality_summary_has_one_row_per_table(mini_raw, mini_clean):
    panel, daily, _, _ = mini_clean
    summary = cleaning.data_quality_summary(mini_raw, panel, daily)
    assert len(summary) == 4 and summary["rows_clean"].gt(0).all()

import numpy as np
import pandas as pd

import cleaning
import datagen


def _demand(rows):
    return pd.DataFrame(rows, columns=["sku", "warehouse_code", "date", "units_demanded", "units_fulfilled", "promo_flag"])


def test_standardize_code_strips_and_uppercases():
    out, n = cleaning.standardize_code(pd.Series([" sku-001 ", "SKU-002", "sku-003"]))
    assert list(out) == ["SKU-001", "SKU-002", "SKU-003"]
    assert n == 2


def test_parse_mixed_dates_handles_both_formats():
    parsed, n_other = cleaning.parse_mixed_dates(pd.Series(["2024-03-05", "05-Mar-2024", "garbage"]))
    assert parsed.iloc[0] == parsed.iloc[1] == pd.Timestamp("2024-03-05")
    assert pd.isna(parsed.iloc[2])
    assert n_other == 1                       # exactly one row was in the second format


def test_clean_demand_rules_on_handmade_rows():
    log = cleaning.CleaningLog()
    rows = [
        ["SKU-1", "WH-A", "2024-01-01", 10, 10, 0],
        [" sku-1", "wh-a", "2024-01-01", 10, 10, 0],       # duplicate after standardising keys
        ["SKU-1", "WH-A", "2024-01-02", -8, 8, 0],         # sign error -> 8
        ["SKU-1", "WH-A", "2024-01-03", np.nan, 5, 0],     # missing -> fulfilled (5)
        ["SKU-1", "WH-A", "2024-01-04", 6, 9, 0],          # fulfilled > demanded -> cap at 6
        ["SKU-1", "WH-A", "03-Jan-2024", 4, 2, 1],         # same key as 2024-01-03 -> duplicate
    ]
    out = cleaning.clean_demand(_demand(rows), log)
    assert len(out) == 4                                    # 2 duplicates removed
    assert out["sku"].unique().tolist() == ["SKU-1"]
    by_day = out.set_index(out["date"].dt.strftime("%Y-%m-%d"))
    assert by_day.loc["2024-01-02", "units_demanded"] == 8
    assert by_day.loc["2024-01-03", "units_demanded"] == 5
    assert by_day.loc["2024-01-04", "units_fulfilled"] == 6
    assert (out["units_fulfilled"] <= out["units_demanded"]).all()
    assert out["stockout_flag"].tolist() == [0, 0, 0, 0]


def test_stockout_flag_marks_unmet_demand():
    log = cleaning.CleaningLog()
    rows = [["SKU-1", "WH-A", "2024-01-01", 10, 7, 0], ["SKU-1", "WH-A", "2024-01-02", 10, 10, 0]]
    out = cleaning.clean_demand(_demand(rows), log)
    assert out["stockout_flag"].tolist() == [1, 0]


def test_typo_outlier_is_replaced_by_sku_median():
    log = cleaning.CleaningLog()
    rows = [["SKU-1", "WH-A", f"2024-01-{d:02d}", 40, 40, 0] for d in range(1, 21)]
    rows.append(["SKU-1", "WH-A", "2024-01-21", 4000, 40, 0])      # extra zeros typo
    out = cleaning.clean_demand(_demand(rows), log)
    assert out["units_demanded"].max() == 40


def test_cleaning_log_records_every_rule():
    log = cleaning.CleaningLog()
    cleaning.clean_demand(_demand([["SKU-1", "WH-A", "2024-01-01", 5, 5, 0]]), log)
    frame = log.to_frame()
    assert list(frame.columns) == ["table", "issue", "rule", "rows_affected", "action"]
    assert len(frame) >= 7


def test_full_cleaning_recovers_the_clean_truth(small_clean, small_cleaned):
    """Messy data -> clean_all -> should match the hidden clean data almost perfectly."""
    cleaned, _ = small_cleaned
    truth = small_clean["demand_daily"]
    got = cleaned["demand_daily"]
    key = ["sku", "warehouse_code", "date"]
    assert not got.duplicated(key).any()
    assert len(got) == len(truth)                           # no row lost, no row invented
    m = got.merge(truth, on=key, suffixes=("", "_true"))
    assert len(m) == len(truth)
    assert abs(m["units_demanded"].sum() / m["units_demanded_true"].sum() - 1) < 0.01
    assert (m["units_demanded"] == m["units_demanded_true"]).mean() > 0.99


def test_cleaned_tables_have_valid_values(small_cleaned):
    c, _ = small_cleaned
    assert (c["demand_daily"]["units_demanded"] >= 0).all()
    assert (c["inventory_daily"]["on_hand_units"] >= 0).all()
    assert c["products"]["unit_cost"].notna().all()
    assert c["products"]["sku"].is_unique
    assert c["purchase_orders"]["po_number"].is_unique
    assert (c["purchase_orders"]["quantity"] > 0).all()
    valid = c["purchase_orders"]["actual_delivery_date"].dropna()
    ordered = c["purchase_orders"].loc[valid.index, "order_date"]
    assert (valid >= ordered).all()
    assert set(c["products"]["category"]) <= set(datagen.CATEGORIES)


def test_referential_integrity_has_no_orphans(small_cleaned):
    _, log = small_cleaned
    checks = log[log["issue"].str.contains("Orphan")]
    assert len(checks) == 3
    assert (checks["rows_affected"] == 0).all()

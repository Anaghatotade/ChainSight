import numpy as np
import pandas as pd
import pytest

import config as cfg
import db
import kpis


def test_fill_rate():
    assert kpis.fill_rate([100, 100], [90, 80]) == pytest.approx(0.85)
    assert np.isnan(kpis.fill_rate([0], [0]))


def test_stockout_rate():
    assert kpis.stockout_rate([1, 0, 0, 1]) == 0.5


def test_inventory_turnover_annualises():
    # COGS 1000 in 73 days = 5000 per year; avg inventory 250 -> 20 turns/year
    assert kpis.inventory_turnover(1000, 250, 73) == pytest.approx(20.0)
    assert np.isnan(kpis.inventory_turnover(1000, 0, 73))


def test_days_of_inventory():
    assert kpis.days_of_inventory(300, 20) == pytest.approx(15.0)


def test_inventory_turnover_and_days_are_consistent():
    # DOI ~= 365 / turnover when both use the same basis (units == value at constant cost)
    n_days, units_sold, avg_units = 100, 5000, 400
    turnover = kpis.inventory_turnover(units_sold * 2.0, avg_units * 2.0, n_days)
    doi = kpis.days_of_inventory(avg_units, units_sold / n_days)
    assert doi == pytest.approx(365 / turnover)


def test_demand_cv():
    assert kpis.demand_cv([10, 10, 10]) == 0
    assert kpis.demand_cv([5, 15]) == pytest.approx(np.std([5, 15], ddof=1) / 10)


def test_safety_stock_reduces_to_textbook_formula():
    z, sd, lt = 1.65, 20.0, 9.0
    assert kpis.safety_stock(z, sd, lt) == pytest.approx(z * sd * np.sqrt(lt))


def test_safety_stock_grows_with_review_period_and_lead_time_variability():
    base = kpis.safety_stock(1.65, 20, 9)
    assert kpis.safety_stock(1.65, 20, 9, review_days=7) > base
    assert kpis.safety_stock(1.65, 20, 9, lead_time_std_days=3, mean_daily=50) > base


def test_reorder_point():
    assert kpis.reorder_point(50, 10, 120) == 620


def test_abc_classify_known_example():
    rev = pd.Series({"a": 70, "b": 15, "c": 8, "d": 4, "e": 3})     # cum 70/85/93/97/100
    cls = kpis.abc_classify(rev)
    # share BEFORE each item: 0, .70, .85, .93, .97  -> A, A, B, B, C
    assert cls.to_dict() == {"a": "A", "b": "A", "c": "B", "d": "B", "e": "C"}


def test_abc_item_crossing_the_cutoff_stays_in_class_a():
    cls = kpis.abc_classify(pd.Series({"big": 90, "small": 10}))
    assert cls["big"] == "A"                  # one item holds 90% - it must not be demoted to B


def test_abc_ties_are_deterministic():
    rev = pd.Series({"x": 10, "y": 10, "z": 10})
    assert kpis.abc_classify(rev).to_dict() == kpis.abc_classify(rev.iloc[::-1]).to_dict()


def test_cv_band():
    assert [kpis.cv_band(v) for v in (0.1, 0.4, 0.9)] == ["Low", "Medium", "High"]


def test_sql_and_pandas_give_the_same_kpis(small_cleaned, tmp_path):
    """The same KPI computed in SQL (SQLite) and in pandas must match - a strong end-to-end check."""
    tables, _ = small_cleaned
    path = db.build_database(tables, db_path=tmp_path / "t.db")
    overall = kpis.build_overall_kpis(tables)
    sql = db.parse_named_queries((cfg.SQL_DIR / "01_kpi_queries.sql").read_text())["kpi_overall"]
    s = db.run_query(sql, path).iloc[0]
    assert s["fill_rate"] == pytest.approx(overall["fill_rate"])
    assert s["stockout_rate"] == pytest.approx(overall["stockout_rate"])
    assert s["inventory_turnover"] == pytest.approx(overall["inventory_turnover"])
    assert s["days_of_inventory"] == pytest.approx(overall["days_of_inventory"])
    assert s["revenue"] == pytest.approx(overall["revenue"])


def test_sql_abc_matches_pandas_abc(small_cleaned, tmp_path):
    tables, _ = small_cleaned
    path = db.build_database(tables, db_path=tmp_path / "t2.db")
    sku = kpis.build_sku_kpis(tables).set_index("sku")["abc_class"]
    sql = db.parse_named_queries((cfg.SQL_DIR / "03_abc_analysis.sql").read_text())["abc_classification"]
    got = db.run_query(sql, path).set_index("sku")["abc_class"]
    assert got.sort_index().to_dict() == sku.sort_index().to_dict()


def test_all_sql_queries_run(small_cleaned, tmp_path):
    tables, _ = small_cleaned
    path = db.build_database(tables, db_path=tmp_path / "t3.db")
    results = db.run_all_sql_files(db_path=path, out_dir=tmp_path / "sql_out")
    assert len(results) >= 20
    integrity = results["06_data_quality_checks__dq_integrity_checks"]
    assert (integrity["issues"] == 0).all()

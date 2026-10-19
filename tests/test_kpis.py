import numpy as np
import pandas as pd
import pytest

import analysis
import config as cfg
import db
import kpis
import panel as pn


# ------------------------------------------------------------------ pure formulas
def test_demand_cv_uses_population_std():
    assert kpis.demand_cv([10, 10, 10]) == 0
    assert kpis.demand_cv([5, 15]) == pytest.approx(5 / 10)          # population std = 5, mean = 10
    assert np.isnan(kpis.demand_cv([0, 0]))


def test_cv_band_boundaries():
    assert [kpis.cv_band(v) for v in (0.1, 0.49, 0.5, 0.99, 1.0, 3.0)] == ["stable", "stable", "variable", "variable", "erratic", "erratic"]
    assert pd.isna(kpis.cv_band(np.nan))


def test_demand_class_quadrants():
    assert kpis.demand_class(1.0, 0.2) == "smooth"
    assert kpis.demand_class(1.0, 0.9) == "erratic"
    assert kpis.demand_class(2.0, 0.2) == "intermittent"
    assert kpis.demand_class(2.0, 0.9) == "lumpy"


def test_safety_stock_matches_textbook_formula():
    z, sigma, lt, r = 1.65, 20.0, 2, 1
    assert kpis.safety_stock(sigma, lt, r, z) == pytest.approx(z * sigma * np.sqrt(lt + r))
    assert kpis.safety_stock(sigma) == pytest.approx(cfg.SERVICE_Z * sigma * np.sqrt(cfg.ASSUMED_LEAD_TIME_WEEKS + cfg.REVIEW_PERIOD_WEEKS))


def test_safety_stock_grows_with_variability_lead_time_and_z():
    assert kpis.safety_stock(30) > kpis.safety_stock(10)
    assert kpis.safety_stock(10, lead_time_weeks=4) > kpis.safety_stock(10, lead_time_weeks=1)
    assert kpis.safety_stock(10, z=2.0) > kpis.safety_stock(10, z=1.0)


def test_reorder_point_and_order_up_to():
    assert kpis.reorder_point(50, 10, lead_time_weeks=2) == 110          # 50 x 2 + 10
    assert kpis.order_up_to(50, 10, lead_time_weeks=2, review_weeks=1) == 160   # 50 x 3 + 10


def test_abc_classify_known_example():
    rev = pd.Series({"a": 70, "b": 15, "c": 8, "d": 4, "e": 3})        # cumulative 70/85/93/97/100
    # share BEFORE each item: 0, .70, .85, .93, .97  -> A, A, B, B, C
    assert kpis.abc_classify(rev).to_dict() == {"a": "A", "b": "A", "c": "B", "d": "B", "e": "C"}


def test_abc_item_crossing_the_cutoff_stays_in_class_a():
    assert kpis.abc_classify(pd.Series({"big": 90, "small": 10}))["big"] == "A"


def test_abc_ties_are_deterministic():
    rev = pd.Series({"x": 10, "y": 10, "z": 10})
    assert kpis.abc_classify(rev).to_dict() == kpis.abc_classify(rev.iloc[::-1]).to_dict()


# ------------------------------------------------------------------ builders on the mini panel
def test_item_state_aggregation_conserves_units(mini_clean):
    panel, _, _, _ = mini_clean
    g, units, price, cnt = kpis.aggregate_item_state(panel)
    assert len(g) == 4 * 2                                            # 4 items x 2 states (CA, TX)
    assert np.nansum(units) == panel.units.sum()
    assert np.isnan(units[(g["item_id"] == "HOBBIES_1_001").to_numpy()][:, :5]).all()     # not on sale before launch


def test_overall_and_cut_kpis_are_consistent(mini_clean):
    panel, _, _, _ = mini_clean
    overall = kpis.build_overall_kpis(panel)
    assert overall["total_units"] == panel.units.sum()
    assert overall["total_revenue"] == pytest.approx(panel.revenue().sum())
    cat = kpis.build_cut_kpis(panel, "cat_id")
    assert cat["revenue"].sum() == pytest.approx(overall["total_revenue"])
    assert cat["revenue_share"].sum() == pytest.approx(1.0)


def test_item_kpis_abc_covers_all_items(mini_clean):
    panel, _, _, _ = mini_clean
    item = kpis.build_item_kpis(panel)
    assert set(item["abc_class"]) <= {"A", "B", "C"} and len(item) == 4
    assert item["cum_revenue_share"].iloc[-1] == pytest.approx(1.0)


def test_item_state_kpis_policy_columns(mini_clean):
    panel, _, _, _ = mini_clean
    item_state = kpis.build_item_state_kpis(panel, kpis.build_item_kpis(panel))
    assert (item_state["safety_stock_units"].dropna() >= 0).all()
    ok = item_state.dropna(subset=["mean_units_last52"])
    assert (ok["reorder_point_units"] >= ok["safety_stock_units"]).all()
    assert (ok["order_up_to_units"] >= ok["reorder_point_units"]).all()


def _two_year_panel(monthly_factor):
    """A hand-built panel with 3 full calendar years (weekly, Monday starts), one series, demand = 100 x factor of its month."""
    starts = pd.date_range("2012-01-02", periods=156, freq="7D")                  # 2012, 2013, 2014 (all 12 months present)
    mid = starts + pd.Timedelta(days=3)
    weeks = pd.DataFrame({"week_idx": range(len(starts)), "week_start": starts, "month": mid.month, "year": mid.year})
    units = np.array([[100 * monthly_factor(m) for m in weeks["month"]]])
    series = pd.DataFrame({"series_id": ["x"], "item_id": ["i"], "dept_id": ["D"], "cat_id": ["C"], "store_id": ["s"], "state_id": ["CA"]})
    return pn.Panel(series, weeks, units.astype(np.int32), np.full(units.shape, 2.0, dtype=np.float32))


def test_seasonality_index_is_flat_for_flat_demand_and_finds_a_planted_peak():
    flat = analysis.seasonality_index(_two_year_panel(lambda m: 1.0), "cat_id")
    assert flat.loc["C"].to_numpy() == pytest.approx(1.0)
    peaked = analysis.seasonality_index(_two_year_panel(lambda m: 2.0 if m == 12 else 1.0), "cat_id").loc["C"]
    assert peaked.idxmax() == 12 and peaked[12] > 1.5 and peaked[1] < 1.0
    assert peaked.mean() == pytest.approx(1.0, abs=0.01)                          # an index always averages to 1


def test_complete_years_ignores_partial_years(mini_clean):
    panel, _, _, _ = mini_clean
    assert analysis.complete_years(panel.weeks) == []                             # 70 weeks never cover all 12 months of a year


# ------------------------------------------------------------------ SQL vs pandas (end-to-end cross-check)
@pytest.fixture(scope="module")
def mini_db(mini_clean, tmp_path_factory):
    panel, daily, dim_date, _ = mini_clean
    return db.build_database(panel, daily, dim_date, db_path=tmp_path_factory.mktemp("db") / "t.db")


def _query(name, file, path):
    sql = db.parse_named_queries((cfg.SQL_DIR / file).read_text())[name]
    return db.run_query(sql, path)


def test_sql_overall_kpis_match_pandas(mini_clean, mini_db):
    panel, _, _, _ = mini_clean
    overall = kpis.build_overall_kpis(panel)
    s = _query("overall_kpis", "01_kpi_queries.sql", mini_db).iloc[0]
    assert s["total_units"] == overall["total_units"]
    assert s["total_revenue"] == pytest.approx(overall["total_revenue"])


def test_sql_abc_matches_pandas_abc(mini_clean, mini_db):
    panel, _, _, _ = mini_clean
    pandas_abc = kpis.build_item_kpis(panel).set_index("item_id")["abc_class"]
    sql_abc = _query("abc_classification", "03_abc_analysis.sql", mini_db).set_index("item_id")["abc_class"]
    assert sql_abc.sort_index().to_dict() == pandas_abc.sort_index().to_dict()


def test_sql_cv_matches_pandas_cv(mini_clean, mini_db):
    """SQLite has no STDDEV: the SQL uses sqrt(E[x^2] - E[x]^2). It must equal numpy's population std / mean."""
    panel, _, _, _ = mini_clean
    item_state = kpis.build_item_state_kpis(panel, kpis.build_item_kpis(panel)).set_index(["item_id", "state_id"])
    sql = _query("item_state_demand_profile", "04_demand_variability.sql", mini_db).set_index(["item_id", "state_id"])
    joined = sql.join(item_state[["cv"]], how="inner", rsuffix="_pd")
    assert len(joined) == len(item_state)
    assert joined["cv"].to_numpy() == pytest.approx(joined["cv_pd"].to_numpy(), abs=1e-3)      # SQL rounds to 4 decimals


def test_all_sql_queries_run_and_integrity_checks_are_clean(mini_db, tmp_path):
    results = db.run_all_sql_files(db_path=mini_db, out_dir=tmp_path / "sql_out")
    assert len(results) >= 25
    integrity = results["06_data_quality_checks__dq_integrity_checks"]
    assert (integrity["issues"] == 0).all()

import pandas as pd
import numpy as np

from app.services import supplier_scoring, inventory_analysis, simulator
from app.ml import forecasting, risk_scoring


def test_supplier_scoring_grades_best_supplier_highest():
    df = pd.DataFrame([
        dict(supplier_id=1, name="Great Co", region="EU", category="Electronics",
             on_time_rate=0.98, avg_delay_days=0.5, avg_defect_rate=0.005, cost_index=0.9,
             lead_time_std_days=1.0),
        dict(supplier_id=2, name="Poor Co", region="EU", category="Electronics",
             on_time_rate=0.55, avg_delay_days=8, avg_defect_rate=0.09, cost_index=1.3,
             lead_time_std_days=9.0),
    ])
    scored = supplier_scoring.score_suppliers(df)
    great = scored[scored["supplier_id"] == 1].iloc[0]
    poor = scored[scored["supplier_id"] == 2].iloc[0]
    assert great["composite_score"] > poor["composite_score"]
    assert great["grade"] in ("A", "B")
    assert poor["grade"] in ("C", "D")


def test_inventory_status_classification():
    inv = pd.DataFrame([
        dict(product_id=1, warehouse_id=1, on_hand_units=0, in_transit_units=0,
             safety_stock_units=10, reorder_point_units=20, sku="A", name="A", category="x", abc_class="A"),
        dict(product_id=2, warehouse_id=1, on_hand_units=5000, in_transit_units=0,
             safety_stock_units=10, reorder_point_units=20, sku="B", name="B", category="x", abc_class="A"),
    ])
    demand = pd.DataFrame([
        dict(product_id=1, warehouse_id=1, avg_daily_demand=10),
        dict(product_id=2, warehouse_id=1, avg_daily_demand=10),
    ])
    result = inventory_analysis.compute_inventory_health(inv, demand)
    assert result[result.product_id == 1].iloc[0]["inventory_status"] == "critical"
    assert result[result.product_id == 2].iloc[0]["inventory_status"] == "overstock"


def test_simulator_higher_demand_increases_stockouts_or_cost():
    result_up = simulator.run_simulation(
        sku="TEST-1", avg_demand=20, std_demand=5, lead_time_mean=10, lead_time_std=2,
        safety_stock=20, reorder_point=220, unit_cost=10, warehouse_capacity=100000,
        demand_change_pct=80, lead_time_change_days=0, supplier_capacity_change_pct=0,
        safety_stock_change_units=0, cost_change_pct=0, simulation_days=60,
    )
    assert result_up["scenario"]["stockout_rate"] >= result_up["baseline"]["stockout_rate"] - 1e-6
    assert isinstance(result_up["narrative"], list) and len(result_up["narrative"]) > 0


def test_simulator_more_safety_stock_improves_service_level():
    result = simulator.run_simulation(
        sku="TEST-2", avg_demand=15, std_demand=8, lead_time_mean=14, lead_time_std=5,
        safety_stock=5, reorder_point=100, unit_cost=5, warehouse_capacity=100000,
        demand_change_pct=0, lead_time_change_days=0, supplier_capacity_change_pct=0,
        safety_stock_change_units=100, cost_change_pct=0, simulation_days=90,
    )
    assert result["scenario"]["service_level"] >= result["baseline"]["service_level"] - 0.02


def test_forecasting_fallback_for_short_history():
    dates = pd.date_range("2026-01-01", periods=20)
    df = pd.DataFrame({"ds": dates, "y": np.random.randint(1, 10, size=20)})
    forecast_df, metrics = forecasting.train_and_forecast(df, horizon_days=7)
    assert len(forecast_df) == 7
    assert metrics["model"] == "exp_smoothing_fallback"
    assert (forecast_df["yhat"] >= 0).all()


def test_forecasting_random_forest_path_with_sufficient_history():
    dates = pd.date_range("2025-01-01", periods=200)
    rng = np.random.default_rng(1)
    y = 20 + 5 * np.sin(np.arange(200) / 7) + rng.normal(0, 2, 200)
    df = pd.DataFrame({"ds": dates, "y": np.clip(y, 0, None)})
    forecast_df, metrics = forecasting.train_and_forecast(df, horizon_days=14, backtest_days=14)
    assert len(forecast_df) == 14
    assert metrics["model"] == "random_forest"
    assert metrics["mae"] is not None


def test_risk_model_trains_and_scores_with_explanations():
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({
        "days_of_supply": rng.uniform(1, 60, n),
        "demand_cv": rng.uniform(0.1, 1.2, n),
        "lead_time_days": rng.uniform(3, 40, n),
        "lead_time_cv": rng.uniform(0.05, 0.6, n),
        "supplier_on_time_rate": rng.uniform(0.5, 0.99, n),
        "safety_stock_ratio": rng.uniform(0.2, 2.0, n),
        "defect_rate": rng.uniform(0.0, 0.1, n),
        "recent_trend_pct": rng.uniform(-0.3, 0.3, n),
    })
    df["label"] = (df["days_of_supply"] < 10).astype(int)
    bundle = risk_scoring.train_risk_model(df)
    proba, factors = risk_scoring.score_instance(bundle, {"days_of_supply": 2, "demand_cv": 0.9,
                                                            "lead_time_days": 30, "lead_time_cv": 0.5,
                                                            "supplier_on_time_rate": 0.6,
                                                            "safety_stock_ratio": 0.3, "defect_rate": 0.08,
                                                            "recent_trend_pct": 0.2})
    assert 0 <= proba <= 1
    assert len(factors) == 5
    assert all("detail" in f for f in factors)

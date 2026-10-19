import numpy as np
import pandas as pd
import pytest

import baselines
import diagnosis
import error_analysis as ea
import features
import metrics
import panel as pn
import policy_sim
import splits

TRAIN, DEV, TEST = 54, 8, 8           # the mini panel has 70 weeks and rows need 52 weeks of history


# ------------------------------------------------------------------ metrics
def test_wape_hand_calculation():
    assert metrics.wape([100, 50, 50], [110, 50, 40]) == pytest.approx(0.10)     # errors 10 + 0 + 10 over 200


def test_bias_sign_convention():
    assert metrics.bias([100, 100], [110, 110]) == pytest.approx(0.10)           # over-forecast = positive
    assert metrics.bias([100, 100], [90, 90]) == pytest.approx(-0.10)


def test_rmse_and_mae():
    assert metrics.rmse([0, 0], [3, 4]) == pytest.approx(np.sqrt(12.5))
    assert metrics.mae([0, 0], [3, 4]) == pytest.approx(3.5)


def test_mape_skips_zero_actuals_and_nans_are_ignored():
    assert metrics.mape([0, 100], [5, 110]) == pytest.approx(0.10)
    assert metrics.wape([100, np.nan], [90, 50]) == pytest.approx(0.10)


def test_perfect_forecast_has_zero_error():
    s = metrics.score_all([5, 6, 7], [5, 6, 7])
    assert s["WAPE"] == 0 and s["RMSE"] == 0 and s["Bias"] == 0


# ------------------------------------------------------------------ split logic
def test_assign_split_sizes_and_order():
    s = pd.Series(splits.assign_split(np.arange(273)))
    assert (s == "train").sum() == 225 and (s == "dev").sum() == 24 and (s == "test").sum() == 24
    assert s.iloc[0] == "train" and s.iloc[-1] == "test"


def test_split_is_chronological_with_no_overlap():
    df = pd.DataFrame({"week_idx": np.arange(273)})
    df["split"] = splits.assign_split(df["week_idx"])
    rng = splits.validate_split(df)
    assert rng.loc["train", "max"] < rng.loc["dev", "min"] and rng.loc["dev", "max"] < rng.loc["test", "min"]


def test_validate_split_catches_overlap():
    df = pd.DataFrame({"week_idx": [1, 2, 3, 4], "split": ["train", "dev", "train", "test"]})
    with pytest.raises(AssertionError):
        splits.validate_split(df)


# ------------------------------------------------------------------ feature table
@pytest.fixture(scope="module")
def mini_feat(mini_clean):
    panel, _, _, _ = mini_clean
    feat, g, Y, P, info = features.build_feature_table(panel, TRAIN, DEV, TEST)
    return panel, feat, g, Y


def test_feature_table_split_is_time_ordered(mini_feat):
    _, feat, _, _ = mini_feat
    splits.validate_split(feat)
    assert set(feat["split"]) == {"train", "dev", "test"}


def test_rows_need_52_weeks_of_history_and_only_on_sale_weeks(mini_feat):
    _, feat, _, Y = mini_feat
    assert feat["week_idx"].min() >= 52
    assert not np.isnan(Y[feat["gi"].to_numpy(), feat["week_idx"].to_numpy()]).any()


def test_lag_feature_uses_only_the_past(mini_feat):
    _, feat, _, Y = mini_feat
    row = feat[feat["week_idx"] == 60].iloc[0]
    assert row["lag_1"] * row["scale"] == pytest.approx(Y[int(row["gi"]), 59])
    assert row["lag_4"] * row["scale"] == pytest.approx(Y[int(row["gi"]), 56])
    assert row["roll_mean_4"] * row["scale"] == pytest.approx(Y[int(row["gi"]), 56:60].mean())


def test_scale_uses_train_weeks_only(mini_clean, mini_feat):
    panel, feat, _, _ = mini_feat
    changed = pn.Panel(panel.series, panel.weeks, panel.units.copy(), panel.price)
    changed.units[:, TRAIN:] *= 10                                    # change dev / test demand only
    feat2, *_ = features.build_feature_table(changed, TRAIN, DEV, TEST)
    a = feat.groupby("gi")["scale"].first()
    b = feat2.groupby("gi")["scale"].first()
    assert a.equals(b)


def test_standardizer_fits_on_train_statistics_only():
    sc = features.Standardizer().fit(np.array([[1.0, 5.0], [3.0, 5.0]]))
    out = sc.transform(np.array([[2.0, 5.0], [100.0, 5.0]]))
    assert out[0, 0] == pytest.approx(0.0)                            # 2 is the TRAIN mean
    assert out[1, 0] == pytest.approx(98.0)                           # (100 - 2) / 1: a huge value does not change train mean/std
    assert out[0, 1] == 0.0                                           # constant column does not blow up


def test_winsor_cap_is_computed_on_train_rows_only(mini_feat):
    _, feat, _, _ = mini_feat
    cap = features.winsor_cap(feat)
    assert cap == pytest.approx(np.quantile(feat.loc[feat["split"] == "train", "y_scaled"], 0.999))


# ------------------------------------------------------------------ baselines
Y = np.array([[10.0, 20.0, 30.0, 40.0, 50.0]])


def test_naive_is_last_value():
    f = baselines.naive(Y)
    assert np.isnan(f[0, 0]) and f[0, 1:].tolist() == [10, 20, 30, 40]


def test_moving_average_hand_calculation():
    f = baselines.moving_average(Y, 2)
    assert np.isnan(f[0, 1]) and f[0, 2] == 15 and f[0, 4] == 35


def test_exponential_smoothing_recursion():
    f = baselines.exp_smoothing(Y, 0.5)
    assert f[0, 1] == 10 and f[0, 2] == 15 and f[0, 3] == pytest.approx(22.5)    # level: 10 -> 15 -> 22.5


def test_exponential_smoothing_skips_weeks_when_not_on_sale():
    f = baselines.exp_smoothing(np.array([[10.0, np.nan, 30.0]]), 0.5)
    assert f[0, 1] == 10 and f[0, 2] == 10                            # a NaN week does not move the level


def test_seasonal_naive_looks_one_season_back():
    assert baselines.seasonal_naive(Y, season=2)[0, 2:].tolist() == [10, 20, 30]


def test_baseline_forecast_never_uses_the_target_week():
    changed = Y.copy()
    changed[0, 4] = 9999
    assert baselines.naive(Y)[0, 4] == baselines.naive(changed)[0, 4]
    assert baselines.exp_smoothing(Y, 0.3)[0, 4] == baselines.exp_smoothing(changed, 0.3)[0, 4]
    assert baselines.moving_average(Y, 3)[0, 4] == baselines.moving_average(changed, 3)[0, 4]


def test_tuning_uses_only_the_dev_weeks():
    rng = np.random.default_rng(1)
    base = rng.poisson(20, size=(5, 40)).astype(float)
    k1, a1 = baselines.tune_on_dev(base, list(range(20, 30)))
    changed = base.copy()
    changed[:, 30:] = 999                                            # "test" weeks: must not influence the choice
    assert baselines.tune_on_dev(changed, list(range(20, 30))) == (k1, a1)


# ------------------------------------------------------------------ diagnosis + error analysis
def test_diagnosis_cases():
    assert "AVOIDABLE BIAS" in diagnosis.diagnose(0.10, 0.20, 0.21)["diagnosis"]
    assert "VARIANCE" in diagnosis.diagnose(0.10, 0.11, 0.25)["diagnosis"]
    d = diagnosis.diagnose(0.12, 0.10, 0.105)
    assert d["avoidable_bias"] == pytest.approx(-0.02) and d["variance"] == pytest.approx(0.005)


def _season_index():
    return pd.DataFrame([[1.0] * 12], index=["Cat"], columns=range(1, 13))


def _errors(**kw):
    base = dict(series=["a"], category=["Cat"], month_mid=[3], actual=[100], forecast=[110], price_cut=[0], price_cut_lag1=[0],
                event_flag=[0], prev8_mean=[100])
    base.update(kw)
    return pd.DataFrame(base)


def test_error_tags_and_priority_order():
    df = pd.concat([_errors(actual=[300]),                                          # outlier (3x the recent level)
                    _errors(price_cut=[1]),                                         # price-cut week
                    _errors(price_cut_lag1=[1]),                                    # week after a price cut
                    _errors(event_flag=[1]),                                        # event week
                    _errors()], ignore_index=True)                                  # nothing special
    tagged = ea.tag_errors(df, _season_index())
    assert tagged["primary_cause"].tolist() == ["outlier_week", "price_cut_week", "post_price_cut_week", "event_week", "no_clear_cause"]


def test_outlier_tag_has_priority_over_price_cut():
    assert ea.tag_errors(_errors(actual=[300], price_cut=[1]), _season_index())["primary_cause"].iloc[0] == "outlier_week"


def test_error_tally_shares_sum_to_one_and_lift_uses_base_rate():
    df = pd.concat([_errors(event_flag=[1]), _errors(), _errors(), _errors(event_flag=[1])], ignore_index=True)
    tagged = ea.tag_errors(df, _season_index())
    tal = ea.tally(tagged)
    assert tal["share_of_errors"].sum() == pytest.approx(1.0)
    tags = ea.tally_tags(tagged.iloc[:2], tagged).set_index("tag")
    assert tags.loc["event_week", "share"] == pytest.approx(0.5) and tags.loc["event_week", "base_rate_all_dev_rows"] == pytest.approx(0.5)
    assert tags.loc["event_week", "lift"] == pytest.approx(1.0)


def test_seasonal_turn_tag_fires_on_a_big_monthly_step():
    idx = pd.DataFrame([[1.0, 1.0, 1.3] + [1.0] * 9], index=["Cat"], columns=range(1, 13))
    t = ea.tag_errors(_errors(month_mid=[3]), idx)
    assert t["tag_seasonal_turn"].iloc[0] == 1                       # index jumps 1.0 -> 1.3 between Feb and Mar


# ------------------------------------------------------------------ inventory simulation (assumption-based)
def test_simulation_with_huge_safety_factor_serves_everything():
    rng = np.random.default_rng(0)
    actual = rng.poisson(20, size=(5, 12)).astype(float)
    r = policy_sim.simulate(actual, actual.copy(), np.full(5, 50.0), np.ones((5, 12)), z=10.0)
    assert r["fill_rate"] == pytest.approx(1.0) and r["lost_revenue"] == pytest.approx(0.0)


def test_simulation_with_no_stock_loses_sales_and_more_safety_stock_never_hurts():
    rng = np.random.default_rng(1)
    actual = rng.poisson(20, size=(8, 20)).astype(float)
    fc, sig, price = np.full_like(actual, 20.0), np.full(8, 5.0), np.ones((8, 20))
    low = policy_sim.simulate(actual, fc, sig, price, z=0.0)
    high = policy_sim.simulate(actual, fc, sig, price, z=2.0)
    assert high["fill_rate"] >= low["fill_rate"] and high["avg_inventory_value"] >= low["avg_inventory_value"]
    assert 0 < low["fill_rate"] <= 1


def test_inventory_at_target_interpolates_and_flags_unreachable_targets():
    front = pd.DataFrame({"model": ["m"] * 3 + ["n"] * 2, "z": [0, 1, 2, 0, 1], "fill_rate": [0.90, 0.96, 0.99, 0.80, 0.85],
                          "avg_inventory_value": [100.0, 200.0, 300.0, 50.0, 60.0]})
    out = policy_sim.inventory_at_target(front, target=0.93)
    assert out["m"] == pytest.approx(150.0)                          # halfway between 0.90 and 0.96
    assert np.isnan(out["n"])                                        # 95% never reached inside the grid

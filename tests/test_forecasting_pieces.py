import numpy as np
import pandas as pd
import pytest

import baselines
import diagnosis
import error_analysis as ea
import features
import kpis
import metrics
import splits


# ------------------------------------------------------------------ metrics
def test_wape_hand_calculation():
    # errors: 10, 0, 10 -> sum 20 ; actual sum 200 -> 10%
    assert metrics.wape([100, 50, 50], [110, 50, 40]) == pytest.approx(0.10)


def test_bias_sign_convention():
    assert metrics.bias([100, 100], [110, 110]) == pytest.approx(0.10)      # over-forecast = positive
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
    s = pd.Series(splits.assign_split(np.arange(104)))
    assert (s == "train").sum() == 72 and (s == "dev").sum() == 16 and (s == "test").sum() == 16
    assert s.iloc[0] == "train" and s.iloc[-1] == "test"


def test_split_is_chronological_with_no_overlap():
    df = pd.DataFrame({"week_idx": np.arange(104)})
    df["split"] = splits.assign_split(df["week_idx"])
    rng = splits.validate_split(df)
    assert rng.loc["train", "max"] < rng.loc["dev", "min"] < rng.loc["dev", "max"] < rng.loc["test", "min"]


def test_validate_split_catches_overlap():
    df = pd.DataFrame({"week_idx": [1, 2, 3, 4], "split": ["train", "dev", "train", "test"]})
    with pytest.raises(AssertionError):
        splits.validate_split(df)


@pytest.fixture(scope="module")
def small_feat(small_cleaned):
    tables, _ = small_cleaned
    weekly = kpis.weekly_demand(tables)
    return weekly, features.build_feature_table(weekly, train_weeks=18, dev_weeks=6, test_weeks=6)


def test_feature_table_split_is_time_ordered(small_feat):
    _, feat = small_feat
    splits.validate_split(feat)
    assert set(feat["split"]) == {"train", "dev", "test"}


def test_lag_feature_uses_only_the_past(small_feat):
    weekly, feat = small_feat
    row = feat[(feat["week_idx"] == 20)].iloc[0]
    prev = weekly[(weekly["sku"] == row["sku"]) & (weekly["week_idx"] == 19)]["units_demanded"].iloc[0]
    assert row["lag_1"] * row["scale"] == pytest.approx(prev)


def test_scale_uses_train_weeks_only(small_cleaned):
    tables, _ = small_cleaned
    weekly = kpis.weekly_demand(tables)
    a = features.build_feature_table(weekly, 18, 6, 6)
    changed = weekly.copy()
    changed.loc[changed["week_idx"] >= 18, "units_demanded"] *= 10          # change dev/test demand only
    b = features.build_feature_table(changed, 18, 6, 6)
    assert a.groupby("sku")["scale"].first().equals(b.groupby("sku")["scale"].first())


def test_standardizer_fits_on_train_statistics_only():
    train = np.array([[1.0, 5.0], [3.0, 5.0]])
    sc = features.Standardizer().fit(train)
    out = sc.transform(np.array([[2.0, 5.0], [100.0, 5.0]]))
    assert out[0, 0] == pytest.approx(0.0)                    # 2 is the TRAIN mean -> 0
    assert out[1, 0] == pytest.approx(98.0)                   # (100 - 2) / 1: a huge dev value does not change train mean/std
    assert out[0, 1] == 0.0                                   # constant column does not blow up


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
    # level0 = 10; f1 = 10; level1 = .5*20+.5*10 = 15; f2 = 15; level2 = 22.5; f3 = 22.5
    assert f[0, 1] == 10 and f[0, 2] == 15 and f[0, 3] == pytest.approx(22.5)


def test_seasonal_naive_looks_one_season_back():
    f = baselines.seasonal_naive(Y, season=2)
    assert f[0, 2:].tolist() == [10, 20, 30]


def test_baseline_forecast_never_uses_the_target_week():
    changed = Y.copy(); changed[0, 4] = 9999
    assert baselines.naive(Y)[0, 4] == baselines.naive(changed)[0, 4]
    assert baselines.exp_smoothing(Y, 0.3)[0, 4] == baselines.exp_smoothing(changed, 0.3)[0, 4]
    assert baselines.moving_average(Y, 3)[0, 4] == baselines.moving_average(changed, 3)[0, 4]


# ------------------------------------------------------------------ diagnosis + error analysis
def test_diagnosis_cases():
    assert "AVOIDABLE BIAS" in diagnosis.diagnose(0.10, 0.20, 0.21)["diagnosis"]
    assert "VARIANCE" in diagnosis.diagnose(0.10, 0.11, 0.25)["diagnosis"]
    d = diagnosis.diagnose(0.12, 0.10, 0.105)
    assert d["avoidable_bias"] == pytest.approx(-0.02) and d["variance"] == pytest.approx(0.005)


def _season_index():
    return pd.DataFrame([[1.0] * 12], index=["Cat"], columns=range(1, 13))


def test_error_tally_shares_sum_to_one_and_priority_order():
    df = pd.DataFrame({"sku": ["a", "b", "c"], "category": ["Cat"] * 3, "month_mid": [3, 3, 3], "actual": [100, 100, 100],
                       "forecast": [200, 50, 100], "promo_flag": [1, 0, 0], "promo_lag1": [0, 1, 0], "prev8_mean": [100, 100, 100]})
    tagged = ea.tag_errors(df, _season_index())
    assert tagged["primary_cause"].tolist() == ["promo_week", "post_promo_week", "no_clear_cause"]
    tal = ea.tally(tagged)
    assert tal["share_of_errors"].sum() == pytest.approx(1.0)


def test_outlier_tag_has_priority_over_promo():
    df = pd.DataFrame({"sku": ["a"], "category": ["Cat"], "month_mid": [3], "actual": [300], "forecast": [100],
                       "promo_flag": [1], "promo_lag1": [0], "prev8_mean": [100]})
    assert ea.tag_errors(df, _season_index())["primary_cause"].iloc[0] == "outlier_week"

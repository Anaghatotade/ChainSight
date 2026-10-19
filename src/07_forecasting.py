"""
Step 7 - Demand forecasting on real M5 data: interpretable baselines first, then ONE simple neural network as a challenger.

What happens here (in order):
  1. weekly item x state demand (9,147 series) -> feature table, TIME-based split (train 225 wks / dev 24 / test 24)
  2. baselines: Naive, Moving average, Exponential smoothing (+ seasonal naive as a reference)
  3. linear regression, then an MLP (NumPy, from scratch) with the same features
  4. ONE optimising metric (WAPE) + satisficing metrics (RMSE, bias, interpretability)
  5. bias / variance diagnosis, using the best baseline as the "human-level proxy"
  6. error analysis on the 100 biggest dev errors
  7. honest verdict: does the NN beat the baseline? at what cost in interpretability?
  8. what forecast accuracy means for inventory: a SIMULATION on real test-period demand with an ASSUMED lead time

Reads  data/processed/*
Writes outputs/tables/forecast_*.csv, error_analysis_*.csv, policy_sim_*.csv, outputs/charts/forecast_*.png,
       data/processed/forecast_predictions.csv.gz, adds numbers to outputs/tables/key_numbers.json

Run:  python src/07_forecasting.py          (about 5-15 minutes: five neural-network trainings on ~1.1 million rows)
"""
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor

import baselines
import config as cfg
import diagnosis
import error_analysis as ea
import features
import keynums as nums
import kpis
import metrics
import nn_numpy
import panel as pn
import policy_sim
import splits
import viz

BASELINE_NAMES = ["naive", "ma", "ses"]            # the three required baselines
MODEL_LABEL = {"naive": "Naive (last week)", "ma": "Moving average", "ses": "Exp. smoothing",
               "snaive": "Seasonal naive (ref.)", "linear": "Linear regression", "mlp": "MLP (NumPy NN)"}
INTERPRETABLE = {"naive": "Yes - one line", "ma": "Yes - one line", "ses": "Yes - one parameter",
                 "snaive": "Yes - one line", "linear": f"Yes - {len(features.FEATURES)} coefficients",
                 "mlp": "Partly - needs permutation importance"}

# candidate MLP settings, compared on the DEV set only (small manual comparison, not a search framework)
MLP_CANDIDATES = {
    "mlp_16":        dict(hidden=(16,),   l2=1e-4, dropout=0.0),
    "mlp_16_8":      dict(hidden=(16, 8), l2=1e-4, dropout=0.0),
    "mlp_16_8_l2":   dict(hidden=(16, 8), l2=1e-3, dropout=0.0),
    "mlp_16_8_drop": dict(hidden=(16, 8), l2=1e-4, dropout=0.1),
}


def wrap_label(m):
    """Two-line axis label for a model key, e.g. 'Moving\\naverage' or 'Naive\\n(last week)'."""
    label = MODEL_LABEL[m].replace(" (", "\n(")
    return label if "\n" in label else label.replace(" ", "\n", 1)


def train_mlp(Xtr, ytr, Xdev, ydev, params, seed):
    net = nn_numpy.NumpyMLP(Xtr.shape[1], hidden=params["hidden"], l2=params["l2"], dropout=params["dropout"], seed=seed)
    net.fit(Xtr, ytr, Xdev, ydev, epochs=cfg.NN_EPOCHS, batch_size=cfg.NN_BATCH, lr=cfg.NN_LR, patience=cfg.NN_PATIENCE)
    return net


def to_units(pred_scaled, scale):
    return np.clip(pred_scaled * scale, 0, None)          # demand cannot be negative


def main():
    t_start = time.time()
    cfg.ensure_dirs()
    viz.setup()
    panel = pn.load_panel()
    N = {}

    # ------------------------------------------------------------------ 1. features + split
    feat, g, Y, P, info = features.build_feature_table(panel)
    splits.validate_split(feat)
    weeks = panel.weeks
    cap = features.winsor_cap(feat)
    N.update(fc_cap=cap, fc_n_series=int(feat["gi"].nunique()), fc_n_series_total=info["n_series_total"],
             fc_n_series_dropped=info["n_series_dropped_no_train_sales"], fc_n_features=len(features.FEATURES))
    split_rows = feat.groupby("split").agg(rows=("y", "size"), first_week=("week_idx", "min"), last_week=("week_idx", "max"),
                                           mean_weekly_units=("y", "mean"), price_cut_share=("price_cut", "mean"),
                                           event_week_share=("event_flag", "mean"), mean_relative_demand=("y_scaled", "mean")).reindex(["train", "dev", "test"])
    split_rows["first_week_start"] = [weeks.loc[int(split_rows.loc[s, "first_week"]), "week_start"].date() for s in split_rows.index]
    split_rows["last_week_start"] = [weeks.loc[int(split_rows.loc[s, "last_week"]), "week_start"].date() for s in split_rows.index]
    split_rows.to_csv(cfg.TABLES / "forecast_split_summary.csv")
    for s in ("train", "dev", "test"):
        N[f"fc_{s}_rows"] = int(split_rows.loc[s, "rows"])
        N[f"fc_{s}_start_date"], N[f"fc_{s}_end_date"] = str(split_rows.loc[s, "first_week_start"]), str(split_rows.loc[s, "last_week_start"])
    N["fc_dev_mean_rel"], N["fc_test_mean_rel"] = split_rows.loc["dev", "mean_relative_demand"], split_rows.loc["test", "mean_relative_demand"]
    N["fc_dev_pricecut_share"], N["fc_test_pricecut_share"] = split_rows.loc["dev", "price_cut_share"], split_rows.loc["test", "price_cut_share"]
    N.update(fc_train_weeks=cfg.TRAIN_WEEKS, fc_dev_weeks=cfg.DEV_WEEKS, fc_test_weeks=cfg.TEST_WEEKS,
             fc_dev_start_week=cfg.TRAIN_WEEKS + 1, fc_dev_end_week=cfg.TRAIN_WEEKS + cfg.DEV_WEEKS,
             fc_test_start_week=cfg.TRAIN_WEEKS + cfg.DEV_WEEKS + 1, fc_test_end_week=cfg.TRAIN_WEEKS + cfg.DEV_WEEKS + cfg.TEST_WEEKS,
             fc_n_seeds=len(cfg.NN_SEEDS), fc_bias_limit=cfg.BIAS_LIMIT, fc_min_gain=cfg.MIN_RELATIVE_GAIN, ea_n_target=cfg.N_ERROR_ANALYSIS,
             fc_min_history=cfg.MIN_HISTORY, fc_scale_floor=cfg.SCALE_FLOOR, fc_winsor_q=cfg.WINSOR_Q)
    N["fc_zero_share_rows"] = float((feat["y"] == 0).mean())

    # ------------------------------------------------------------------ 2. baselines (tuned on DEV only)
    dev_cols = list(range(cfg.TRAIN_WEEKS, cfg.TRAIN_WEEKS + cfg.DEV_WEEKS))
    k, alpha = baselines.tune_on_dev(Y, dev_cols)
    N["fc_ma_window"], N["fc_ses_alpha"] = k, alpha
    mats = {"naive": baselines.naive(Y), "ma": baselines.moving_average(Y, k),
            "ses": baselines.exp_smoothing(Y, alpha), "snaive": baselines.seasonal_naive(Y)}
    for name, M in mats.items():
        feat[name] = M[feat["gi"].to_numpy(), feat["week_idx"].to_numpy()]

    # ------------------------------------------------------------------ 3. linear regression + MLP
    tr, dv, te = ((feat["split"] == s).to_numpy() for s in ("train", "dev", "test"))
    Xraw = features.model_matrix(feat, cap)
    scaler = features.Standardizer().fit(Xraw[tr])                                  # TRAIN statistics only
    X = scaler.transform(Xraw)
    y = np.minimum(feat["y_scaled"].to_numpy(), cap)                                # capped TRAINING target
    scale = feat["scale"].to_numpy()
    y_units = feat["y"].to_numpy()

    Xb = np.hstack([X, np.ones((len(X), 1))])                                       # linear regression (least squares)
    coef, *_ = np.linalg.lstsq(Xb[tr], y[tr], rcond=None)
    feat["linear"] = to_units(Xb @ coef, scale)
    lin_coef = pd.DataFrame({"feature": features.FEATURES + ["intercept"], "standardised_coefficient": coef})
    lin_coef.to_csv(cfg.TABLES / "forecast_linear_coefficients.csv", index=False)

    cand_rows, cand_nets = [], {}
    for name, params in MLP_CANDIDATES.items():
        t0 = time.time()
        net = train_mlp(X[tr], y[tr], X[dv], y[dv], params, seed=cfg.NN_SEEDS[0])
        pred = to_units(net.predict(X[dv]), scale[dv])
        cand_rows.append(dict(candidate=name, hidden=str(params["hidden"]), l2=params["l2"], dropout=params["dropout"],
                              best_epoch=net.best_epoch, dev_WAPE=metrics.wape(y_units[dv], pred), train_seconds=round(time.time() - t0, 1)))
        cand_nets[name] = net
        print(f"  trained {name}: dev WAPE {cand_rows[-1]['dev_WAPE']:.4f} ({cand_rows[-1]['train_seconds']}s)", flush=True)
    cand = pd.DataFrame(cand_rows).sort_values("dev_WAPE").reset_index(drop=True)
    cand.to_csv(cfg.TABLES / "forecast_mlp_candidates_dev.csv", index=False)
    best_name = cand.iloc[0]["candidate"]
    N["fc_mlp_choice"], N["fc_mlp_hidden"] = best_name, cand.iloc[0]["hidden"]
    N["fc_mlp_l2"], N["fc_mlp_dropout"] = float(cand.iloc[0]["l2"]), float(cand.iloc[0]["dropout"])

    # final MLP: chosen setting, 5 seeds -> report the spread, keep seed-42 as "the" model
    params = MLP_CANDIDATES[best_name]
    seed_rows, main_net = [], None
    seed_test_pred = {}
    for seed in cfg.NN_SEEDS:
        net = cand_nets[best_name] if seed == cfg.NN_SEEDS[0] else train_mlp(X[tr], y[tr], X[dv], y[dv], params, seed)
        if seed == cfg.NN_SEEDS[0]:
            main_net = net
        row = {"seed": seed, "best_epoch": net.best_epoch}
        for s_name, mask in (("dev", dv), ("test", te)):
            row[f"{s_name}_WAPE"] = metrics.wape(y_units[mask], to_units(net.predict(X[mask]), scale[mask]))
        seed_rows.append(row)
    seeds = pd.DataFrame(seed_rows)
    seeds.to_csv(cfg.TABLES / "forecast_mlp_seed_spread.csv", index=False)
    feat["mlp"] = to_units(main_net.predict(X), scale)
    N["fc_mlp_test_wape_min"], N["fc_mlp_test_wape_max"] = seeds["test_WAPE"].min(), seeds["test_WAPE"].max()
    N["fc_mlp_test_wape_mean"] = seeds["test_WAPE"].mean()
    N["fc_mlp_best_epoch"] = main_net.best_epoch
    N["fc_n_parameters"] = int(sum(w.size + b.size for w, b in zip(main_net.W, main_net.b)))

    # independent sanity check: scikit-learn's MLPRegressor with the same architecture (NOT a separate model)
    sk = MLPRegressor(hidden_layer_sizes=params["hidden"], alpha=params["l2"], learning_rate_init=cfg.NN_LR, batch_size=cfg.NN_BATCH,
                      max_iter=cfg.NN_EPOCHS, early_stopping=True, n_iter_no_change=cfg.NN_PATIENCE, random_state=cfg.NN_SEEDS[0])
    sk.fit(X[tr], y[tr])
    N["fc_sklearn_check_test_wape"] = metrics.wape(y_units[te], to_units(sk.predict(X[te]), scale[te]))

    # ------------------------------------------------------------------ 4. scorecard: optimising + satisficing metrics
    model_cols = ["naive", "ma", "ses", "snaive", "linear", "mlp"]
    rows = []
    for m in model_cols:
        for s_name, mask in (("train", tr), ("dev", dv), ("test", te)):
            rows.append(dict(model=m, split=s_name, **metrics.score_all(y_units[mask], feat.loc[mask, m])))
    score = pd.DataFrame(rows)
    score.to_csv(cfg.TABLES / "forecast_metrics_long.csv", index=False)
    wide = score.pivot(index="model", columns="split")
    summary = pd.DataFrame({
        "model": [MODEL_LABEL[m] for m in model_cols], "model_key": model_cols,
        "WAPE_train": [wide.loc[m, ("WAPE", "train")] for m in model_cols],
        "WAPE_dev": [wide.loc[m, ("WAPE", "dev")] for m in model_cols],
        "WAPE_test": [wide.loc[m, ("WAPE", "test")] for m in model_cols],
        "RMSE_dev": [wide.loc[m, ("RMSE", "dev")] for m in model_cols],
        "RMSE_test": [wide.loc[m, ("RMSE", "test")] for m in model_cols],
        "Bias_dev": [wide.loc[m, ("Bias", "dev")] for m in model_cols],
        "Bias_test": [wide.loc[m, ("Bias", "test")] for m in model_cols],
        "MAPE_test": [wide.loc[m, ("MAPE", "test")] for m in model_cols],
        "interpretable": [INTERPRETABLE[m] for m in model_cols],
    })
    naive_rmse_dev = float(summary.loc[summary["model_key"] == "naive", "RMSE_dev"].iloc[0])
    summary["gate_bias_ok_dev"] = summary["Bias_dev"].abs() <= cfg.BIAS_LIMIT
    summary["gate_rmse_ok_dev"] = summary["RMSE_dev"] <= naive_rmse_dev
    summary["passes_gates"] = summary["gate_bias_ok_dev"] & summary["gate_rmse_ok_dev"]
    summary.to_csv(cfg.TABLES / "forecast_model_comparison.csv", index=False)
    S = summary.set_index("model_key")

    best_bl = min(BASELINE_NAMES, key=lambda m: S.loc[m, "WAPE_dev"])         # chosen on DEV
    N["fc_best_baseline"], N["fc_best_baseline_key"] = MODEL_LABEL[best_bl], best_bl
    for m in model_cols:
        N[f"fc_wape_dev_{m}"], N[f"fc_wape_test_{m}"] = S.loc[m, "WAPE_dev"], S.loc[m, "WAPE_test"]
        N[f"fc_bias_test_{m}"], N[f"fc_rmse_test_{m}"] = S.loc[m, "Bias_test"], S.loc[m, "RMSE_test"]
        N[f"fc_passes_gates_{m}"] = bool(S.loc[m, "passes_gates"])
    N["fc_wape_train_best_baseline"] = S.loc[best_bl, "WAPE_train"]
    N["fc_wape_train_mlp"], N["fc_wape_train_linear"] = S.loc["mlp", "WAPE_train"], S.loc["linear", "WAPE_train"]

    # decision rule: complexity must earn its place (>= MIN_RELATIVE_GAIN on DEV, then confirmed on TEST)
    choice = best_bl
    for m in ("linear", "mlp"):
        if S.loc[m, "passes_gates"] and S.loc[m, "WAPE_dev"] <= S.loc[choice, "WAPE_dev"] * (1 - cfg.MIN_RELATIVE_GAIN):
            choice = m
    confirmed = S.loc[choice, "WAPE_test"] < S.loc[best_bl, "WAPE_test"] if choice != best_bl else True
    final_model = choice if confirmed else best_bl
    N["fc_final_model"], N["fc_final_model_key"] = MODEL_LABEL[final_model], final_model
    N["fc_final_confirmed_on_test"] = bool(confirmed)

    base_test, mlp_test = S.loc[best_bl, "WAPE_test"], S.loc["mlp", "WAPE_test"]
    rel_gain = (base_test - mlp_test) / base_test
    N["fc_mlp_rel_gain_vs_baseline_test"] = rel_gain
    N["fc_mlp_rel_gain_vs_baseline_dev"] = (S.loc[best_bl, "WAPE_dev"] - S.loc["mlp", "WAPE_dev"]) / S.loc[best_bl, "WAPE_dev"]
    N["fc_linear_rel_gain_vs_baseline_test"] = (base_test - S.loc["linear", "WAPE_test"]) / base_test
    N["fc_linear_rel_gain_vs_baseline_dev"] = (S.loc[best_bl, "WAPE_dev"] - S.loc["linear", "WAPE_dev"]) / S.loc[best_bl, "WAPE_dev"]
    N["fc_mlp_rel_gain_vs_linear_test"] = (S.loc["linear", "WAPE_test"] - mlp_test) / S.loc["linear", "WAPE_test"]
    N["fc_mlp_worst_seed_beats_baseline"] = bool(seeds["test_WAPE"].max() < base_test)
    if rel_gain >= cfg.MIN_RELATIVE_GAIN and N["fc_mlp_worst_seed_beats_baseline"]:
        verdict = "NN_WINS"
    elif rel_gain > 0:
        verdict = "MARGINAL"
    else:
        verdict = "BASELINE_WINS"
    N["fc_verdict"] = verdict
    N["fc_snaive_beats_best_baseline_test"] = bool(S.loc["snaive", "WAPE_test"] < base_test)
    N["fc_mlp_beats_snaive_test"] = bool(mlp_test < S.loc["snaive", "WAPE_test"])
    N["fc_mlp_bias_ok"] = bool(abs(S.loc["mlp", "Bias_test"]) <= cfg.BIAS_LIMIT)

    # ------------------------------------------------------------------ 5. bias / variance diagnosis
    diag = {m: diagnosis.diagnose(S.loc[best_bl, "WAPE_train"], S.loc[m, "WAPE_train"], S.loc[m, "WAPE_dev"]) for m in ("mlp", "linear")}
    pd.DataFrame(diag).T.to_csv(cfg.TABLES / "forecast_bias_variance_diagnosis.csv")
    N["fc_avoidable_bias_mlp"], N["fc_variance_mlp"] = diag["mlp"]["avoidable_bias"], diag["mlp"]["variance"]
    N["fc_diagnosis_mlp"] = diag["mlp"]["diagnosis"]
    N["fc_avoidable_bias_linear"], N["fc_variance_linear"] = diag["linear"]["avoidable_bias"], diag["linear"]["variance"]

    # ------------------------------------------------------------------ 6. segment view + error analysis (DEV set)
    gi = feat["gi"].to_numpy()
    feat["category"] = g["cat_id"].to_numpy()[gi]
    feat["state"] = g["state_id"].to_numpy()[gi]
    feat["series"] = (g["item_id"] + " | " + g["state_id"]).to_numpy()[gi]
    train_rev = np.nansum(Y[:, :cfg.TRAIN_WEEKS] * np.round(np.nan_to_num(P[:, :cfg.TRAIN_WEEKS]), 2), axis=1)   # ABC from TRAIN revenue only
    abc_g = kpis.abc_classify(pd.Series(train_rev, index=np.arange(len(g))))
    feat["abc_class"] = abc_g.to_numpy()[gi]
    feat["week_start"] = weeks["week_start"].to_numpy()[feat["week_idx"].to_numpy()]

    seg_rows = []
    for split_name in ("dev", "test"):
        part = feat[feat["split"] == split_name]
        for seg_col in ("category", "state", "abc_class", "price_cut", "event_flag"):
            for key, grp in part.groupby(seg_col):
                seg_rows.append(dict(split=split_name, segment_type=seg_col, segment=key, n_rows=len(grp), actual_units=grp["y"].sum(),
                                     WAPE_baseline=metrics.wape(grp["y"], grp[best_bl]), WAPE_mlp=metrics.wape(grp["y"], grp["mlp"]),
                                     WAPE_linear=metrics.wape(grp["y"], grp["linear"]),
                                     Bias_baseline=metrics.bias(grp["y"], grp[best_bl]), Bias_mlp=metrics.bias(grp["y"], grp["mlp"])))
    seg = pd.DataFrame(seg_rows)
    seg["mlp_better"] = seg["WAPE_mlp"] < seg["WAPE_baseline"]
    seg.to_csv(cfg.TABLES / "forecast_segment_wape.csv", index=False)
    test_seg = seg[(seg["split"] == "test") & (seg["segment_type"].isin(["category", "state", "abc_class"]))]
    N["fc_segments_mlp_better_test"], N["fc_segments_total"] = int(test_seg["mlp_better"].sum()), int(len(test_seg))
    pc = seg[(seg["split"] == "test") & (seg["segment_type"] == "price_cut")].set_index("segment")
    N["fc_n_pricecut_rows_test"] = int(pc.loc[1, "n_rows"]) if 1 in pc.index else 0
    if 1 in pc.index:
        N["fc_pricecut_wape_baseline_test"], N["fc_pricecut_wape_mlp_test"] = pc.loc[1, "WAPE_baseline"], pc.loc[1, "WAPE_mlp"]
    N["fc_nocut_wape_baseline_test"], N["fc_nocut_wape_mlp_test"] = pc.loc[0, "WAPE_baseline"], pc.loc[0, "WAPE_mlp"]
    abc_seg = seg[(seg["split"] == "test") & (seg["segment_type"] == "abc_class")].set_index("segment")
    for c in "ABC":
        N[f"fc_wape_test_abc_{c}_baseline"], N[f"fc_wape_test_abc_{c}_mlp"] = abc_seg.loc[c, "WAPE_baseline"], abc_seg.loc[c, "WAPE_mlp"]
    cat_seg = seg[(seg["split"] == "test") & (seg["segment_type"] == "category")].set_index("segment")
    for c in cat_seg.index:
        N[f"fc_wape_test_cat_{c}_baseline"], N[f"fc_wape_test_cat_{c}_mlp"] = cat_seg.loc[c, "WAPE_baseline"], cat_seg.loc[c, "WAPE_mlp"]
    N["fc_worst_category_baseline"] = cat_seg["WAPE_baseline"].idxmax()

    dev_df = feat[feat["split"] == "dev"].rename(columns={"y": "actual", "mlp": "forecast"}).copy()
    dev_df["baseline_forecast"] = dev_df[best_bl]
    season_idx = ea.category_season_index(panel)
    tagged = ea.tag_errors(dev_df, season_idx)
    tagged["baseline_abs_error"] = (tagged["baseline_forecast"] - tagged["actual"]).abs()
    top = tagged.sort_values("abs_error", ascending=False).head(cfg.N_ERROR_ANALYSIS).reset_index(drop=True)
    top.insert(0, "rank", np.arange(1, len(top) + 1))
    top["mlp_beats_baseline"] = (top["abs_error"] < top["baseline_abs_error"]).astype(int)
    keep = ["rank", "series", "category", "state", "abc_class", "week_start", "actual", "forecast", "baseline_forecast", "error", "abs_error",
            "pct_error", "price_cut", "price_cut_lag1", "event_flag", "tag_outlier_week", "tag_price_cut_week", "tag_post_price_cut_week",
            "tag_seasonal_turn", "tag_event_week", "primary_cause", "direction", "mlp_beats_baseline"]
    out = top[keep].copy()
    out["week_start"] = pd.to_datetime(out["week_start"]).dt.strftime("%Y-%m-%d")
    out[["actual", "forecast", "baseline_forecast", "error", "abs_error"]] = out[["actual", "forecast", "baseline_forecast", "error", "abs_error"]].round(1)
    out["pct_error"] = out["pct_error"].round(3)
    out["manual_cause"] = ""          # <- fill in yourself after eyeballing the row
    out["notes"] = ""
    out.to_csv(cfg.TABLES / "error_analysis_top100.csv", index=False)
    tal = ea.tally(top)
    tal.to_csv(cfg.TABLES / "error_analysis_tally.csv", index=False)
    tags_df = ea.tally_tags(top, tagged)
    tags_df.to_csv(cfg.TABLES / "error_analysis_tags.csv", index=False)
    by_cat = top.groupby("category").agg(n_errors=("abs_error", "size"), abs_error_units=("abs_error", "sum")).sort_values("n_errors", ascending=False)
    by_cat["share"] = by_cat["n_errors"] / by_cat["n_errors"].sum()
    by_cat.reset_index().to_csv(cfg.TABLES / "error_analysis_by_category.csv", index=False)
    by_abc = top.groupby("abc_class").agg(n_errors=("abs_error", "size")).reset_index()
    by_abc["share"] = by_abc["n_errors"] / by_abc["n_errors"].sum()
    by_abc.to_csv(cfg.TABLES / "error_analysis_by_abc.csv", index=False)

    biggest = tal.sort_values("n_errors", ascending=False).iloc[0]
    N["ea_top_n"] = len(top)
    N["ea_top_cause"], N["ea_top_cause_n"], N["ea_top_cause_share"] = biggest["primary_cause"], int(biggest["n_errors"]), biggest["share_of_errors"]
    N["ea_top_cause_error_share"] = biggest["share_of_error_units"]
    for _, r in tal.iterrows():
        N[f"ea_n_{r['primary_cause']}"] = int(r["n_errors"])
    N["ea_top_share_of_dev_error"] = top["abs_error"].sum() / tagged["abs_error"].sum()
    N["ea_under_forecast_share"] = float((top["direction"] == "under-forecast").mean())
    N["ea_top_category"], N["ea_top_category_n"] = by_cat.index[0], int(by_cat.iloc[0]["n_errors"])
    N["ea_a_class_share"] = float((top["abc_class"] == "A").mean())
    N["ea_mlp_beats_baseline_share"] = float(top["mlp_beats_baseline"].mean())
    N["ea_n_series_in_top"] = int(top["series"].nunique())
    N["ea_top_series"] = top.iloc[0]["series"]
    T = tags_df.set_index("tag")
    for t in ea.TAGS:
        N[f"ea_tag_{t}_n"], N[f"ea_tag_{t}_lift"], N[f"ea_tag_{t}_base"] = int(T.loc[t, "n_errors"]), float(T.loc[t, "lift"]), float(T.loc[t, "base_rate_all_dev_rows"])
    N["ea_n_weeks_top_in_one_week"] = int(top["week_start"].value_counts().iloc[0])
    N["ea_top_week"] = str(pd.to_datetime(top["week_start"].value_counts().index[0]).date())

    # ------------------------------------------------------------------ 7. permutation importance (interpretability trade-off)
    rng = np.random.default_rng(0)
    Xd, yd_raw, sd = X[dv], y_units[dv], scale[dv]
    base_w = metrics.wape(yd_raw, to_units(main_net.predict(Xd), sd))
    imp = []
    for j, f in enumerate(features.FEATURES):
        incr = []
        for _ in range(5):
            Xp = Xd.copy()
            Xp[:, j] = rng.permutation(Xp[:, j])
            incr.append(metrics.wape(yd_raw, to_units(main_net.predict(Xp), sd)) - base_w)
        imp.append(dict(feature=f, wape_increase=float(np.mean(incr))))
    imp = pd.DataFrame(imp).sort_values("wape_increase", ascending=False)
    imp.to_csv(cfg.TABLES / "forecast_mlp_permutation_importance.csv", index=False)
    N["fc_top_feature"], N["fc_top_feature_increase"] = imp.iloc[0]["feature"], imp.iloc[0]["wape_increase"]
    N["fc_second_feature"] = imp.iloc[1]["feature"]
    N["fc_lag52_importance_rank"] = int(list(imp["feature"]).index("lag_52") + 1)

    # ------------------------------------------------------------------ 8. inventory-policy SIMULATION (assumed lead time, real demand)
    Tn = cfg.TEST_WEEKS
    cnt = feat[feat["split"] != "train"].groupby(["gi", "split"]).size().unstack(fill_value=0)
    complete = cnt.index[(cnt["test"] == Tn) & (cnt["dev"] >= cfg.DEV_WEEKS // 2)].to_numpy()
    pos = {gv: i for i, gv in enumerate(complete)}
    n_sim = len(complete)
    sim_models = [best_bl, "naive", "linear", "mlp"] if best_bl != "naive" else ["naive", "linear", "mlp"]
    t_rows = feat[te & feat["gi"].isin(complete).to_numpy()]
    d_rows = feat[dv & feat["gi"].isin(complete).to_numpy()]
    ti = t_rows["gi"].map(pos).to_numpy(); tw = (t_rows["week_idx"].to_numpy() - (cfg.TRAIN_WEEKS + cfg.DEV_WEEKS))
    actual_sim = np.zeros((n_sim, Tn)); price_sim = np.zeros((n_sim, Tn))
    actual_sim[ti, tw] = t_rows["y"].to_numpy(); price_sim[ti, tw] = t_rows["price"].to_numpy()
    fc_sim, sig_sim = {}, {}
    for m in sim_models:
        fm = np.zeros((n_sim, Tn)); fm[ti, tw] = t_rows[m].to_numpy()
        fc_sim[m] = fm
        err = (d_rows[m] - d_rows["y"]).groupby(d_rows["gi"]).std(ddof=0).reindex(complete)      # DEV forecast-error std per series
        sig_sim[m] = np.nan_to_num(err.to_numpy(), nan=0.0)
    front = policy_sim.frontier(actual_sim, fc_sim, sig_sim, price_sim)
    front["model_label"] = front["model"].map(MODEL_LABEL)
    front.to_csv(cfg.TABLES / "policy_sim_frontier.csv", index=False)
    inv_at = policy_sim.inventory_at_target(front)
    at_z = front[np.isclose(front["z"], cfg.SERVICE_Z, atol=0.3)]
    sim_sum = pd.DataFrame({"model": [MODEL_LABEL[m] for m in sim_models], "model_key": sim_models,
                            "inventory_value_at_95pct_fill": [inv_at[m] for m in sim_models]})
    sim_sum.to_csv(cfg.TABLES / "policy_sim_summary.csv", index=False)
    N.update(sim_n_series=n_sim, sim_lead_time_weeks=cfg.ASSUMED_LEAD_TIME_WEEKS, sim_review_weeks=cfg.REVIEW_PERIOD_WEEKS,
             sim_target_fill=cfg.FILL_RATE_TARGET, sim_demand_units=float(actual_sim.sum()))
    for m in sim_models:
        N[f"sim_inv_at_target_{m}"] = inv_at[m]
        for z in (1.0, 1.5, 2.0):
            r = front[(front["model"] == m) & np.isclose(front["z"], z)].iloc[0]
            N[f"sim_fill_z{int(z * 10)}_{m}"], N[f"sim_inv_z{int(z * 10)}_{m}"] = float(r["fill_rate"]), float(r["avg_inventory_value"])
    ref, cmp_ = inv_at[best_bl], inv_at["mlp"]
    N["sim_mlp_inventory_change_vs_baseline"] = (cmp_ - ref) / ref if np.isfinite(ref) and np.isfinite(cmp_) else None
    N["sim_linear_inventory_change_vs_baseline"] = (inv_at["linear"] - ref) / ref if np.isfinite(ref) and np.isfinite(inv_at["linear"]) else None
    N["sim_fill_best_z"] = float(front[front["model"] == "mlp"]["fill_rate"].max())

    # ------------------------------------------------------------------ save predictions (regenerable, not committed)
    pred_cols = ["series", "category", "state", "abc_class", "week_idx", "week_start", "split", "price", "price_cut", "event_flag"] + model_cols
    preds = feat[feat["split"].isin(["dev", "test"])][pred_cols].copy()
    preds.insert(7, "actual", feat.loc[preds.index, "y"])
    preds[model_cols] = preds[model_cols].round(2)
    preds.to_csv(cfg.DATA_PROCESSED / "forecast_predictions.csv.gz", index=False, compression="gzip")

    # ------------------------------------------------------------------ charts
    order = ["naive", "ma", "ses", "snaive", "linear", "mlp"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    x = np.arange(len(order)); w = 0.38
    axes[0].bar(x - w / 2, [S.loc[m, "WAPE_dev"] for m in order], w, label="Dev", color=viz.PALETTE["grey"])
    axes[0].bar(x + w / 2, [S.loc[m, "WAPE_test"] for m in order], w, label="Test", color=viz.PALETTE["main"])
    axes[0].set_xticks(x); axes[0].set_xticklabels([wrap_label(m) for m in order], fontsize=8)
    viz.pct_axis(axes[0]); axes[0].set_title("Forecast error (WAPE) - lower is better"); axes[0].legend()
    for i, m in enumerate(order):
        axes[0].text(i + w / 2, S.loc[m, "WAPE_test"] + 0.002, f"{S.loc[m, 'WAPE_test']:.1%}", ha="center", fontsize=8)
    axes[1].bar(x, [S.loc[m, "Bias_test"] for m in order], color=[viz.PALETTE["good"] if abs(S.loc[m, "Bias_test"]) <= cfg.BIAS_LIMIT else viz.PALETTE["bad"] for m in order])
    axes[1].axhline(cfg.BIAS_LIMIT, color="black", ls="--", lw=1); axes[1].axhline(-cfg.BIAS_LIMIT, color="black", ls="--", lw=1)
    axes[1].set_xticks(x); axes[1].set_xticklabels([wrap_label(m) for m in order], fontsize=8)
    viz.pct_axis(axes[1]); axes[1].set_title(f"Bias on test (limit +/-{cfg.BIAS_LIMIT:.0%}): + over, - under-forecast", fontsize=11)
    viz.save(fig, "forecast_01_model_comparison")

    h = main_net.history
    fig, ax = plt.subplots(figsize=(8, 4.5))
    epochs = list(range(1, len(h["train_loss"]) + 1))      # epochs counted from 1, so the line matches the label
    ax.plot(epochs, h["train_loss"], label="Train loss", color=viz.PALETTE["main"])
    ax.plot(epochs, h["dev_loss"], label="Dev loss", color=viz.PALETTE["accent"])
    ax.axvline(main_net.best_epoch, color="black", ls="--", lw=1, label=f"best epoch ({main_net.best_epoch})")
    ax.set_xlabel("Epoch"); ax.set_ylabel("MSE loss (relative demand)"); ax.set_title("MLP learning curve (early stopping on dev)")
    ax.legend()
    viz.save(fig, "forecast_02_learning_curve")

    sub = feat[feat["split"] != "train"]
    vol = sub.groupby("series")["y"].sum().sort_values(ascending=False)
    cvs = sub.groupby("series")["y"].agg(lambda s: s.std() / s.mean() if s.mean() > 0 else 0)
    pick = list(vol.index[:2])
    pick.append(cvs[vol.index[:500]].drop(pick, errors="ignore").idxmax())
    pick.append(sub.groupby("series")["price_cut"].sum().drop(pick, errors="ignore").idxmax())
    fig, axes = plt.subplots(2, 2, figsize=(13, 7))
    for ax, s in zip(axes.ravel(), pick):
        gg = sub[sub["series"] == s].sort_values("week_idx")
        ax.plot(gg["week_start"], gg["y"], color="black", lw=2, label="Actual")
        ax.plot(gg["week_start"], gg[best_bl], color=viz.PALETTE["grey"], lw=1.5, label=MODEL_LABEL[best_bl])
        ax.plot(gg["week_start"], gg["mlp"], color=viz.PALETTE["accent"], lw=1.8, label="MLP")
        ax.scatter(gg.loc[gg["price_cut"] == 1, "week_start"], gg.loc[gg["price_cut"] == 1, "y"], color=viz.PALETTE["bad"], zorder=5, s=25, label="Price-cut week")
        ax.axvline(feat.loc[te, "week_start"].min(), color="grey", ls=":")
        ax.set_title(f"{s}  ({gg['category'].iloc[0]}, class {gg['abc_class'].iloc[0]})", fontsize=10); ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Weekly demand: actual vs forecasts (dev | test, dotted line = start of test)", fontweight="bold")
    viz.save(fig, "forecast_03_actual_vs_forecast")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
    tt = tal.set_index("primary_cause").reindex(ea.CAUSE_ORDER)
    axes[0].barh([c.replace("_", " ") for c in tt.index], tt["n_errors"], color=viz.PALETTE["main"])
    axes[0].invert_yaxis(); axes[0].set_title(f"Top {len(top)} dev errors by primary cause"); axes[0].set_xlabel("Number of errors")
    bc = by_cat.sort_values("n_errors")
    axes[1].barh(bc.index, bc["n_errors"], color=[viz.CAT_COLORS[c] for c in bc.index]); axes[1].set_title("... by category"); axes[1].set_xlabel("Number of errors")
    over = (top["direction"] == "over-forecast").sum()
    axes[2].bar(["Over-forecast", "Under-forecast"], [over, len(top) - over], color=[viz.PALETTE["grey"], viz.PALETTE["bad"]])
    axes[2].set_title("... by direction (under = stockout risk)")
    viz.save(fig, "forecast_04_error_analysis")

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar(seeds["seed"].astype(str), seeds["test_WAPE"], color=viz.PALETTE["accent"], label="MLP (test WAPE)")
    ax.axhline(base_test, color=viz.PALETTE["main"], lw=2, label=f"Best baseline: {MODEL_LABEL[best_bl]}")
    ax.axhline(S.loc["linear", "WAPE_test"], color=viz.PALETTE["good"], lw=2, ls="--", label="Linear regression")
    lo = min(seeds["test_WAPE"].min(), base_test, S.loc["linear", "WAPE_test"]); hi = max(seeds["test_WAPE"].max(), base_test, S.loc["linear", "WAPE_test"])
    ax.set_ylim(lo * 0.97, hi * 1.02)
    viz.pct_axis(ax); ax.set_xlabel("Random seed"); ax.set_title("MLP result depends a little on the random seed"); ax.legend(fontsize=8)
    viz.save(fig, "forecast_05_seed_spread")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    lc = lin_coef[lin_coef["feature"] != "intercept"].sort_values("standardised_coefficient")
    axes[0].barh(lc["feature"], lc["standardised_coefficient"], color=viz.PALETTE["main"]); axes[0].set_title("Linear regression: standardised coefficients")
    im = imp.sort_values("wape_increase")
    axes[1].barh(im["feature"], im["wape_increase"], color=viz.PALETTE["accent"]); axes[1].set_title("MLP: permutation importance (WAPE increase on dev)")
    viz.save(fig, "forecast_06_interpretability")

    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
    styles = {best_bl: (viz.PALETTE["main"], "-"), "naive": (viz.PALETTE["grey"], ":"), "linear": (viz.PALETTE["good"], "--"), "mlp": (viz.PALETTE["accent"], "-")}
    for m in sim_models:
        gg = front[front["model"] == m].sort_values("z")
        col, ls = styles.get(m, (viz.PALETTE["grey"], "-"))
        axes[0].plot(gg["avg_inventory_value"], gg["fill_rate"], marker="o", color=col, ls=ls, lw=2, label=MODEL_LABEL[m])
    axes[0].axhline(cfg.FILL_RATE_TARGET, color="black", ls="--", lw=1)
    axes[0].set_xlabel("Average inventory (retail $, all item-state series)"); axes[0].set_ylabel("Fill rate on test weeks")
    viz.pct_axis(axes[0]); viz.money_axis(axes[0], axis="x", unit=1e6, suffix="M"); axes[0].legend(fontsize=8)
    axes[0].set_title("SIMULATION (assumed 1-week lead time): service vs inventory")
    vals = [inv_at[m] for m in sim_models]
    axes[1].bar([MODEL_LABEL[m].replace(" (", "\n(") for m in sim_models], vals, color=[styles.get(m, (viz.PALETTE["grey"], ""))[0] for m in sim_models])
    for i, v in enumerate(vals):
        if np.isfinite(v):
            axes[1].text(i, v, f"${v / 1e6:,.2f}M", ha="center", va="bottom", fontsize=9)
    axes[1].set_title(f"Inventory needed for {cfg.FILL_RATE_TARGET:.0%} fill rate (simulation)"); viz.money_axis(axes[1], unit=1e6, suffix="M")
    viz.save(fig, "forecast_07_policy_simulation")

    nums.save(N)
    print(summary[["model", "WAPE_train", "WAPE_dev", "WAPE_test", "Bias_test", "passes_gates"]].round(4).to_string(index=False))
    print(); print(cand.to_string(index=False)); print(seeds.round(4).to_string(index=False))
    print(tal.round(3).to_string(index=False)); print(tags_df.round(3).to_string(index=False))
    print(front.round(4).to_string(index=False)); print(sim_sum.to_string(index=False))
    for k_ in ("fc_best_baseline", "fc_final_model", "fc_verdict", "fc_mlp_rel_gain_vs_baseline_test", "fc_linear_rel_gain_vs_baseline_test",
               "fc_avoidable_bias_mlp", "fc_variance_mlp", "fc_sklearn_check_test_wape", "sim_mlp_inventory_change_vs_baseline", "ea_top_cause",
               "fc_dev_mean_rel", "fc_test_mean_rel", "fc_top_feature", "fc_n_series"):
        print(f"{k_:<40} {N[k_]}")
    print(f"\nStep 7 finished in {(time.time() - t_start) / 60:.1f} minutes.")


if __name__ == "__main__":
    main()

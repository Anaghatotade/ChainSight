"""
Step 7 - Demand forecasting: interpretable baselines first, then ONE simple neural network as a challenger.

What happens here (in order):
  1. weekly SKU demand -> feature table, TIME-based split (train 72 wks / dev 16 / test 16)
  2. baselines: Naive, Moving average, Exponential smoothing (+ seasonal naive as a reference)
  3. linear regression, then an MLP (NumPy, from scratch) with the same features
  4. ONE optimising metric (WAPE) + satisficing metrics (RMSE, bias, interpretability)
  5. bias / variance diagnosis, using the best baseline as the "human-level proxy"
  6. error analysis on the 100 biggest dev errors
  7. honest verdict: does the NN beat the baseline? at what cost in interpretability?

Reads  data/processed/*.csv
Writes outputs/tables/forecast_*.csv, outputs/tables/error_analysis_*.csv, outputs/charts/forecast_*.png,
       adds numbers to outputs/tables/key_numbers.json

Run:  python src/07_forecasting.py          (takes ~1-3 minutes)
"""
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
import splits
import viz

BASELINE_NAMES = ["naive", "ma", "ses"]            # the three required baselines
MODEL_LABEL = {"naive": "Naive (last week)", "ma": "Moving average", "ses": "Exp. smoothing",
               "snaive": "Seasonal naive (ref.)", "linear": "Linear regression", "mlp": "MLP (NumPy NN)"}
INTERPRETABLE = {"naive": "Yes - one line", "ma": "Yes - one line", "ses": "Yes - one parameter",
                 "snaive": "Yes - one line", "linear": "Yes - 9 coefficients",
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
    net.fit(Xtr, ytr, Xdev, ydev, epochs=300, batch_size=64, lr=0.003, patience=30)
    return net


def to_units(pred_scaled, scale):
    return np.clip(pred_scaled * scale, 0, None)          # demand cannot be negative


def main():
    cfg.ensure_dirs()
    viz.setup()
    t = kpis.load_clean()
    N = {}
    weekly = kpis.weekly_demand(t)
    sku_kpi = kpis.build_sku_kpis(t)[["sku", "category", "abc_class", "unit_cost", "supplier_code"]]

    # ------------------------------------------------------------------ 1. features + split
    feat = features.build_feature_table(weekly)
    rng_split = splits.validate_split(feat)
    split_rows = feat.groupby("split").agg(rows=("y", "size"), first_week=("week_idx", "min"), last_week=("week_idx", "max"),
                                           mean_weekly_demand=("y", "mean"), promo_week_share=("promo_flag", "mean"),
                                           mean_relative_demand=("y_scaled", "mean")).reindex(["train", "dev", "test"])
    split_rows.to_csv(cfg.TABLES / "forecast_split_summary.csv")
    N["fc_train_rows"], N["fc_dev_rows"], N["fc_test_rows"] = (int(split_rows.loc[s, "rows"]) for s in ("train", "dev", "test"))
    N["fc_dev_mean_rel"], N["fc_test_mean_rel"] = split_rows.loc["dev", "mean_relative_demand"], split_rows.loc["test", "mean_relative_demand"]
    N["fc_dev_promo_share"], N["fc_test_promo_share"] = split_rows.loc["dev", "promo_week_share"], split_rows.loc["test", "promo_week_share"]
    N["fc_n_skus"] = int(feat["sku"].nunique())
    N.update(fc_train_weeks=cfg.TRAIN_WEEKS, fc_dev_start_week=cfg.TRAIN_WEEKS + 1, fc_dev_end_week=cfg.TRAIN_WEEKS + cfg.DEV_WEEKS,
             fc_test_start_week=cfg.TRAIN_WEEKS + cfg.DEV_WEEKS + 1, fc_test_end_week=cfg.TRAIN_WEEKS + cfg.DEV_WEEKS + cfg.TEST_WEEKS,
             fc_n_seeds=len(cfg.NN_SEEDS), fc_bias_limit=cfg.BIAS_LIMIT, fc_min_gain=cfg.MIN_RELATIVE_GAIN, ea_n_target=cfg.N_ERROR_ANALYSIS)

    # ------------------------------------------------------------------ 2. baselines (tuned on DEV only)
    Y, skus = baselines.to_matrix(weekly)
    dev_cols = list(range(cfg.TRAIN_WEEKS, cfg.TRAIN_WEEKS + cfg.DEV_WEEKS))
    k, alpha = baselines.tune_on_dev(Y, dev_cols)
    N["fc_ma_window"], N["fc_ses_alpha"] = k, alpha
    forecasts = {"naive": baselines.naive(Y), "ma": baselines.moving_average(Y, k),
                 "ses": baselines.exp_smoothing(Y, alpha), "snaive": baselines.seasonal_naive(Y)}
    for name, M in forecasts.items():
        feat = feat.merge(baselines.to_long(M, skus, name), on=["sku", "week_idx"], how="left")

    # ------------------------------------------------------------------ 3. linear regression + MLP on scaled features
    tr, dv, te = (feat["split"] == s for s in ("train", "dev", "test"))
    scaler = features.Standardizer().fit(feat.loc[tr, features.FEATURES])       # TRAIN statistics only
    X = scaler.transform(feat[features.FEATURES])
    y = feat["y_scaled"].to_numpy()
    scale = feat["scale"].to_numpy()

    Xb = np.hstack([X, np.ones((len(X), 1))])                                   # linear regression (least squares)
    coef, *_ = np.linalg.lstsq(Xb[tr.to_numpy()], y[tr.to_numpy()], rcond=None)
    feat["linear"] = to_units(Xb @ coef, scale)
    lin_coef = pd.DataFrame({"feature": features.FEATURES + ["intercept"], "standardised_coefficient": coef})
    lin_coef.to_csv(cfg.TABLES / "forecast_linear_coefficients.csv", index=False)

    cand_rows, cand_nets = [], {}
    for name, params in MLP_CANDIDATES.items():
        net = train_mlp(X[tr.to_numpy()], y[tr.to_numpy()], X[dv.to_numpy()], y[dv.to_numpy()], params, seed=cfg.NN_SEEDS[0])
        pred = to_units(net.predict(X[dv.to_numpy()]), scale[dv.to_numpy()])
        cand_rows.append(dict(candidate=name, hidden=str(params["hidden"]), l2=params["l2"], dropout=params["dropout"],
                              best_epoch=net.best_epoch, dev_WAPE=metrics.wape(feat.loc[dv, "y"], pred)))
        cand_nets[name] = net
    cand = pd.DataFrame(cand_rows).sort_values("dev_WAPE").reset_index(drop=True)
    cand.to_csv(cfg.TABLES / "forecast_mlp_candidates_dev.csv", index=False)
    best_name = cand.iloc[0]["candidate"]
    N["fc_mlp_choice"] = best_name
    N["fc_mlp_hidden"] = cand.iloc[0]["hidden"]
    N["fc_mlp_l2"] = float(cand.iloc[0]["l2"])
    N["fc_mlp_dropout"] = float(cand.iloc[0]["dropout"])

    # final MLP: chosen setting, 5 seeds -> report the spread, keep seed-42 as "the" model
    params = MLP_CANDIDATES[best_name]
    seed_rows, main_net = [], None
    for seed in cfg.NN_SEEDS:
        net = cand_nets[best_name] if seed == cfg.NN_SEEDS[0] else train_mlp(X[tr.to_numpy()], y[tr.to_numpy()], X[dv.to_numpy()], y[dv.to_numpy()], params, seed)
        if seed == cfg.NN_SEEDS[0]:
            main_net = net
        row = {"seed": seed, "best_epoch": net.best_epoch}
        for s_name, mask in (("dev", dv), ("test", te)):
            row[f"{s_name}_WAPE"] = metrics.wape(feat.loc[mask, "y"], to_units(net.predict(X[mask.to_numpy()]), scale[mask.to_numpy()]))
        seed_rows.append(row)
    seeds = pd.DataFrame(seed_rows)
    seeds.to_csv(cfg.TABLES / "forecast_mlp_seed_spread.csv", index=False)
    feat["mlp"] = to_units(main_net.predict(X), scale)
    N["fc_mlp_test_wape_min"], N["fc_mlp_test_wape_max"] = seeds["test_WAPE"].min(), seeds["test_WAPE"].max()
    N["fc_mlp_test_wape_mean"] = seeds["test_WAPE"].mean()
    N["fc_mlp_best_epoch"] = main_net.best_epoch
    N["fc_n_parameters"] = int(sum(w.size + b.size for w, b in zip(main_net.W, main_net.b)))

    # independent sanity check: scikit-learn's MLPRegressor with the same architecture (NOT a separate model)
    sk = MLPRegressor(hidden_layer_sizes=params["hidden"], alpha=params["l2"], learning_rate_init=0.003, batch_size=64,
                      max_iter=300, early_stopping=True, n_iter_no_change=30, random_state=cfg.NN_SEEDS[0])
    sk.fit(X[tr.to_numpy()], y[tr.to_numpy()])
    sk_pred = to_units(sk.predict(X[te.to_numpy()]), scale[te.to_numpy()])
    N["fc_sklearn_check_test_wape"] = metrics.wape(feat.loc[te, "y"], sk_pred)

    # ------------------------------------------------------------------ 4. scorecard: optimising + satisficing metrics
    model_cols = ["naive", "ma", "ses", "snaive", "linear", "mlp"]
    rows = []
    for m in model_cols:
        for s_name, mask in (("train", tr), ("dev", dv), ("test", te)):
            sc = metrics.score_all(feat.loc[mask, "y"], feat.loc[mask, m])
            rows.append(dict(model=m, split=s_name, **sc))
    score = pd.DataFrame(rows)
    score.to_csv(cfg.TABLES / "forecast_metrics_long.csv", index=False)
    wide = score.pivot(index="model", columns="split")
    summary = pd.DataFrame({
        "model": [MODEL_LABEL[m] for m in model_cols],
        "model_key": model_cols,
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
    N["fc_best_baseline"] = MODEL_LABEL[best_bl]
    for m in model_cols:
        N[f"fc_wape_dev_{m}"], N[f"fc_wape_test_{m}"] = S.loc[m, "WAPE_dev"], S.loc[m, "WAPE_test"]
        N[f"fc_bias_test_{m}"], N[f"fc_rmse_test_{m}"] = S.loc[m, "Bias_test"], S.loc[m, "RMSE_test"]
    N["fc_wape_train_best_baseline"] = S.loc[best_bl, "WAPE_train"]
    N["fc_wape_train_mlp"], N["fc_wape_train_linear"] = S.loc["mlp", "WAPE_train"], S.loc["linear", "WAPE_train"]

    # decision rule: complexity must earn its place (>= MIN_RELATIVE_GAIN on DEV, then confirmed on TEST)
    choice = best_bl
    for m in ("linear", "mlp"):
        if S.loc[m, "passes_gates"] and S.loc[m, "WAPE_dev"] <= S.loc[choice, "WAPE_dev"] * (1 - cfg.MIN_RELATIVE_GAIN):
            choice = m
    confirmed = S.loc[choice, "WAPE_test"] < S.loc[best_bl, "WAPE_test"] if choice != best_bl else True
    final_model = choice if confirmed else best_bl
    N["fc_final_model"] = MODEL_LABEL[final_model]
    N["fc_final_confirmed_on_test"] = bool(confirmed)

    base_test, mlp_test = S.loc[best_bl, "WAPE_test"], S.loc["mlp", "WAPE_test"]
    rel_gain = (base_test - mlp_test) / base_test
    N["fc_mlp_rel_gain_vs_baseline_test"] = rel_gain
    N["fc_mlp_rel_gain_vs_baseline_dev"] = (S.loc[best_bl, "WAPE_dev"] - S.loc["mlp", "WAPE_dev"]) / S.loc[best_bl, "WAPE_dev"]
    N["fc_linear_rel_gain_vs_baseline_test"] = (base_test - S.loc["linear", "WAPE_test"]) / base_test
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
    diag = {}
    for m in ("mlp", "linear"):
        diag[m] = diagnosis.diagnose(S.loc[best_bl, "WAPE_train"], S.loc[m, "WAPE_train"], S.loc[m, "WAPE_dev"])
    pd.DataFrame(diag).T.to_csv(cfg.TABLES / "forecast_bias_variance_diagnosis.csv")
    N["fc_avoidable_bias_mlp"], N["fc_variance_mlp"] = diag["mlp"]["avoidable_bias"], diag["mlp"]["variance"]
    N["fc_diagnosis_mlp"] = diag["mlp"]["diagnosis"]
    N["fc_avoidable_bias_linear"], N["fc_variance_linear"] = diag["linear"]["avoidable_bias"], diag["linear"]["variance"]

    # ------------------------------------------------------------------ 6. segment view + error analysis (DEV set)
    feat = feat.merge(sku_kpi[["sku", "category", "abc_class", "unit_cost", "supplier_code"]], on="sku", how="left")
    feat["prev8_mean"] = feat["roll_mean_8"] * feat["scale"]
    feat["month_mid"] = (feat["week_start"] + pd.Timedelta(days=3)).dt.month
    seg_rows = []
    for split_name in ("dev", "test"):
        part = feat[feat["split"] == split_name]
        for seg_col in ("category", "abc_class", "promo_flag"):
            for key, g in part.groupby(seg_col):
                seg_rows.append(dict(split=split_name, segment_type=seg_col, segment=key, n_rows=len(g), actual_units=g["y"].sum(),
                                     WAPE_baseline=metrics.wape(g["y"], g[best_bl]), WAPE_mlp=metrics.wape(g["y"], g["mlp"]),
                                     Bias_baseline=metrics.bias(g["y"], g[best_bl]), Bias_mlp=metrics.bias(g["y"], g["mlp"])))
    seg = pd.DataFrame(seg_rows)
    seg["mlp_better"] = seg["WAPE_mlp"] < seg["WAPE_baseline"]
    seg.to_csv(cfg.TABLES / "forecast_segment_wape.csv", index=False)
    test_seg = seg[(seg["split"] == "test") & (seg["segment_type"] == "category")]
    N["fc_categories_mlp_better_test"] = int(test_seg["mlp_better"].sum())
    N["fc_categories_total"] = int(len(test_seg))
    promo_seg = seg[(seg["split"] == "test") & (seg["segment_type"] == "promo_flag")].set_index("segment")
    N["fc_promo_wape_baseline_test"], N["fc_promo_wape_mlp_test"] = promo_seg.loc[1, "WAPE_baseline"], promo_seg.loc[1, "WAPE_mlp"]
    N["fc_nopromo_wape_baseline_test"], N["fc_nopromo_wape_mlp_test"] = promo_seg.loc[0, "WAPE_baseline"], promo_seg.loc[0, "WAPE_mlp"]

    dev_df = feat[feat["split"] == "dev"].copy()
    dev_df = dev_df.rename(columns={"y": "actual", "mlp": "forecast"})
    dev_df["baseline_forecast"] = dev_df[best_bl]
    season_idx = ea.category_season_index(weekly[weekly["week_idx"] < cfg.TRAIN_WEEKS], t["products"])
    tagged = ea.tag_errors(dev_df, season_idx)
    tagged["baseline_abs_error"] = (tagged["baseline_forecast"] - tagged["actual"]).abs()
    top = tagged.sort_values("abs_error", ascending=False).head(cfg.N_ERROR_ANALYSIS).reset_index(drop=True)
    top.insert(0, "rank", np.arange(1, len(top) + 1))
    top["mlp_beats_baseline"] = (top["abs_error"] < top["baseline_abs_error"]).astype(int)
    keep = ["rank", "sku", "category", "abc_class", "week_start", "actual", "forecast", "baseline_forecast", "error", "abs_error",
            "pct_error", "promo_flag", "promo_lag1", "tag_outlier_week", "tag_promo_week", "tag_post_promo_week",
            "tag_seasonal_turn", "primary_cause", "direction", "mlp_beats_baseline"]
    out = top[keep].copy()
    out[["actual", "forecast", "baseline_forecast", "error", "abs_error"]] = out[["actual", "forecast", "baseline_forecast", "error", "abs_error"]].round(1)
    out["pct_error"] = out["pct_error"].round(3)
    out["manual_cause"] = ""          # <- fill in yourself after eyeballing the row
    out["notes"] = ""
    out.to_csv(cfg.TABLES / "error_analysis_top100.csv", index=False)
    tal = ea.tally(top)
    tal.to_csv(cfg.TABLES / "error_analysis_tally.csv", index=False)
    ea.tally_tags(top).to_csv(cfg.TABLES / "error_analysis_tags.csv", index=False)
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
    N["ea_n_skus_in_top"] = int(top["sku"].nunique())
    tags_df = ea.tally_tags(top).set_index("tag")
    N["ea_tag_promo_week_n"] = int(tags_df.loc["promo_week", "n_errors"])
    N["ea_tag_outlier_week_n"] = int(tags_df.loc["outlier_week", "n_errors"])
    N["ea_tag_seasonal_turn_n"] = int(tags_df.loc["seasonal_turn", "n_errors"])
    N["ea_tag_post_promo_n"] = int(tags_df.loc["post_promo_week", "n_errors"])

    # ------------------------------------------------------------------ 7. permutation importance (interpretability trade-off)
    rng = np.random.default_rng(0)
    Xd, yd_raw, sd = X[dv.to_numpy()], feat.loc[dv, "y"].to_numpy(), scale[dv.to_numpy()]
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

    # ------------------------------------------------------------------ 8. what accuracy means for safety stock (indicative)
    te_df = feat[feat["split"] == "test"].merge(
        kpis.build_policy_check(t).groupby("sku", as_index=False)["lead_mean"].mean(), on="sku", how="left")

    def ss_value(col):
        e = (te_df[col] - te_df["y"]).groupby(te_df["sku"]).std()
        lt_w = (te_df.groupby("sku")["lead_mean"].first() / 7).clip(lower=1)
        cost = te_df.groupby("sku")["unit_cost"].first()
        return float((cfg.SERVICE_Z * e * np.sqrt(lt_w) * cost).sum())
    ss_b, ss_m = ss_value(best_bl), ss_value("mlp")
    N["ss_value_baseline"], N["ss_value_mlp"] = ss_b, ss_m
    N["ss_pct_change_mlp_vs_baseline"] = (ss_m - ss_b) / ss_b

    # ------------------------------------------------------------------ save predictions (dashboard-ready)
    pred_cols = ["sku", "category", "abc_class", "week_idx", "week_start", "split", "y", "promo_flag"] + model_cols
    preds = feat[feat["split"].isin(["dev", "test"])][pred_cols].rename(columns={"y": "actual"})
    preds[model_cols] = preds[model_cols].round(1)
    preds.to_csv(cfg.TABLES / "forecast_predictions.csv", index=False)

    # ------------------------------------------------------------------ charts
    # (a) model comparison
    order = ["naive", "ma", "ses", "snaive", "linear", "mlp"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    x = np.arange(len(order)); w = 0.38
    axes[0].bar(x - w / 2, [S.loc[m, "WAPE_dev"] for m in order], w, label="Dev", color=viz.PALETTE["grey"])
    axes[0].bar(x + w / 2, [S.loc[m, "WAPE_test"] for m in order], w, label="Test", color=viz.PALETTE["main"])
    axes[0].set_xticks(x); axes[0].set_xticklabels([wrap_label(m) for m in order], fontsize=8)
    viz.pct_axis(axes[0]); axes[0].set_title("Forecast error (WAPE) - lower is better"); axes[0].legend()
    for i, m in enumerate(order):
        axes[0].text(i + w / 2, S.loc[m, "WAPE_test"] + 0.003, f"{S.loc[m, 'WAPE_test']:.1%}", ha="center", fontsize=8)
    axes[1].bar(x, [S.loc[m, "Bias_test"] for m in order], color=[viz.PALETTE["good"] if abs(S.loc[m, "Bias_test"]) <= cfg.BIAS_LIMIT else viz.PALETTE["bad"] for m in order])
    axes[1].axhline(cfg.BIAS_LIMIT, color="black", ls="--", lw=1); axes[1].axhline(-cfg.BIAS_LIMIT, color="black", ls="--", lw=1)
    axes[1].set_xticks(x); axes[1].set_xticklabels([wrap_label(m) for m in order], fontsize=8)
    viz.pct_axis(axes[1]); axes[1].set_title(f"Bias on test (limit +/-{cfg.BIAS_LIMIT:.0%}): + over, - under-forecast", fontsize=11)
    viz.save(fig, "forecast_01_model_comparison")

    # (b) learning curve
    h = main_net.history
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(h["train_loss"], label="Train loss", color=viz.PALETTE["main"])
    ax.plot(h["dev_loss"], label="Dev loss", color=viz.PALETTE["accent"])
    ax.axvline(main_net.best_epoch - 1, color="black", ls="--", lw=1, label=f"best epoch ({main_net.best_epoch})")
    ax.set_xlabel("Epoch"); ax.set_ylabel("MSE loss (relative demand)"); ax.set_title("MLP learning curve (early stopping on dev)")
    ax.legend()
    viz.save(fig, "forecast_02_learning_curve")

    # (c) actual vs forecast for 4 SKUs on dev+test
    pick = []
    top_a = sku_kpi.merge(feat.groupby("sku", as_index=False)["y"].sum(), on="sku").sort_values("y", ascending=False)
    pick += list(top_a["sku"].head(2))
    cvs = kpis.build_sku_kpis(t).set_index("sku")["demand_cv"]
    pick.append(cvs.drop(pick).idxmax())
    promo_heavy = feat[feat["split"] != "train"].groupby("sku")["promo_flag"].sum().drop(pick).idxmax()
    pick.append(promo_heavy)
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharex=False)
    for ax, s in zip(axes.ravel(), pick):
        g = feat[(feat["sku"] == s) & (feat["split"] != "train")].sort_values("week_idx")
        ax.plot(g["week_start"], g["y"], color="black", lw=2, label="Actual")
        ax.plot(g["week_start"], g[best_bl], color=viz.PALETTE["grey"], lw=1.5, label=MODEL_LABEL[best_bl])
        ax.plot(g["week_start"], g["mlp"], color=viz.PALETTE["accent"], lw=1.8, label="MLP")
        ax.scatter(g.loc[g["promo_flag"] == 1, "week_start"], g.loc[g["promo_flag"] == 1, "y"], color=viz.PALETTE["bad"], zorder=5, s=25, label="Promo week")
        ax.axvline(feat.loc[feat["split"] == "test", "week_start"].min(), color="grey", ls=":")
        ax.set_title(f"{s}  ({g['category'].iloc[0]}, class {g['abc_class'].iloc[0]})", fontsize=10); ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Weekly demand: actual vs forecasts (dev | test, dotted line = start of test)", fontweight="bold")
    viz.save(fig, "forecast_03_actual_vs_forecast")

    # (d) error analysis
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    tt = tal.set_index("primary_cause").reindex(ea.CAUSE_ORDER)
    axes[0].barh([c.replace("_", " ") for c in tt.index], tt["n_errors"], color=viz.PALETTE["main"])
    axes[0].invert_yaxis(); axes[0].set_title(f"Top {len(top)} dev errors by primary cause"); axes[0].set_xlabel("Number of errors")
    bc = by_cat.sort_values("n_errors")
    axes[1].barh(bc.index, bc["n_errors"], color=viz.PALETTE["accent"]); axes[1].set_title("... by category"); axes[1].set_xlabel("Number of errors")
    over = (top["direction"] == "over-forecast").sum()
    axes[2].bar(["Over-forecast", "Under-forecast"], [over, len(top) - over], color=[viz.PALETTE["grey"], viz.PALETTE["bad"]])
    axes[2].set_title("... by direction (under = stockout risk)")
    viz.save(fig, "forecast_04_error_analysis")

    # (e) seed spread
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar(seeds["seed"].astype(str), seeds["test_WAPE"], color=viz.PALETTE["accent"], label="MLP (test WAPE)")
    ax.axhline(base_test, color=viz.PALETTE["main"], lw=2, label=f"Best baseline: {MODEL_LABEL[best_bl]}")
    ax.set_ylim(min(seeds["test_WAPE"].min(), base_test) * 0.9, max(seeds["test_WAPE"].max(), base_test) * 1.05)
    viz.pct_axis(ax); ax.set_xlabel("Random seed"); ax.set_title("MLP result depends a little on the random seed"); ax.legend()
    viz.save(fig, "forecast_05_seed_spread")

    # (f) interpretability: linear coefficients vs permutation importance
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    lc = lin_coef[lin_coef["feature"] != "intercept"].sort_values("standardised_coefficient")
    axes[0].barh(lc["feature"], lc["standardised_coefficient"], color=viz.PALETTE["main"]); axes[0].set_title("Linear regression: standardised coefficients")
    im = imp.sort_values("wape_increase")
    axes[1].barh(im["feature"], im["wape_increase"], color=viz.PALETTE["accent"]); axes[1].set_title("MLP: permutation importance (WAPE increase on dev)")
    viz.save(fig, "forecast_06_interpretability")

    nums.save(N)
    print(summary[["model", "WAPE_train", "WAPE_dev", "WAPE_test", "Bias_test", "passes_gates"]].round(4).to_string(index=False))
    print()
    print(cand.to_string(index=False)); print(seeds.round(4).to_string(index=False))
    print(tal.round(3).to_string(index=False))
    for k_ in ("fc_best_baseline", "fc_final_model", "fc_verdict", "fc_mlp_rel_gain_vs_baseline_test", "fc_avoidable_bias_mlp", "fc_variance_mlp",
               "fc_sklearn_check_test_wape", "ss_pct_change_mlp_vs_baseline", "ea_top_cause", "fc_dev_mean_rel", "fc_test_mean_rel"):
        print(f"{k_:<36} {N[k_]}")


if __name__ == "__main__":
    main()

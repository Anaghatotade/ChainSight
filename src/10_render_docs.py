"""
Step 10 - write README.md and INTERVIEW_NOTES.md from templates + the real pipeline outputs.

Why: the rule of this project is "no hard-coded claims". The templates in docs/templates/ contain
placeholders like {{kpi_fill_rate:pct1}}; this script fills them from outputs/tables/key_numbers.json
and the CSV tables. If a placeholder has no value the script STOPS with an error - so the docs can never
quietly show a stale or invented number.

Placeholder syntax
  {{key}}            raw value          {{key:pct1}}  0.2503 -> 25.0%      {{key:pct0}} -> 25%
  {{key:usd}}        $187.36M / $720K    {{key:int}}   65,596,652            {{key:f1}} / f2 / f3 decimals
  {{key:x2}}         1.23x
  {{@table:name}}    markdown table from outputs/tables/<name>.csv (optionally {{@table:name|col1,col2}})
  {{@file:path}}     paste a text file (e.g. outputs/recommendations.md)

Run:  python src/10_render_docs.py
"""
import re

import pandas as pd

import config as cfg
import keynums as nums

BASELINE_KEY = {"Naive (last week)": "naive", "Moving average": "ma", "Exp. smoothing": "ses"}


def usd(x):
    x = float(x)
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K"


FORMATS = {
    "pct0": lambda v: f"{float(v) * 100:.0f}%", "pct1": lambda v: f"{float(v) * 100:.1f}%", "pct2": lambda v: f"{float(v) * 100:.2f}%",
    "usd": usd, "int": lambda v: f"{int(round(float(v))):,}",
    "f1": lambda v: f"{float(v):.1f}", "f2": lambda v: f"{float(v):.2f}", "f3": lambda v: f"{float(v):.3f}",
    "x2": lambda v: f"{float(v):.2f}x", "pp1": lambda v: f"{float(v) * 100:.1f} pp",
}


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def table_block(name, cols=None):
    """CSV -> markdown table; columns whose name hints at a ratio/money get % or $ formatting."""
    df = pd.read_csv(cfg.TABLES / f"{name}.csv")
    if cols:
        df = df[[c.strip() for c in cols.split(",")]]
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind == "f" and out[c].dropna().map(float.is_integer).all() and not any(h in c.lower() for h in ("rate", "share", "pct", "wape", "bias")):
            out[c] = out[c].map(lambda v: "" if pd.isna(v) else f"{int(v):,}")           # whole numbers (counts) print without decimals
        elif out[c].dtype.kind in "iu":
            out[c] = out[c].map(lambda v: f"{v:,}" if abs(v) >= 10000 else str(v))      # 30490 -> 30,490 (but years stay 2012)
        elif out[c].dtype.kind == "f":
            low = c.lower()
            if any(h in c for h in ("WAPE", "Bias")) or any(h in low for h in ("rate", "share", "pct")):
                out[c] = out[c].map(lambda v: "" if pd.isna(v) else f"{v * 100:.1f}%")
            elif any(h in low for h in ("revenue", "value", "freight")):
                out[c] = out[c].map(lambda v: "" if pd.isna(v) else f"${v:,.0f}")
            else:
                out[c] = out[c].map(lambda v: "" if pd.isna(v) else f"{v:,.2f}")
        elif out[c].dtype == bool:
            out[c] = out[c].map({True: "yes", False: "no"})
    return md_table(out)


def derived_text(N):
    """Sentences whose WORDING depends on the numbers (up/down, wins/loses). All decided by code."""
    P = {}
    P["fc_min_gain_pct"] = f"{cfg.MIN_RELATIVE_GAIN * 100:.0f}%"
    P["abc_a_cut_pct"], P["abc_b_cut_pct"] = f"{cfg.ABC_A_CUTOFF * 100:.0f}%", f"{(cfg.ABC_B_CUTOFF - cfg.ABC_A_CUTOFF) * 100:.0f}%"
    lfl = N["eda_lfl_growth_total"]
    P["growth_phrase"] = (f"Total weekly revenue grew {N['eda_rev_per_week_growth_total'] * 100:.0f}% between {N['eda_first_full_year']} and {N['eda_last_full_year']}, "
                          f"but the number of item-store series on sale grew {(N['eda_assortment_growth'] - 1) * 100:.0f}%, so revenue per on-sale series "
                          + ("fell" if lfl < 0 else "rose") + f" {abs(lfl) * 100:.0f}%. "
                          + ("Growth is consistent with a wider assortment rather than each item selling more (new items also tend to be smaller sellers, which on its own lowers the per-series average)."
                             if lfl < 0 else "Each series also sold more, not just the assortment."))
    P["data_n_days_raw"] = N["data_n_days"] + N["dq_dropped_days"]
    bl = N["fc_best_baseline"]
    bk = BASELINE_KEY[bl]
    P["bl_wape_dev"], P["bl_wape_test"] = N[f"fc_wape_dev_{bk}"], N[f"fc_wape_test_{bk}"]
    P["bl_bias_test"] = N[f"fc_bias_test_{bk}"]
    gain, vs_lin, lin_gain, thr = (N["fc_mlp_rel_gain_vs_baseline_test"], N["fc_mlp_rel_gain_vs_linear_test"],
                                   N["fc_linear_rel_gain_vs_baseline_test"], cfg.MIN_RELATIVE_GAIN)
    v = N["fc_verdict"]
    seeds = ("even its worst random seed beats the baseline" if N["fc_mlp_worst_seed_beats_baseline"]
             else "but its worst random seed does not beat the baseline")
    if v == "NN_WINS":
        head = (f"The MLP beats the best baseline ({bl}) on the untouched test weeks: WAPE {N['fc_wape_test_mlp'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}% "
                f"({gain * 100:.1f}% relative improvement, and {seeds}).")
    elif v == "MARGINAL":
        head = (f"The MLP is only marginally better than the best baseline ({bl}) on test: WAPE {N['fc_wape_test_mlp'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}% "
                f"({gain * 100:.1f}% relative, {seeds}) - below the {thr * 100:.0f}% bar we set before looking at test.")
    else:
        head = (f"The MLP does NOT beat the best baseline ({bl}) on test: WAPE {N['fc_wape_test_mlp'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}%. "
                "The baseline is the final answer.")
    if lin_gain > 0:
        lin_s = (f" Plain linear regression with the same features gets {N['fc_wape_test_linear'] * 100:.1f}% ({lin_gain * 100:.1f}% better than the baseline); "
                 f"the hidden layers add {vs_lin * 100:.1f}% on top of that.")
    else:
        lin_s = (f" Linear regression with the same features is worse than the baseline ({N['fc_wape_test_linear'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}%): "
                 "the extra features alone do not help, only the non-linear model gets a small gain.")
    P["verdict_text"] = head + lin_s
    P["final_text"] = (f"**Final model: {N['fc_final_model']}.** " +
                       ("It earned its place on the dev set and was confirmed on test." if N["fc_final_model_key"] != bk and N["fc_final_confirmed_on_test"]
                        else f"Nothing more complex beat it by the required {thr * 100:.0f}% on dev, so the simple baseline stays."))
    P["interp_text"] = (f"The linear model is read straight from its {N['fc_n_features']} coefficients; the MLP has "
                        f"{N['fc_n_parameters']:,} weights and can only be explained indirectly (permutation importance: "
                        f"'{N['fc_top_feature']}' matters most, then '{N['fc_second_feature']}').")
    P["seasonality_vs_lag"] = (f"The seasonal-naive reference (same week last year) scores {N['fc_wape_test_snaive'] * 100:.1f}% on test, "
                               + ("far worse than the simple baselines: here recent weeks carry much more information than the same week a year ago "
                                  f"(the 52-week lag ranks {N['fc_lag52_importance_rank']} of {N['fc_n_features']} in the MLP's permutation importance)."
                                  if N["fc_wape_test_snaive"] > P["bl_wape_test"] else "better than the simple baselines, so yearly seasonality is strong."))
    P["gate_text"] = (f"passes both satisficing gates (|bias| <= {cfg.BIAS_LIMIT * 100:.0f}% and RMSE no worse than naive)"
                      if N["fc_mlp_bias_ok"] and N["fc_passes_gates_mlp"] else "fails a satisficing gate")
    P["dist_text"] = (f"Dev and test are consecutive recent blocks, but not identical: mean relative demand is {N['fc_dev_mean_rel']:.2f} on dev vs "
                      f"{N['fc_test_mean_rel']:.2f} on test (demand trends upward); price-cut weeks are {N['fc_dev_pricecut_share'] * 100:.1f}% of dev rows vs "
                      f"{N['fc_test_pricecut_share'] * 100:.1f}% of test rows.")
    P["ea_text"] = (f"The largest bucket is '{N['ea_top_cause'].replace('_', ' ')}' with {N['ea_top_cause_n']} of the top {N['ea_top_n']} errors ({N['ea_top_cause_share'] * 100:.0f}%). "
                    f"But that tag is true for {N['ea_tag_outlier_week_base'] * 100:.0f}% of ALL dev rows, so among the big errors it is only {N['ea_tag_outlier_week_lift']:.1f}x as common as normal; "
                    f"price-cut weeks are {N['ea_tag_price_cut_week_lift']:.1f}x over-represented (but only {N['ea_tag_price_cut_week_n']} rows). "
                    f"{N['ea_under_forecast_share'] * 100:.0f}% of the big errors are under-forecasts.")
    P["ea_sowhat"] = ("the largest errors are weeks in which demand moved far from the previous 8-week level, and the calendar and price tags explain few of them. "
                      "A lag-based model cannot see such jumps coming; the next step is to read these rows one by one (the `manual_cause` column) for causes the data cannot show, "
                      "such as an item's own stock-out or a launch - not to build a bigger network."
                      if N["ea_top_cause"] == "outlier_week" else
                      f"fix the largest bucket first ({N['ea_top_cause'].replace('_', ' ')}) with a targeted feature or rule, not a bigger network.")
    ch = N["sim_mlp_inventory_change_vs_baseline"]
    P["sim_text"] = f"{abs(ch) * 100:.1f}% {'less' if ch < 0 else 'more'} inventory"
    P["pcu_cut_ratio_pct"] = f"{cfg.PRICE_CUT_RATIO * 100:.0f}%"
    P["sim_inv_baseline"] = N[f"sim_inv_at_target_{bk}"]
    P["pcu_phrase"] = ("a typical price-cut week sells more than the item's recent level"
                       if N["kpi_pcu_cut_median_ratio"] > N["kpi_pcu_normal_median_ratio"] * 1.05 else "price-cut weeks look much like normal weeks")
    P["snap_phrase"] = ("clearly" if N["eda_snap_foods_max_ratio"] >= 1.15 else "modestly")
    return P


def render(template, values):
    def repl(m):
        token = m.group(1).strip()
        if token.startswith("@table:"):
            name, _, cols = token[len("@table:"):].partition("|")
            return table_block(name.strip(), cols or None)
        if token.startswith("@file:"):
            return (cfg.ROOT / token[len("@file:"):].strip()).read_text(encoding="utf-8")
        key, _, fmt = token.partition(":")
        if key not in values or values[key] is None:
            raise KeyError(f"No value for placeholder {{{{{token}}}}}")
        v = values[key]
        return FORMATS[fmt](v) if fmt else str(v)
    return re.sub(r"\{\{(.+?)\}\}", repl, template)


def main():
    N = nums.load()
    values = {**N, **derived_text(N)}
    tdir = cfg.DOCS / "templates"
    for src, dst in (("README.template.md", "README.md"), ("INTERVIEW_NOTES.template.md", "INTERVIEW_NOTES.md")):
        text = render((tdir / src).read_text(encoding="utf-8"), values)
        (cfg.ROOT / dst).write_text(text, encoding="utf-8")
        print("Wrote", dst, f"({len(text):,} characters)")


if __name__ == "__main__":
    main()

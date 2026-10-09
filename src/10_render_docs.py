"""
Step 10 - write README.md and INTERVIEW_NOTES.md from templates + the real pipeline outputs.

Why: the rule of this project is "no hard-coded claims". The templates in docs/templates/ contain
placeholders like {{kpi_fill_rate:pct1}}; this script fills them from outputs/tables/key_numbers.json
and the CSV tables. If a placeholder has no value the script STOPS with an error - so the docs can never
quietly show a stale or invented number.

Placeholder syntax
  {{key}}            raw value          {{key:pct1}}  0.8557 -> 85.6%      {{key:pct0}} -> 86%
  {{key:usd}}        $61.51M / $720K    {{key:int}}   3,265,338            {{key:f1}} / f2 / f3 decimals
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
        if out[c].dtype.kind == "f":
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
    P["fill_trend"] = "fell" if N["kpi_fill_last_3m"] < N["kpi_fill_first_3m"] else "rose"
    P["abc_service_phrase"] = ("nearly identical across A, B and C items (the policy ignores how important an item is)"
                               if N["rec_abc_fill_spread_pp"] < 2 else "different across A, B and C items")
    P["doi_phrase"] = ("SKUs holding fewer days of stock have clearly lower fill rates" if N["kpi_corr_doi_fill"] > 0.3
                       else "days of inventory and fill rate are only weakly related")
    P["policy_phrase"] = ("SKU-warehouses whose reorder point is below the recommended level stock out far more often"
                          if N["pol_stockout_under"] > 2 * N["pol_stockout_ok"] else "the policy gap explains only part of the stockouts")
    P["promo_phrase"] = "Promotions are a real demand driver" if N["eda_promo_ratio"] > 1.1 else "Promotions have only a small effect"
    bl = N["fc_best_baseline"]
    bk = BASELINE_KEY[bl]
    P["bl_wape_dev"], P["bl_wape_test"] = N[f"fc_wape_dev_{bk}"], N[f"fc_wape_test_{bk}"]
    gain, vs_lin, lin_gain, thr = (N["fc_mlp_rel_gain_vs_baseline_test"], N["fc_mlp_rel_gain_vs_linear_test"],
                                   N["fc_linear_rel_gain_vs_baseline_test"], cfg.MIN_RELATIVE_GAIN)
    v = N["fc_verdict"]
    if v == "NN_WINS":
        head = (f"The MLP beats the best baseline ({bl}) on the untouched test weeks: WAPE {N['fc_wape_test_mlp'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}% "
                f"({gain * 100:.1f}% relative improvement, and even its worst random seed beats the baseline).")
    elif v == "MARGINAL":
        head = (f"The MLP is only marginally better than the best baseline ({bl}) on test: WAPE {N['fc_wape_test_mlp'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}% "
                f"({gain * 100:.1f}% relative) - below the {thr * 100:.0f}% bar or not stable across seeds.")
    else:
        head = (f"The MLP does NOT beat the best baseline ({bl}) on test: WAPE {N['fc_wape_test_mlp'] * 100:.1f}% vs {P['bl_wape_test'] * 100:.1f}%. "
                "The baseline is the final answer.")
    if lin_gain > 0:
        lin_s = (f" But plain linear regression with the same features already gets {N['fc_wape_test_linear'] * 100:.1f}% ({lin_gain * 100:.1f}% better than the baseline); "
                 f"the hidden layers add only {vs_lin * 100:.1f}% on top of that"
                 + (" - below the bar, so the extra complexity is not justified." if vs_lin < thr else " - above the bar."))
    else:
        lin_s = " Linear regression with the same features does not beat the baseline either."
    P["verdict_text"] = head + lin_s
    P["final_text"] = (f"**Final model: {N['fc_final_model']}.** " +
                       ("It earned its place on the dev set and was confirmed on test." if N["fc_final_model"] != bl and N["fc_final_confirmed_on_test"]
                        else f"Nothing more complex beat it by the required {thr * 100:.0f}% on dev, so the simple baseline stays."))
    P["interp_text"] = ("The linear model is read straight from its 9 coefficients; the MLP has "
                        f"{N['fc_n_parameters']:,} weights and can only be explained indirectly (permutation importance: "
                        f"'{N['fc_top_feature']}' matters most, then '{N['fc_second_feature']}').")
    P["seasonality_vs_lag"] = (f"The seasonal-naive reference (same week last year) scores {N['fc_wape_test_snaive'] * 100:.1f}% on test, "
                               + ("worse than the simple baselines: in this data recent weeks carry more information than the same week a year ago."
                                  if N["fc_wape_test_snaive"] > P["bl_wape_test"] else "better than the simple baselines, so yearly seasonality is strong."))
    P["gate_text"] = (f"passes both satisficing gates (|bias| <= {cfg.BIAS_LIMIT * 100:.0f}% and RMSE no worse than naive)"
                      if N["fc_mlp_bias_ok"] else "fails the bias gate")
    P["dist_text"] = (f"Dev and test are consecutive recent blocks of the same process, but not identical: mean relative demand is {N['fc_dev_mean_rel']:.2f} on dev vs "
                      f"{N['fc_test_mean_rel']:.2f} on test (demand trends upward), promo-week share {N['fc_dev_promo_share'] * 100:.1f}% vs {N['fc_test_promo_share'] * 100:.1f}%.")
    P["ea_text"] = (f"The largest bucket is '{N['ea_top_cause'].replace('_', ' ')}' with {N['ea_top_cause_n']} of the top {N['ea_top_n']} errors ({N['ea_top_cause_share'] * 100:.0f}%). "
                    f"{N['ea_under_forecast_share'] * 100:.0f}% of these big errors are under-forecasts (stockout risk).")
    P["ea_sowhat"] = ("most of the biggest errors have none of our simple causes (promo, outlier, seasonal turn): they look like noise or missing information, "
                      "so a bigger network is unlikely to help - review the rows manually and look for new features (price, weather, customer orders)."
                      if N["ea_top_cause"] == "no_clear_cause" else
                      f"fix the largest bucket first ({N['ea_top_cause'].replace('_', ' ')}) with a targeted feature or rule, not a bigger network.")
    P["ss_text"] = f"{'lower' if N['ss_pct_change_mlp_vs_baseline'] < 0 else 'higher'} by {abs(N['ss_pct_change_mlp_vs_baseline']) * 100:.1f}%"
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

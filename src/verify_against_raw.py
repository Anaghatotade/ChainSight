"""
Independent check - does the pipeline's revenue match a from-scratch recomputation on the RAW files?

The pipeline works on NumPy matrices (panel.py). Here we recompute units and revenue per store a completely different way
(melt the wide sales table to long format, merge calendar and prices with pandas) using none of the cleaning code, and compare.
If a single store differs by more than half a cent per million dollars the script stops with an error.

Reads  data/raw/*, data/processed/panel.npz
Writes outputs/tables/verification_store_revenue.csv, adds verify_* numbers to key_numbers.json

Run:  python src/verify_against_raw.py          (about 1-2 minutes; run after step 02)
"""
import numpy as np
import pandas as pd

import config as cfg
import keynums as nums
import panel as pn


def independent_store_totals(raw, n_days):
    """units and revenue per store from raw long-format data (no project code involved)."""
    cal = raw["calendar"]
    cal = cal[cal["d"].str[2:].astype(int) <= n_days][["d", "wm_yr_wk"]]
    prices = raw["prices"]
    dcols = [f"d_{i}" for i in range(1, n_days + 1)]
    out = {}
    for store, g in raw["sales"].groupby("store_id"):
        long = g.melt(id_vars=["item_id"], value_vars=dcols, var_name="d", value_name="units")
        long = long.merge(cal, on="d").merge(prices[prices["store_id"] == store][["item_id", "wm_yr_wk", "sell_price"]],
                                              on=["item_id", "wm_yr_wk"], how="left")
        out[store] = dict(indep_units=int(long["units"].sum()),
                          indep_revenue=float((long["units"] * long["sell_price"].fillna(0)).sum()),
                          units_without_price=int(long.loc[long["sell_price"].isna(), "units"].sum()))
    return pd.DataFrame(out).T


def main():
    cfg.ensure_dirs()
    raw = pn.load_raw()
    panel = pn.load_panel()
    n_days = panel.n_weeks * 7
    ind = independent_store_totals(raw, n_days)
    stores = panel.series["store_id"].to_numpy()
    mine = pd.DataFrame({"pipeline_units": panel.units.sum(axis=1), "pipeline_revenue": panel.revenue().sum(axis=1), "store_id": stores}) \
        .groupby("store_id").sum()
    cmp_ = ind.join(mine)
    cmp_["revenue_abs_diff"] = (cmp_["indep_revenue"] - cmp_["pipeline_revenue"]).abs()
    cmp_["units_match"] = cmp_["indep_units"] == cmp_["pipeline_units"]
    cmp_.round(2).reset_index(names="store_id").to_csv(cfg.TABLES / "verification_store_revenue.csv", index=False)
    print(cmp_.round(2).to_string())
    total_rel = float(cmp_["revenue_abs_diff"].sum() / cmp_["indep_revenue"].sum())
    nums.save({"verify_n_stores": len(cmp_), "verify_all_units_match": bool(cmp_["units_match"].all()),
               "verify_max_store_revenue_diff": float(cmp_["revenue_abs_diff"].max()), "verify_total_revenue": float(cmp_["indep_revenue"].sum()),
               "verify_units_without_price": int(cmp_["units_without_price"].sum())})
    if not cmp_["units_match"].all() or total_rel > 5e-9 or cmp_["units_without_price"].sum() != 0:
        raise SystemExit("VERIFICATION FAILED - pipeline and independent recomputation disagree (see table above)")
    print(f"\nOK - {len(cmp_)} stores: units identical, revenue identical to the cent (max diff ${cmp_['revenue_abs_diff'].max():.6f}).")


if __name__ == "__main__":
    main()

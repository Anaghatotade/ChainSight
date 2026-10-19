"""
policy_sim.py - what does forecast accuracy mean for inventory? (a SIMULATION on REAL demand with ASSUMED lead time)

The M5 data has no inventory or lead times, so this is NOT a measurement of what Walmart's stock did. It answers a
what-if question: "if a regional DC replenished each item with a weekly periodic-review order-up-to policy that uses
forecast X, how much stock would it need to hold to reach a given fill rate on the real test-period demand?"

Assumptions (config.py, all labelled in the outputs):
  * review period R = 1 week, lead time L = 1 week (ASSUMED)
  * order-up-to level for week t:  S_t = (L + R) * forecast_t + z * sigma_e * sqrt(L + R)
        sigma_e = standard deviation of that model's forecast errors on the DEV weeks (never the test weeks)
  * unmet demand is lost (no backorders); the DC starts the test period fully stocked to S_0
  * stock is valued at retail price (the data has no cost)
Weekly buckets hide within-week timing, and a zero-sales week is not necessarily a stockout - so treat results as relative
(model A vs model B), not absolute.
"""
import numpy as np
import pandas as pd

import config as cfg


def simulate(actual, forecast, sigma, price, z, lead=None, review=None):
    """
    actual, forecast, price: [n_series, n_weeks]; sigma: [n_series]. Returns dict of totals.
    Week t: stock on hand = leftover + order that arrives now; demand is served; then (at the review) an order is placed
    to raise the inventory position (on hand + on order) to S_t; it arrives `lead` weeks later.
    """
    L = cfg.ASSUMED_LEAD_TIME_WEEKS if lead is None else lead
    R = cfg.REVIEW_PERIOD_WEEKS if review is None else review
    n, T = actual.shape
    P = L + R
    target = P * forecast + z * sigma[:, None] * np.sqrt(P)           # S_t for every week
    on_hand = target[:, 0].copy()                                      # start fully stocked
    pipeline = np.zeros((n, T + L + 1))
    served_tot = demand_tot = lost_value = inv_value = 0.0
    stockout_weeks = 0
    for t in range(T):
        on_hand = on_hand + pipeline[:, t]                             # arrivals at the start of week t
        d = actual[:, t]
        served = np.minimum(on_hand, d)
        on_hand = on_hand - served
        served_tot += served.sum(); demand_tot += d.sum()
        lost_value += ((d - served) * price[:, t]).sum()
        inv_value += (on_hand * price[:, t]).sum()                     # end-of-week stock, retail value
        stockout_weeks += int((d - served > 1e-9).sum())
        position = on_hand + pipeline[:, t + 1:t + L + 1].sum(axis=1) if L > 0 else on_hand
        order = np.maximum(0.0, target[:, min(t + 1, T - 1)] - position)    # decided with next week's forecast
        pipeline[:, t + 1 + L] += order
    return dict(fill_rate=served_tot / demand_tot, avg_inventory_value=inv_value / T,
                lost_revenue=lost_value, stockout_week_share=stockout_weeks / (n * T))


def frontier(actual, forecasts, sigmas, price, z_grid=cfg.Z_GRID):
    """For every model and every safety factor z: fill rate and average inventory value."""
    rows = []
    for name, f in forecasts.items():
        for z in z_grid:
            r = simulate(actual, f, sigmas[name], price, z)
            rows.append(dict(model=name, z=z, **r))
    return pd.DataFrame(rows)


def inventory_at_target(front, target=cfg.FILL_RATE_TARGET):
    """Average inventory value needed to reach the target fill rate (linear interpolation between grid points)."""
    out = {}
    for name, g in front.groupby("model"):
        g = g.sort_values("z")
        fr, inv = g["fill_rate"].to_numpy(), g["avg_inventory_value"].to_numpy()
        if fr.max() < target or fr.min() > target:
            out[name] = np.nan                                         # target not reached inside the grid
        else:
            out[name] = float(np.interp(target, fr, inv))              # fill rate increases with z
    return out

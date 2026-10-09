"""
datagen.py - synthetic supply-chain data generator.

REUSED from the original ChainSight project (backend/app/etl/generate_synthetic_data.py):
  * the day-by-day simulation per (SKU, warehouse): demand -> inventory -> purchase orders
  * the periodic-review (weekly) reorder-point / order-up-to policy
  * supplier lead-time + reliability logic

CHANGED on purpose:
  * fully reproducible: fixed start date (not date.today()) and ONE seeded RNG
  * 2 years of history (needed for seasonality + a proper train/dev/test split)
  * promo windows are recorded as a flag (needed as a forecasting feature)
  * each product category has its own seasonal phase (so seasonality differs by category)
  * the inventory policy is set ONCE from the first 13 weeks (planners rarely re-tune it)
  * shipping mode affects lead time / freight cost (so lead-time analysis is meaningful)
  * a *separate* function injects realistic data-quality problems, so the cleaning step
    has real work to do. The injected problems are random and are documented in the README.

IMPORTANT: this is SYNTHETIC data. Findings describe what the analysis method finds in
data with these mechanisms - they are not claims about a real company.
"""
import math

import numpy as np
import pandas as pd

import config as cfg

# ----------------------------------------------------------------------------- lookup lists
CATEGORIES = ["Electronics", "Packaging", "Raw Materials", "Textiles", "Machinery Parts", "Chemicals"]
SUB_CATEGORIES = {
    "Electronics": ["Sensors", "Circuit Boards", "Connectors", "Displays"],
    "Packaging": ["Cartons", "Pallets", "Labels", "Wrap Film"],
    "Raw Materials": ["Steel Coil", "Aluminum Sheet", "Resin Pellets"],
    "Textiles": ["Cotton Fabric", "Synthetic Fiber", "Zippers"],
    "Machinery Parts": ["Bearings", "Motors", "Gearboxes", "Valves"],
    "Chemicals": ["Adhesives", "Coatings", "Solvents"],
}
# each category peaks in a different part of the year (phase shift of the yearly sine wave)
CATEGORY_PHASE = {
    "Electronics": 4.2,
    "Packaging": 4.0,
    "Raw Materials": 1.5,
    "Textiles": 3.0,
    "Machinery Parts": 0.0,
    "Chemicals": 2.2,
}
REGION_COUNTRIES = {
    "North America": ["USA", "Mexico", "Canada"],
    "Europe": ["Germany", "Poland", "Italy", "Netherlands"],
    "East Asia": ["China", "Vietnam", "South Korea", "Taiwan"],
    "South Asia": ["India", "Bangladesh"],
    "Latin America": ["Brazil", "Colombia"],
}
WAREHOUSES = [
    ("WH-EAST", "East Distribution Center", "North America", 500000),
    ("WH-WEST", "West Coast Fulfillment Hub", "North America", 420000),
    ("WH-EU", "European Central Warehouse", "Europe", 380000),
    ("WH-APAC", "APAC Regional Hub", "East Asia", 450000),
    ("WH-SOUTH", "Southern Logistics Center", "Latin America", 260000),
]
# shipping mode -> (lead-time multiplier vs. road, freight cost as share of goods value)
MODE_LEAD_FACTOR = {"air": 0.45, "road": 1.0, "rail": 1.1, "ocean": 1.35}
MODE_FREIGHT_RATE = {"air": 0.12, "road": 0.06, "rail": 0.05, "ocean": 0.04}
ADJECTIVES = ["Apex", "Summit", "Pioneer", "Vertex", "Zenith", "Meridian", "Atlas", "Nova", "Orion",
              "Titan", "Crest", "Horizon", "Prime", "Vanguard", "Cobalt", "Ember", "Falcon", "Granite",
              "Harbor", "Ironwood", "Juniper", "Keystone", "Lumen", "Mosaic"]
NOUNS = ["Industrial", "Global", "Dynamics", "Systems", "Works", "Supply", "Trading", "Materials",
         "Components", "Logistics", "Partners", "Manufacturing"]
PRODUCT_SUFFIX = ["Pro", "X", "Std", "Plus", "Lite"]


# ----------------------------------------------------------------------------- master data
def make_suppliers(rng, n):
    rows = []
    for i in range(n):
        category = CATEGORIES[i % len(CATEGORIES)]          # 4 suppliers per category
        region = str(rng.choice(list(REGION_COUNTRIES)))
        country = str(rng.choice(REGION_COUNTRIES[region]))
        lead_mean = float(np.clip(rng.normal(8 if region == "North America" else 18, 5), 3, 45))
        rows.append(dict(
            supplier_code=f"SUP-{i + 1:03d}",
            supplier_name=f"{ADJECTIVES[i % len(ADJECTIVES)]} {NOUNS[(i * 5) % len(NOUNS)]} {category.split()[0]}",
            country=country, region=region, category=category,
            quoted_lead_time_days=int(round(lead_mean)),
            # --- hidden "true behaviour" (NOT written to the raw files) ---
            _lead_mean=lead_mean,
            _lead_std=float(np.clip(lead_mean * rng.uniform(0.15, 0.45), 1, 12)),
            _reliability=float(np.clip(rng.normal(0.90, 0.08), 0.55, 0.995)),
            _cost_index=float(np.clip(rng.normal(1.0, 0.15), 0.65, 1.5)),
        ))
    return pd.DataFrame(rows)


def make_products(rng, suppliers, n):
    rows = []
    for i in range(n):
        supplier = suppliers.iloc[int(rng.integers(len(suppliers)))]
        category = supplier["category"]
        sub = str(rng.choice(SUB_CATEGORIES[category]))
        unit_cost = float(np.clip(rng.lognormal(2.2, 0.9), 1.5, 800))
        rows.append(dict(
            sku=f"SKU-{i + 1:05d}",
            product_name=f"{sub} {PRODUCT_SUFFIX[int(rng.integers(len(PRODUCT_SUFFIX)))]}-{i + 1}",
            category=category, sub_category=sub,
            unit_cost=round(unit_cost, 2),
            unit_price=round(unit_cost * float(rng.uniform(1.25, 2.4)), 2),
            supplier_code=supplier["supplier_code"],
            # --- hidden demand behaviour ---
            _base_daily=float(np.clip(rng.lognormal(3.0, 1.1), 3, 800)),
            _noise=float(rng.uniform(0.15, 0.55)),
            _trend=float(rng.uniform(-0.15, 0.35)),
            _season_amp=float(rng.uniform(0.05, 0.40)),
            _has_shock=bool(rng.random() < 0.12),
        ))
    return pd.DataFrame(rows)


def make_promo_calendar(rng, n_days, n_windows=8):
    """Promo flag + uplift per day for ONE sku (same calendar for all warehouses)."""
    flag = np.zeros(n_days, dtype=int)
    uplift = np.ones(n_days)
    for _ in range(n_windows):
        length = int(rng.integers(3, 8))
        start = int(rng.integers(0, n_days - length))
        flag[start:start + length] = 1
        uplift[start:start + length] = np.maximum(uplift[start:start + length], rng.uniform(1.3, 2.0))
    return flag, uplift


def simulate_demand(rng, base, noise, trend, season_amp, phase, n_days, promo_uplift, shock):
    """Daily demand = level x trend x weekday pattern x yearly season x promo + noise (+ optional shock)."""
    days = np.arange(n_days)
    mean = base * (1 + trend * days / 365.0) \
        * (1 + 0.12 * np.sin(2 * np.pi * days / 7.0 + 1.0)) \
        * (1 + season_amp * np.sin(2 * np.pi * days / 365.0 + phase))
    mean = np.clip(mean, 0.5, None)
    demand = rng.normal(mean, mean * noise) * promo_uplift
    if shock:   # one sustained spike or collapse somewhere in the 2 years
        length = int(rng.integers(7, 22))
        start = int(rng.integers(0, n_days - length))
        demand[start:start + length] *= float(rng.choice([2.5, 0.3]))
    return np.clip(np.round(demand), 0, None).astype(int)


# ----------------------------------------------------------------------------- main simulation
def generate_clean(seed=cfg.SEED, n_skus=cfg.N_SKUS, n_suppliers=cfg.N_SUPPLIERS, n_days=cfg.N_DAYS,
                   start_date=cfg.START_DATE):
    """Return a dict of CLEAN DataFrames (the 'truth'). Call inject_raw_issues() to make them messy."""
    rng = np.random.default_rng(seed)
    suppliers = make_suppliers(rng, n_suppliers)
    products = make_products(rng, suppliers, n_skus)
    sup = suppliers.set_index("supplier_code")
    warehouses = pd.DataFrame(WAREHOUSES, columns=["warehouse_code", "warehouse_name", "region", "capacity_units"])
    wh_codes = warehouses["warehouse_code"].tolist()
    dates = pd.date_range(start_date, periods=n_days, freq="D")

    plan_days = min(91, n_days)               # policy is computed from the first 13 weeks
    z = cfg.SERVICE_Z
    review = cfg.REVIEW_PERIOD_DAYS

    demand_parts, inv_parts, policy_rows, po_rows = [], [], [], []
    po_counter = 1

    for _, p in products.iterrows():
        s = sup.loc[p["supplier_code"]]
        n_wh = int(rng.integers(1, 4))                                   # SKU stocked in 1-3 warehouses
        sku_whs = [str(w) for w in rng.choice(wh_codes, size=n_wh, replace=False)]
        promo_flag, promo_uplift = make_promo_calendar(rng, n_days)
        shock_pending = bool(p["_has_shock"])
        phase = CATEGORY_PHASE[p["category"]]

        for wh in sku_whs:
            demand = simulate_demand(
                rng, p["_base_daily"] / n_wh * float(rng.uniform(0.7, 1.3)), p["_noise"], p["_trend"],
                p["_season_amp"], phase, n_days, promo_uplift, shock_pending and wh == sku_whs[0])

            # ---- inventory policy (what the company "currently uses")
            avg_d, sd_d = float(demand[:plan_days].mean()), float(demand[:plan_days].std()) + 1e-6
            lt = max(float(s["_lead_mean"]) * 1.2, 1.0)                 # planner's lead time (a bit above the road quote)
            safety = max(2, int(round(z * sd_d * math.sqrt(lt + review))))   # ignores lead-time variability + later trend/season
            rop = int(round(avg_d * lt + safety))
            order_up_to = int(round(rop + avg_d * 14))
            policy_rows.append(dict(sku=p["sku"], warehouse_code=wh, reorder_point_units=rop,
                                    safety_stock_units=safety, order_up_to_units=order_up_to,
                                    review_period_days=review, policy_set_date=dates[plan_days - 1].date()))

            on_hand, in_transit, pending = order_up_to, 0, {}
            fulfilled_arr = np.zeros(n_days, dtype=int)
            on_hand_arr = np.zeros(n_days, dtype=int)
            transit_arr = np.zeros(n_days, dtype=int)

            for day in range(n_days):
                if day in pending:                                        # goods arrive at start of day
                    qty = pending.pop(day)
                    on_hand += qty
                    in_transit -= qty
                fulfilled = min(on_hand, int(demand[day]))
                on_hand -= fulfilled
                fulfilled_arr[day], on_hand_arr[day], transit_arr[day] = fulfilled, on_hand, in_transit

                position = on_hand + in_transit
                if day % review == 0 and position < rop:                  # weekly review -> maybe order
                    qty = int(max(order_up_to - position, avg_d * review))
                    if s["region"] == "North America":
                        mode = str(rng.choice(["road", "rail", "air"], p=[0.6, 0.3, 0.1]))
                    else:
                        mode = str(rng.choice(["ocean", "air", "road", "rail"], p=[0.55, 0.2, 0.1, 0.15]))
                    if on_hand < safety and rng.random() < 0.7:          # emergency -> expedite by air
                        mode = "air"
                    f = MODE_LEAD_FACTOR[mode]
                    promised_days = max(1, int(round(float(s["_lead_mean"]) * f)))
                    actual_days = max(1, int(round(rng.normal(s["_lead_mean"] * f, s["_lead_std"] * f))))
                    if rng.random() > s["_reliability"]:                  # supplier delay
                        actual_days += int(rng.integers(2, 11))
                    arrival = day + actual_days
                    unit_cost = round(float(p["unit_cost"]) * float(s["_cost_index"]), 2)
                    delivered = arrival < n_days
                    if delivered:
                        pending[arrival] = pending.get(arrival, 0) + qty   # accumulate (original overwrote!)
                    in_transit += qty
                    order_date = dates[day]
                    po_rows.append(dict(
                        po_number=f"PO-{po_counter:06d}", supplier_code=p["supplier_code"], sku=p["sku"],
                        warehouse_code=wh, order_date=order_date.date(),
                        promised_delivery_date=(order_date + pd.Timedelta(days=promised_days)).date(),
                        actual_delivery_date=(order_date + pd.Timedelta(days=actual_days)).date() if delivered else None,
                        quantity=qty, unit_cost=unit_cost, ship_mode=mode,
                        freight_cost=round(qty * unit_cost * MODE_FREIGHT_RATE[mode] * float(rng.uniform(0.8, 1.2)), 2),
                        status="delivered" if delivered else "open"))
                    po_counter += 1

            demand_parts.append(pd.DataFrame(dict(
                sku=p["sku"], warehouse_code=wh, date=dates, units_demanded=demand,
                units_fulfilled=fulfilled_arr, promo_flag=promo_flag)))
            inv_parts.append(pd.DataFrame(dict(
                sku=p["sku"], warehouse_code=wh, date=dates, on_hand_units=on_hand_arr,
                in_transit_units=transit_arr)))

    products_out = products[["sku", "product_name", "category", "sub_category", "unit_cost", "unit_price",
                             "supplier_code"]].copy()
    suppliers_out = suppliers[["supplier_code", "supplier_name", "country", "region", "category",
                               "quoted_lead_time_days"]].copy()
    return dict(
        suppliers=suppliers_out, warehouses=warehouses, products=products_out,
        demand_daily=pd.concat(demand_parts, ignore_index=True),
        inventory_daily=pd.concat(inv_parts, ignore_index=True),
        inventory_policy=pd.DataFrame(policy_rows),
        purchase_orders=pd.DataFrame(po_rows),
    )


# ----------------------------------------------------------------------------- make it messy
def inject_raw_issues(tables, seed=cfg.SEED + 1):
    """
    Take CLEAN tables and return a MESSY copy, like data exported from a real ERP:
    duplicates, inconsistent text, mixed date formats, impossible values, missing values.
    All problems are random but reproducible (fixed seed).
    """
    rng = np.random.default_rng(seed)
    out = {k: v.copy() for k, v in tables.items()}

    # ---------------- demand_daily
    d = out["demand_daily"]
    d["date"] = d["date"].dt.strftime("%Y-%m-%d")
    d["sku"] = d["sku"].astype(object)
    d["warehouse_code"] = d["warehouse_code"].astype(object)
    n = len(d)
    idx = rng.choice(n, size=int(n * 0.010), replace=False)                  # messy dates "05-Mar-2024"
    d.loc[idx, "date"] = pd.to_datetime(d.loc[idx, "date"]).dt.strftime("%d-%b-%Y")
    idx = rng.choice(n, size=int(n * 0.010), replace=False)                  # sku in lowercase / trailing space
    d.loc[idx, "sku"] = d.loc[idx, "sku"].str.lower() + " "
    idx = rng.choice(n, size=int(n * 0.005), replace=False)                  # warehouse code lowercase
    d.loc[idx, "warehouse_code"] = d.loc[idx, "warehouse_code"].str.lower()
    d["units_demanded"] = d["units_demanded"].astype(float)
    idx = rng.choice(n, size=int(n * 0.003), replace=False)                  # missing demand
    d.loc[idx, "units_demanded"] = np.nan
    idx = rng.choice(n, size=int(n * 0.001), replace=False)                  # sign error
    d.loc[idx, "units_demanded"] = -d.loc[idx, "units_demanded"].abs()
    idx = rng.choice(n, size=int(n * 0.002), replace=False)                  # fulfilled > demanded (impossible)
    d.loc[idx, "units_fulfilled"] = d.loc[idx, "units_demanded"].abs().fillna(0) + rng.integers(1, 30, len(idx))
    idx = rng.choice(n, size=max(5, int(n * 0.0004)), replace=False)         # typo: extra zeros (x100)
    d.loc[idx, "units_demanded"] = d.loc[idx, "units_demanded"].abs() * 100
    dup = d.sample(frac=0.005, random_state=seed)                            # exact duplicate rows
    out["demand_daily"] = pd.concat([d, dup], ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)

    # ---------------- inventory_daily
    v = out["inventory_daily"]
    v["date"] = v["date"].dt.strftime("%Y-%m-%d")
    v["on_hand_units"] = v["on_hand_units"].astype(float)
    n = len(v)
    idx = rng.choice(n, size=int(n * 0.003), replace=False)
    v.loc[idx, "on_hand_units"] = np.nan                                      # missing stock count
    idx = rng.choice(n, size=int(n * 0.001), replace=False)
    v.loc[idx, "on_hand_units"] = -rng.integers(1, 50, len(idx))              # negative stock
    dup = v.sample(frac=0.003, random_state=seed)
    out["inventory_daily"] = pd.concat([v, dup], ignore_index=True)

    # ---------------- products
    p = out["products"]
    p["category"] = p["category"].astype(object)
    idx = rng.choice(len(p), size=max(3, len(p) // 10), replace=False)
    p.loc[idx, "category"] = p.loc[idx, "category"].str.upper() + " "         # "ELECTRONICS "
    idx = rng.choice(len(p), size=max(2, len(p) // 20), replace=False)
    p.loc[idx, "category"] = p.loc[idx, "category"].str.lower()
    idx = rng.choice(len(p), size=max(2, len(p) // 25), replace=False)
    p["unit_cost"] = p["unit_cost"].astype(float)
    p.loc[idx, "unit_cost"] = np.nan                                          # missing cost
    out["products"] = pd.concat([p, p.sample(n=2, random_state=seed)], ignore_index=True)   # duplicate master rows

    # ---------------- suppliers
    s = out["suppliers"]
    s["region"] = s["region"].astype(object)
    idx = rng.choice(len(s), size=max(2, len(s) // 6), replace=False)
    s.loc[idx, "region"] = s.loc[idx, "region"].str.upper() + " "
    s["quoted_lead_time_days"] = s["quoted_lead_time_days"].astype(float)
    s.loc[rng.choice(len(s), size=2, replace=False), "quoted_lead_time_days"] = np.nan
    out["suppliers"] = s

    # ---------------- purchase_orders
    po = out["purchase_orders"]
    n = len(po)
    po["freight_cost"] = po["freight_cost"].astype(float)
    po.loc[rng.choice(n, size=max(3, int(n * 0.01)), replace=False), "freight_cost"] = np.nan
    po["quantity"] = po["quantity"].astype(float)
    po.loc[rng.choice(n, size=max(2, int(n * 0.002)), replace=False), "quantity"] *= -1
    delivered = po.index[po["actual_delivery_date"].notna()].to_numpy()
    bad = rng.choice(delivered, size=max(3, int(len(delivered) * 0.003)), replace=False)   # delivered before ordered
    po["actual_delivery_date"] = po["actual_delivery_date"].astype(object)
    for i in bad:
        po.at[i, "actual_delivery_date"] = (pd.Timestamp(po.at[i, "order_date"]) - pd.Timedelta(days=int(rng.integers(1, 6)))).date()
    po["ship_mode"] = po["ship_mode"].astype(object)
    idx = rng.choice(n, size=int(n * 0.02), replace=False)
    po.loc[idx, "ship_mode"] = po.loc[idx, "ship_mode"].str.upper()
    out["purchase_orders"] = pd.concat([po, po.sample(frac=0.003, random_state=seed)], ignore_index=True)
    return out


def write_raw(tables, folder=None):
    """Write tables to CSV files (the 'raw' layer)."""
    folder = folder or cfg.DATA_RAW
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(folder / f"{name}.csv", index=False)

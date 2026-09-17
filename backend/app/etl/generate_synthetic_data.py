"""
ETL: Synthetic Supply Chain Data Generator
===========================================
Generates a coherent, internally-consistent synthetic dataset for the
Supply Chain Intelligence Platform:

  suppliers -> products -> demand_history -> inventory simulation
  -> purchase_orders/purchase_order_items -> shipments -> quality_records
  -> customer_orders -> derived rollups (abc_class, safety stock, reorder point,
     supplier scorecards)

The generation is a day-by-day discrete-event simulation per (product, warehouse)
so that inventory, demand, purchase orders, and stockouts are causally consistent
(not just independently randomized columns), which is what makes the resulting
analytics/ML meaningful.

Run:  python -m app.etl.generate_synthetic_data
"""
import math
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker
from sqlalchemy import text

from app.core.database import engine, SessionLocal, Base
from app.models import models as m

fake = Faker()
random.seed(42)
np.random.seed(42)

SIM_DAYS = 365
START_DATE = date.today() - timedelta(days=SIM_DAYS)

REGIONS = ["North America", "Europe", "East Asia", "South Asia", "Latin America"]
COUNTRY_BY_REGION = {
    "North America": ["USA", "Mexico", "Canada"],
    "Europe": ["Germany", "Poland", "Italy", "Netherlands"],
    "East Asia": ["China", "Vietnam", "South Korea", "Taiwan"],
    "South Asia": ["India", "Bangladesh"],
    "Latin America": ["Brazil", "Colombia"],
}
SUPPLIER_CATEGORIES = ["Electronics", "Packaging", "Raw Materials", "Textiles", "Machinery Parts", "Chemicals"]
PRODUCT_CATEGORIES = {
    "Electronics": ["Sensors", "Circuit Boards", "Connectors", "Displays"],
    "Packaging": ["Cartons", "Pallets", "Labels", "Wrap Film"],
    "Raw Materials": ["Steel Coil", "Aluminum Sheet", "Resin Pellets"],
    "Textiles": ["Cotton Fabric", "Synthetic Fiber", "Zippers"],
    "Machinery Parts": ["Bearings", "Motors", "Gearboxes", "Valves"],
    "Chemicals": ["Adhesives", "Coatings", "Solvents"],
}
CARRIERS = ["Maersk Line", "DHL Global", "FedEx Freight", "DB Schenker", "Kuehne+Nagel", "CN Rail Logistics"]
MODES = ["ocean", "air", "road", "rail"]


# ---------------------------------------------------------------------------
# 1. Suppliers
# ---------------------------------------------------------------------------
def gen_suppliers(n=32):
    rows = []
    for i in range(1, n + 1):
        region = random.choice(REGIONS)
        country = random.choice(COUNTRY_BY_REGION[region])
        category = random.choice(SUPPLIER_CATEGORIES)
        # "true" latent reliability parameters used to drive the simulation
        base_reliability = np.clip(np.random.normal(0.90, 0.08), 0.55, 0.995)
        base_defect_rate = np.clip(np.random.gamma(2, 0.008), 0.001, 0.12)
        base_lead_time = np.clip(np.random.normal(18 if region != "North America" else 8, 5), 3, 45)
        lead_time_std = np.clip(base_lead_time * np.random.uniform(0.15, 0.45), 1, 12)
        cost_index = np.clip(np.random.normal(1.0, 0.15), 0.65, 1.5)

        if base_reliability > 0.93 and base_defect_rate < 0.02:
            risk_tier = "low"
        elif base_reliability < 0.75 or base_defect_rate > 0.06:
            risk_tier = "high"
        else:
            risk_tier = "medium"

        rows.append(dict(
            supplier_code=f"SUP-{i:04d}",
            name=f"{fake.company()} {category.split()[0]}",
            country=country,
            region=region,
            category=category,
            risk_tier=risk_tier,
            cost_index=round(float(cost_index), 3),
            active=True,
            _true_reliability=base_reliability,
            _true_defect_rate=base_defect_rate,
            _true_lead_time=base_lead_time,
            _true_lead_time_std=lead_time_std,
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Warehouses
# ---------------------------------------------------------------------------
def gen_warehouses():
    data = [
        ("WH-EAST", "East Distribution Center", "North America", 500000),
        ("WH-WEST", "West Coast Fulfillment Hub", "North America", 420000),
        ("WH-EU", "European Central Warehouse", "Europe", 380000),
        ("WH-APAC", "APAC Regional Hub", "East Asia", 450000),
        ("WH-SOUTH", "Southern Logistics Center", "Latin America", 260000),
    ]
    return pd.DataFrame(data, columns=["warehouse_code", "name", "region", "capacity_units"])


# ---------------------------------------------------------------------------
# 3. Products
# ---------------------------------------------------------------------------
def gen_products(suppliers_df, n=90):
    rows = []
    for i in range(1, n + 1):
        supplier = suppliers_df.sample(1).iloc[0]
        category = supplier["category"]
        sub = random.choice(PRODUCT_CATEGORIES[category])
        unit_cost = round(float(np.clip(np.random.lognormal(2.2, 0.9), 1.5, 800)), 2)
        margin = np.random.uniform(1.25, 2.4)
        unit_price = round(unit_cost * margin, 2)
        # latent demand parameters
        base_daily_demand = float(np.clip(np.random.lognormal(3.0, 1.1), 3, 800))
        demand_std_ratio = np.random.uniform(0.15, 0.55)
        trend_pct_per_year = np.random.uniform(-0.15, 0.35)
        seasonality_amp = np.random.uniform(0.05, 0.4)
        rows.append(dict(
            sku=f"SKU-{i:05d}",
            name=f"{sub} - {fake.word().capitalize()} {random.choice(['Pro','X','Std','Plus','Lite'])}",
            category=sub,
            unit_cost=unit_cost,
            unit_price=unit_price,
            primary_supplier_id=None,  # filled after DB insert of suppliers
            _supplier_code=supplier["supplier_code"],
            active=True,
            _base_daily_demand=base_daily_demand,
            _demand_std_ratio=demand_std_ratio,
            _trend_pct_per_year=trend_pct_per_year,
            _seasonality_amp=seasonality_amp,
            _is_anomalous=random.random() < 0.12,  # ~12% of SKUs get an injected demand shock
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Demand history generation (per product-warehouse) with seasonality/trend/noise
# ---------------------------------------------------------------------------
def simulate_demand_series(base, std_ratio, trend_pct_per_year, seasonality_amp, n_days, anomalous=False):
    days = np.arange(n_days)
    trend = 1 + (trend_pct_per_year * (days / 365.0))
    weekly = 1 + 0.12 * np.sin(2 * np.pi * days / 7.0 + 1.0)
    yearly = 1 + seasonality_amp * np.sin(2 * np.pi * days / 365.0)
    mean = np.clip(base * trend * weekly * yearly, 0.5, None)
    noise_std = mean * std_ratio
    demand = np.random.normal(mean, noise_std)

    # occasional promo spikes
    promo_days = np.random.choice(days, size=max(1, n_days // 45), replace=False)
    demand[promo_days] *= np.random.uniform(1.6, 2.8, size=len(promo_days))

    if anomalous:
        # inject a sustained anomaly window (spike or collapse) in the last 60 days
        start = n_days - random.randint(20, 55)
        length = random.randint(7, 18)
        direction = random.choice([2.5, 0.25])
        demand[start:start + length] *= direction

    demand = np.clip(np.round(demand), 0, None).astype(int)
    return demand


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def run():
    print("Resetting schema (drop & recreate all tables)...")
    Base.metadata.drop_all(bind=engine)
    with engine.connect() as conn:
        # Recreate via raw SQL (indexes/views) rather than SQLAlchemy metadata for full parity
        with open_init_sql() as f:
            conn.execute(text(f.read()))
        conn.commit()

    print("Generating suppliers...")
    suppliers_df = gen_suppliers()
    print("Generating warehouses...")
    warehouses_df = gen_warehouses()
    print("Generating products...")
    products_df = gen_products(suppliers_df)

    session = SessionLocal()
    try:
        # --- insert suppliers ---
        supplier_id_map = {}
        for _, row in suppliers_df.iterrows():
            s = m.Supplier(
                supplier_code=row["supplier_code"], name=row["name"], country=row["country"],
                region=row["region"], category=row["category"], risk_tier=row["risk_tier"],
                cost_index=row["cost_index"], active=True,
                avg_lead_time_days=round(float(row["_true_lead_time"]), 2),
                lead_time_std_days=round(float(row["_true_lead_time_std"]), 2),
            )
            session.add(s)
            session.flush()
            supplier_id_map[row["supplier_code"]] = s.id
        session.commit()

        # --- insert warehouses ---
        wh_id_map = {}
        for _, row in warehouses_df.iterrows():
            w = m.Warehouse(warehouse_code=row["warehouse_code"], name=row["name"],
                             region=row["region"], capacity_units=int(row["capacity_units"]))
            session.add(w)
            session.flush()
            wh_id_map[row["warehouse_code"]] = w.id
        session.commit()
        wh_ids = list(wh_id_map.values())

        # --- insert products ---
        product_id_map = {}
        product_meta = {}
        for _, row in products_df.iterrows():
            supplier_id = supplier_id_map[row["_supplier_code"]]
            p = m.Product(
                sku=row["sku"], name=row["name"], category=row["category"],
                unit_cost=row["unit_cost"], unit_price=row["unit_price"],
                primary_supplier_id=supplier_id, active=True,
                safety_stock_units=0, reorder_point_units=0,
            )
            session.add(p)
            session.flush()
            product_id_map[row["sku"]] = p.id
            product_meta[p.id] = dict(
                supplier_id=supplier_id,
                base_daily_demand=row["_base_daily_demand"],
                demand_std_ratio=row["_demand_std_ratio"],
                trend_pct_per_year=row["_trend_pct_per_year"],
                seasonality_amp=row["_seasonality_amp"],
                is_anomalous=row["_is_anomalous"],
                unit_cost=float(row["unit_cost"]),
            )
        session.commit()
        print(f"Inserted {len(supplier_id_map)} suppliers, {len(wh_id_map)} warehouses, {len(product_id_map)} products")

        supplier_lookup = {s.id: s for s in session.query(m.Supplier).all()}

        # --- assign each product to 1-3 warehouses ---
        product_warehouses = {}
        for pid in product_id_map.values():
            k = random.randint(1, 3)
            product_warehouses[pid] = random.sample(wh_ids, k)

        # --- simulate demand + inventory + PO/shipments/quality per (product, warehouse) ---
        print("Simulating demand, inventory, purchase orders, shipments, quality (this drives all downstream analytics)...")
        po_counter = 1
        demand_rows, inv_rows, corder_rows = [], [], []
        po_objs = []  # (po_number, supplier_id, warehouse_id, order_date, promised_date, items[(product_id, qty, unit_cost)])
        quality_rows = []

        for pid, meta in product_meta.items():
            supplier = supplier_lookup[meta["supplier_id"]]
            lead_time_mean = float(supplier.avg_lead_time_days)
            lead_time_std = float(supplier.lead_time_std_days)
            reliability = None
            # recover latent reliability/defect rate approx from supplier row via suppliers_df
            srow = suppliers_df[suppliers_df["supplier_code"] ==
                                 [k for k, v in supplier_id_map.items() if v == supplier.id][0]].iloc[0]
            reliability = srow["_true_reliability"]
            defect_rate_true = srow["_true_defect_rate"]

            for wh_id in product_warehouses[pid]:
                demand_series = simulate_demand_series(
                    meta["base_daily_demand"] / max(1, len(product_warehouses[pid])),
                    meta["demand_std_ratio"], meta["trend_pct_per_year"], meta["seasonality_amp"],
                    SIM_DAYS, anomalous=meta["is_anomalous"],
                )
                avg_demand = float(np.mean(demand_series))
                std_demand = float(np.std(demand_series)) + 1e-6

                # inventory policy parameters (periodic review, order-up-to)
                z = 1.65  # ~95% service level target
                safety_stock = max(2, int(round(z * std_demand * math.sqrt(max(lead_time_mean, 1)))))
                reorder_point = int(round(avg_demand * lead_time_mean + safety_stock))
                order_up_to = int(round(reorder_point + avg_demand * 10))  # cover ~10 more days beyond ROP

                on_hand = order_up_to
                in_transit = 0
                pending_arrivals = {}  # day_index -> qty arriving

                review_period = 7
                for day in range(SIM_DAYS):
                    d = START_DATE + timedelta(days=day)
                    todays_demand = int(demand_series[day])

                    # receive arrivals
                    if day in pending_arrivals:
                        arrival_qty, po_id_arrival = pending_arrivals.pop(day)
                        on_hand += arrival_qty
                        in_transit = max(0, in_transit - arrival_qty)

                    fulfilled = min(on_hand, todays_demand)
                    stockout = fulfilled < todays_demand
                    on_hand -= fulfilled

                    demand_rows.append(dict(product_id=pid, warehouse_id=wh_id, demand_date=d,
                                             units_demanded=todays_demand, units_fulfilled=fulfilled))
                    inv_rows.append(dict(product_id=pid, warehouse_id=wh_id, snapshot_date=d,
                                          on_hand_units=max(on_hand, 0), in_transit_units=in_transit,
                                          allocated_units=0, stockout_flag=stockout))

                    promised = d + timedelta(days=random.randint(1, 3))
                    on_time_flag = True
                    ship_date = d
                    if fulfilled < todays_demand:
                        on_time_flag = False
                    corder_rows.append(dict(
                        order_number=f"CO-{pid}-{wh_id}-{day}", product_id=pid, warehouse_id=wh_id,
                        order_date=d, requested_qty=todays_demand, shipped_qty=fulfilled,
                        promised_date=promised, shipped_date=ship_date if fulfilled > 0 else None,
                        on_time=on_time_flag, in_full=(fulfilled == todays_demand),
                    ))

                    # periodic review: place PO if inventory position below reorder point
                    inv_position = on_hand + in_transit
                    if day % review_period == 0 and inv_position < reorder_point:
                        order_qty = max(order_up_to - inv_position, int(avg_demand * review_period))
                        actual_lead = max(1, int(round(np.random.normal(lead_time_mean, lead_time_std))))
                        # reliability affects whether delay occurs
                        delayed = random.random() > reliability
                        if delayed:
                            actual_lead += random.randint(2, 10)
                        arrival_day = day + actual_lead
                        promised_delivery = d + timedelta(days=int(round(lead_time_mean)))
                        actual_delivery = d + timedelta(days=actual_lead)
                        unit_cost = meta["unit_cost"] * float(supplier.cost_index)

                        po_number = f"PO-{po_counter:06d}"
                        po_counter += 1
                        status = "delivered" if arrival_day < SIM_DAYS else "in_transit"
                        po_objs.append(dict(
                            po_number=po_number, supplier_id=supplier.id, warehouse_id=wh_id,
                            order_date=d, promised_date=promised_delivery,
                            actual_delivery_date=actual_delivery if arrival_day < SIM_DAYS else None,
                            status=status, total_cost=round(order_qty * unit_cost, 2),
                            item=dict(product_id=pid, quantity=order_qty, unit_cost=round(unit_cost, 2)),
                            carrier=random.choice(CARRIERS), mode=random.choice(MODES),
                            ship_date=d, expected_arrival=promised_delivery,
                            actual_arrival=actual_delivery if arrival_day < SIM_DAYS else None,
                            delay_days=max(0, (actual_delivery - promised_delivery).days),
                            freight_cost=round(order_qty * unit_cost * np.random.uniform(0.03, 0.09), 2),
                        ))

                        if arrival_day < SIM_DAYS:
                            pending_arrivals[arrival_day] = (order_qty, po_number)
                        in_transit += order_qty

                        # quality inspection on ~70% of received POs
                        if random.random() < 0.7:
                            inspected = int(order_qty * np.random.uniform(0.1, 0.3))
                            inspected = max(inspected, 5)
                            defect_rate = np.clip(np.random.normal(defect_rate_true, defect_rate_true * 0.4 + 0.005), 0, 0.5)
                            defective = int(round(inspected * defect_rate))
                            quality_rows.append(dict(
                                supplier_id=supplier.id, product_id=pid,
                                inspection_date=actual_delivery if arrival_day < SIM_DAYS else d,
                                units_inspected=inspected, units_defective=defective,
                                defect_rate=round(defect_rate, 4),
                                root_cause=random.choice([
                                    "Material inconsistency", "Handling damage", "Process variation",
                                    "Packaging failure", "Supplier tooling wear", None, None,
                                ]) if defective > 0 else None,
                            ))

                # update product safety stock / reorder point with final computed values
                session.query(m.Product).filter(m.Product.id == pid).update({
                    "safety_stock_units": safety_stock,
                    "reorder_point_units": reorder_point,
                })

        session.commit()
        print(f"Simulated {len(demand_rows)} demand rows, {len(po_objs)} purchase orders")

        # --- bulk insert demand history, inventory, customer orders via pandas to_sql ---
        print("Bulk loading demand_history / inventory_snapshots / customer_orders ...")
        pd.DataFrame(demand_rows).to_sql("demand_history", engine, if_exists="append", index=False, method="multi", chunksize=5000)
        pd.DataFrame(inv_rows).to_sql("inventory_snapshots", engine, if_exists="append", index=False, method="multi", chunksize=5000)
        pd.DataFrame(corder_rows).to_sql("customer_orders", engine, if_exists="append", index=False, method="multi", chunksize=5000)

        # --- insert purchase orders + items + shipments ---
        print("Loading purchase orders, items, and shipments...")
        po_df = pd.DataFrame(po_objs)
        po_df[["po_number", "supplier_id", "warehouse_id", "order_date", "promised_date",
               "actual_delivery_date", "status", "total_cost"]].to_sql(
            "purchase_orders", engine, if_exists="append", index=False, method="multi", chunksize=5000)

        po_id_lookup = pd.read_sql("SELECT id, po_number FROM purchase_orders", engine).set_index("po_number")["id"].to_dict()

        items_df = pd.DataFrame([{
            "purchase_order_id": po_id_lookup[r["po_number"]],
            "product_id": r["item"]["product_id"],
            "quantity": r["item"]["quantity"],
            "unit_cost": r["item"]["unit_cost"],
            "quantity_received": r["item"]["quantity"] if r["status"] == "delivered" else 0,
            "defect_units": 0,
        } for r in po_objs])
        items_df.to_sql("purchase_order_items", engine, if_exists="append", index=False, method="multi", chunksize=5000)

        shipments_df = pd.DataFrame([{
            "purchase_order_id": po_id_lookup[r["po_number"]],
            "carrier": r["carrier"], "ship_date": r["ship_date"], "expected_arrival": r["expected_arrival"],
            "actual_arrival": r["actual_arrival"], "mode": r["mode"],
            "status": "delivered" if r["status"] == "delivered" else "in_transit",
            "delay_days": r["delay_days"], "freight_cost": r["freight_cost"],
        } for r in po_objs])
        shipments_df.to_sql("shipments", engine, if_exists="append", index=False, method="multi", chunksize=5000)

        if quality_rows:
            pd.DataFrame(quality_rows).to_sql("quality_records", engine, if_exists="append", index=False, method="multi", chunksize=5000)

        # --- compute supplier rollups from actual generated data ---
        print("Computing supplier rollups (on-time rate, quality score)...")
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE suppliers s SET
                  on_time_rate = sub.on_time_rate,
                  quality_score = sub.quality_score
                FROM (
                  SELECT
                    po.supplier_id,
                    AVG(CASE WHEN po.actual_delivery_date IS NOT NULL
                             AND po.actual_delivery_date <= po.promised_date THEN 1.0 ELSE 0.0 END) AS on_time_rate,
                    100 - LEAST(100, AVG(COALESCE(qr.defect_rate, 0)) * 1000) AS quality_score
                  FROM purchase_orders po
                  LEFT JOIN quality_records qr ON qr.supplier_id = po.supplier_id
                  GROUP BY po.supplier_id
                ) sub
                WHERE s.id = sub.supplier_id
            """))
            conn.commit()

        # --- compute ABC classification by revenue contribution ---
        print("Computing ABC classification...")
        with engine.connect() as conn:
            conn.execute(text("""
                WITH revenue AS (
                  SELECT p.id AS product_id, p.unit_price * COALESCE(SUM(d.units_fulfilled), 0) AS total_revenue
                  FROM products p
                  LEFT JOIN demand_history d ON d.product_id = p.id
                  GROUP BY p.id, p.unit_price
                ),
                ranked AS (
                  SELECT product_id, total_revenue,
                         SUM(total_revenue) OVER (ORDER BY total_revenue DESC) / NULLIF(SUM(total_revenue) OVER (), 0) AS cum_pct
                  FROM revenue
                )
                UPDATE products p SET abc_class = CASE
                  WHEN r.cum_pct <= 0.7 THEN 'A'
                  WHEN r.cum_pct <= 0.9 THEN 'B'
                  ELSE 'C' END
                FROM ranked r WHERE r.product_id = p.id
            """))
            conn.commit()

        print("Synthetic data generation complete.")
    finally:
        session.close()


def open_init_sql():
    import os
    candidates = [
        "/app/db/init.sql",
        "/db/init.sql",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "db", "init.sql"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return open(c, "r")
    raise FileNotFoundError("init.sql not found in expected locations: " + ", ".join(candidates))


if __name__ == "__main__":
    run()

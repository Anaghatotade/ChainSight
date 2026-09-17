"""
Inventory Analysis
==================
Computes days-of-supply and health status per (product, warehouse) based on
current on-hand position and trailing average daily demand.
"""
import pandas as pd


def classify_status(on_hand, safety_stock, reorder_point, days_of_supply):
    if on_hand <= 0:
        return "critical"
    if on_hand < safety_stock:
        return "critical"
    if on_hand < reorder_point:
        return "low"
    if days_of_supply is not None and days_of_supply > 90:
        return "overstock"
    return "healthy"


def compute_inventory_health(latest_inventory: pd.DataFrame, avg_demand: pd.DataFrame) -> pd.DataFrame:
    """
    latest_inventory: product_id, warehouse_id, on_hand_units, in_transit_units,
                       safety_stock_units, reorder_point_units, sku, name, category, abc_class
    avg_demand: product_id, warehouse_id, avg_daily_demand
    """
    df = latest_inventory.merge(avg_demand, on=["product_id", "warehouse_id"], how="left")
    df["avg_daily_demand"] = df["avg_daily_demand"].fillna(0.1)
    df["days_of_supply"] = (df["on_hand_units"] / df["avg_daily_demand"].replace(0, 0.1)).round(1)
    df["inventory_status"] = df.apply(
        lambda r: classify_status(r["on_hand_units"], r["safety_stock_units"], r["reorder_point_units"], r["days_of_supply"]),
        axis=1,
    )
    return df

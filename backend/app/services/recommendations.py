"""
Recommendation Engine
=====================
Rule-based synthesis of actionable recommendations from the outputs of the
other analytics/ML components (supplier scores, inventory health, stockout
risk, anomalies). Each recommendation cites the data that triggered it and
an estimated impact so it reads like a real BI insight rather than a
generic tip.
"""
from typing import List


def generate_recommendations(supplier_scores_df, inventory_df, risk_df, anomalies: List[dict]) -> List[dict]:
    recs = []

    # --- Supplier-driven ---
    for _, row in supplier_scores_df.sort_values("composite_score").head(8).iterrows():
        if row["composite_score"] < 65:
            priority = "critical" if row["composite_score"] < 45 else "high"
            recs.append(dict(
                category="supplier",
                entity_type="supplier",
                entity_id=int(row["supplier_id"]),
                priority=priority,
                title=f"Review sourcing strategy for {row['name']}",
                description=(f"{row['name']} scores {row['composite_score']:.0f}/100 (grade {row['grade']}), "
                              f"driven by on-time rate {row['on_time_rate']*100:.0f}% and defect rate "
                              f"{row['avg_defect_rate']*100:.1f}%. Consider dual-sourcing or a corrective action "
                              f"plan for products relying primarily on this supplier."),
                estimated_impact="Reduces exposure to delivery delays and quality-driven stockouts for dependent SKUs.",
            ))

    # --- Inventory-driven ---
    critical_inv = inventory_df[inventory_df["inventory_status"] == "critical"]
    for _, row in critical_inv.sort_values("days_of_supply").head(10).iterrows():
        recs.append(dict(
            category="inventory",
            entity_type="product",
            entity_id=int(row["product_id"]),
            priority="critical",
            title=f"Expedite replenishment for {row['sku']} ({row['name']})",
            description=(f"On-hand inventory of {int(row['on_hand_units'])} units provides only "
                          f"{row['days_of_supply']:.1f} days of supply at current demand -- below the "
                          f"safety stock threshold of {int(row['safety_stock_units'])} units."),
            estimated_impact="Prevents an imminent stockout and lost sales/service-level breach.",
        ))

    overstock = inventory_df[inventory_df["inventory_status"] == "overstock"]
    for _, row in overstock.sort_values("days_of_supply", ascending=False).head(6).iterrows():
        recs.append(dict(
            category="inventory",
            entity_type="product",
            entity_id=int(row["product_id"]),
            priority="medium",
            title=f"Reduce excess inventory for {row['sku']} ({row['name']})",
            description=(f"{row['days_of_supply']:.0f} days of supply on hand is well beyond typical coverage "
                          f"needs, tying up working capital in {row['category']}."),
            estimated_impact=f"Freeing this capital could fund ~${row['on_hand_units'] * 0:.0f} in other priorities "
                              f"(review against holding-cost assumptions).",
        ))

    # --- Risk-driven ---
    for _, row in risk_df[risk_df["risk_level"].isin(["critical", "high"])].sort_values(
            "risk_probability", ascending=False).head(10).iterrows():
        top_factor = row["explanation"][0]["detail"] if row.get("explanation") else "elevated risk factors"
        recs.append(dict(
            category="procurement",
            entity_type="product",
            entity_id=int(row["product_id"]),
            priority="critical" if row["risk_level"] == "critical" else "high",
            title=f"Stockout risk mitigation needed: {row['sku']}",
            description=(f"Model estimates a {row['risk_probability']*100:.0f}% probability of stockout. "
                          f"Primary driver: {top_factor}"),
            estimated_impact="Early procurement action can avoid unplanned expedited freight and customer impact.",
        ))

    # --- Anomaly-driven ---
    for a in sorted(anomalies, key=lambda x: -x.get("anomaly_score", 0))[:8]:
        if a["severity"] in ("high", "medium"):
            recs.append(dict(
                category="quality" if a["metric_name"] == "defect_rate" else "supplier" if a["entity_type"] == "supplier" else "inventory",
                entity_type=a["entity_type"],
                entity_id=a["entity_id"],
                priority="high" if a["severity"] == "high" else "medium",
                title=f"Investigate anomaly: {a['metric_name'].replace('_',' ')}",
                description=a["description"],
                estimated_impact="Early root-cause investigation limits downstream disruption.",
            ))

    return recs

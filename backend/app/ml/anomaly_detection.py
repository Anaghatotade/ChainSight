"""
Anomaly Detection
=================
Detects unusual behavior across three operational surfaces:
  1. Demand anomalies per product (sudden spikes/collapses vs its own history)
  2. Supplier delivery-delay anomalies (vs supplier's own historical delay distribution)
  3. Quality/defect-rate anomalies per supplier

Approach: IsolationForest for multivariate outlier scoring, combined with
simple rolling mean/std bounds so every flagged anomaly has a plain-English,
statistically grounded explanation (expected range vs observed value).
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def detect_demand_anomalies(demand_df: pd.DataFrame, product_id: int, contamination=0.05):
    """
    demand_df: columns ['demand_date','units_demanded'] for a single product (aggregated across warehouses)
    Returns list of anomaly dicts.
    """
    df = demand_df.sort_values("demand_date").reset_index(drop=True)
    if len(df) < 14:
        return []

    df["roll_mean"] = df["units_demanded"].rolling(14, min_periods=7).mean()
    df["roll_std"] = df["units_demanded"].rolling(14, min_periods=7).std().fillna(0) + 1e-6
    overall_mean = df["units_demanded"].mean()
    df["roll_mean"] = df["roll_mean"].fillna(overall_mean)
    df["z"] = (df["units_demanded"] - df["roll_mean"]) / df["roll_std"]

    features = df[["units_demanded", "z"]].fillna(0).values
    if len(features) < 20:
        model_scores = np.zeros(len(features))
    else:
        iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=150)
        iso.fit(features)
        model_scores = -iso.score_samples(features)  # higher = more anomalous

    anomalies = []
    threshold = np.percentile(model_scores, 100 - contamination * 100) if len(model_scores) > 20 else 999
    for i, row in df.iterrows():
        is_stat_outlier = abs(row["z"]) > 2.5
        is_model_outlier = model_scores[i] >= threshold if len(model_scores) > 20 else False
        if is_stat_outlier or is_model_outlier:
            severity = "high" if abs(row["z"]) > 4 else ("medium" if abs(row["z"]) > 3 else "low")
            direction = "spike" if row["z"] > 0 else "drop"
            anomalies.append(dict(
                entity_type="product",
                entity_id=int(product_id),
                metric_name="daily_demand",
                detected_date=row["demand_date"],
                metric_value=float(row["units_demanded"]),
                expected_range_low=float(max(0, row["roll_mean"] - 2 * row["roll_std"])),
                expected_range_high=float(row["roll_mean"] + 2 * row["roll_std"]),
                anomaly_score=float(round(model_scores[i] if len(model_scores) > 20 else abs(row["z"]) / 5, 4)),
                severity=severity,
                description=(f"Demand {direction} of {int(row['units_demanded'])} units vs. expected "
                             f"{int(row['roll_mean'])} ± {int(2*row['roll_std'])} (14-day rolling range)."),
            ))
    return anomalies


def detect_supplier_delay_anomalies(po_df: pd.DataFrame, supplier_id: int, supplier_name: str, contamination=0.08):
    """
    po_df: columns ['order_date','delay_days'] for one supplier's delivered POs
    """
    df = po_df.dropna(subset=["delay_days"]).sort_values("order_date").reset_index(drop=True)
    if len(df) < 10:
        return []

    mean_delay = df["delay_days"].mean()
    std_delay = df["delay_days"].std() + 1e-6

    features = df[["delay_days"]].values
    iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=150)
    iso.fit(features)
    scores = -iso.score_samples(features)
    threshold = np.percentile(scores, 100 - contamination * 100)

    anomalies = []
    for i, row in df.iterrows():
        z = (row["delay_days"] - mean_delay) / std_delay
        if scores[i] >= threshold and row["delay_days"] > mean_delay:
            severity = "high" if row["delay_days"] > mean_delay + 3 * std_delay else "medium"
            anomalies.append(dict(
                entity_type="supplier",
                entity_id=int(supplier_id),
                metric_name="delivery_delay_days",
                detected_date=row["order_date"],
                metric_value=float(row["delay_days"]),
                expected_range_low=0.0,
                expected_range_high=float(round(mean_delay + 2 * std_delay, 2)),
                anomaly_score=float(round(scores[i], 4)),
                severity=severity,
                description=(f"{supplier_name} delivered {row['delay_days']:.0f} days late vs. "
                              f"its typical {mean_delay:.1f} ± {std_delay:.1f} day pattern."),
            ))
    return anomalies


def detect_quality_anomalies(quality_df: pd.DataFrame, supplier_id: int, supplier_name: str):
    """
    quality_df: columns ['inspection_date','defect_rate'] for one supplier
    """
    df = quality_df.sort_values("inspection_date").reset_index(drop=True)
    if len(df) < 8:
        return []
    mean_rate = df["defect_rate"].mean()
    std_rate = df["defect_rate"].std() + 1e-6

    anomalies = []
    for _, row in df.iterrows():
        z = (row["defect_rate"] - mean_rate) / std_rate
        if z > 2.2:
            severity = "high" if z > 3.5 else "medium"
            anomalies.append(dict(
                entity_type="supplier",
                entity_id=int(supplier_id),
                metric_name="defect_rate",
                detected_date=row["inspection_date"],
                metric_value=float(row["defect_rate"]),
                expected_range_low=0.0,
                expected_range_high=float(round(mean_rate + 2 * std_rate, 4)),
                anomaly_score=float(round(z / 5, 4)),
                severity=severity,
                description=(f"{supplier_name} defect rate of {row['defect_rate']*100:.1f}% is well above "
                              f"its typical {mean_rate*100:.1f}% baseline."),
            ))
    return anomalies

"""
Stockout Risk Scoring
=====================
Trains a RandomForestClassifier on historical (product, warehouse, day)
snapshots to predict P(stockout within next 14 days), using operationally
meaningful features: days-of-supply, demand volatility, supplier reliability,
lead-time variability, and safety-stock coverage.

Explainability: rather than opaque black-box output, each prediction is
paired with a per-feature contribution breakdown. We use the model's global
feature_importances_ combined with how far each feature sits from a "safe"
reference value (z-score vs. the training population) to produce a signed,
human-readable contribution per factor -- i.e. "why" a SKU is risky, not
just a number. This mirrors the spirit of SHAP-style local attributions
without the added runtime dependency.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

FEATURES = [
    "days_of_supply", "demand_cv", "lead_time_days", "lead_time_cv",
    "supplier_on_time_rate", "safety_stock_ratio", "defect_rate", "recent_trend_pct",
]

FEATURE_LABELS = {
    "days_of_supply": "Days of supply on hand",
    "demand_cv": "Demand volatility (coefficient of variation)",
    "lead_time_days": "Supplier lead time",
    "lead_time_cv": "Lead time variability",
    "supplier_on_time_rate": "Supplier on-time delivery rate",
    "safety_stock_ratio": "Safety stock coverage ratio",
    "defect_rate": "Supplier defect rate",
    "recent_trend_pct": "Recent demand trend",
}

# direction: True means "higher value -> higher risk"
RISK_DIRECTION = {
    "days_of_supply": False,
    "demand_cv": True,
    "lead_time_days": True,
    "lead_time_cv": True,
    "supplier_on_time_rate": False,
    "safety_stock_ratio": False,
    "defect_rate": True,
    "recent_trend_pct": True,
}


@dataclass
class RiskModelBundle:
    model: RandomForestClassifier
    feature_means: dict
    feature_stds: dict
    feature_importances: dict


def train_risk_model(training_df: pd.DataFrame) -> RiskModelBundle:
    """
    training_df must contain FEATURES columns + 'label' (0/1 stockout within horizon)
    """
    X = training_df[FEATURES].fillna(0)
    y = training_df["label"].astype(int)

    if y.nunique() < 2:
        # degenerate case (no positive examples) -> train a trivial model
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        # add one synthetic positive to allow fit
        X_aug = pd.concat([X, X.iloc[[0]]], ignore_index=True)
        y_aug = pd.concat([y, pd.Series([1])], ignore_index=True)
        model.fit(X_aug, y_aug)
    else:
        model = RandomForestClassifier(n_estimators=300, max_depth=8, random_state=42,
                                        class_weight="balanced", n_jobs=-1)
        model.fit(X, y)

    means = X.mean().to_dict()
    stds = (X.std() + 1e-6).to_dict()
    importances = dict(zip(FEATURES, model.feature_importances_.tolist()))
    return RiskModelBundle(model=model, feature_means=means, feature_stds=stds, feature_importances=importances)


def score_instance(bundle: RiskModelBundle, feature_row: dict):
    x = pd.DataFrame([{f: feature_row.get(f, 0) for f in FEATURES}])
    proba = float(bundle.model.predict_proba(x)[0][1]) if bundle.model.n_classes_ > 1 else float(bundle.model.predict_proba(x)[0][0])

    contributions = []
    for f in FEATURES:
        val = feature_row.get(f, bundle.feature_means[f])
        z = (val - bundle.feature_means[f]) / bundle.feature_stds[f]
        higher_is_riskier = RISK_DIRECTION[f]
        signed_z = z if higher_is_riskier else -z
        contribution = signed_z * bundle.feature_importances[f]
        contributions.append((f, contribution, val, signed_z))

    contributions.sort(key=lambda c: abs(c[1]), reverse=True)
    top_factors = []
    for f, contribution, val, signed_z in contributions[:5]:
        direction = "increases_risk" if contribution > 0 else "decreases_risk"
        detail = _explain_factor(f, val, signed_z)
        top_factors.append(dict(
            factor=FEATURE_LABELS[f],
            contribution=round(float(contribution), 4),
            direction=direction,
            detail=detail,
        ))

    return proba, top_factors


def _explain_factor(feature: str, value: float, signed_z: float) -> str:
    if feature == "days_of_supply":
        return f"Only {value:.1f} days of inventory remain on hand." if signed_z > 0 else f"{value:.1f} days of supply on hand is comfortably above typical needs."
    if feature == "demand_cv":
        return f"Demand volatility is high (CV={value:.2f}), making stockouts harder to plan around." if signed_z > 0 else f"Demand is relatively stable (CV={value:.2f})."
    if feature == "lead_time_days":
        return f"Supplier lead time of {value:.0f} days leaves a long exposure window." if signed_z > 0 else f"Short supplier lead time of {value:.0f} days limits exposure."
    if feature == "lead_time_cv":
        return f"Lead times from this supplier are unpredictable (CV={value:.2f})." if signed_z > 0 else "Lead times from this supplier are consistent."
    if feature == "supplier_on_time_rate":
        return f"Supplier on-time rate is only {value*100:.0f}%, increasing delay risk." if signed_z > 0 else f"Supplier on-time rate of {value*100:.0f}% is strong."
    if feature == "safety_stock_ratio":
        return f"Safety stock covers only {value:.2f}x expected demand variability." if signed_z > 0 else f"Safety stock coverage ratio of {value:.2f}x is healthy."
    if feature == "defect_rate":
        return f"Supplier defect rate of {value*100:.1f}% may reduce usable received quantity." if signed_z > 0 else f"Supplier defect rate of {value*100:.1f}% is low."
    if feature == "recent_trend_pct":
        return f"Demand has trended up {value*100:.1f}% recently, straining current stock plans." if signed_z > 0 else f"Recent demand trend of {value*100:+.1f}% is not adding pressure."
    return ""


def risk_level_from_probability(p: float) -> str:
    if p >= 0.7:
        return "critical"
    if p >= 0.45:
        return "high"
    if p >= 0.2:
        return "medium"
    return "low"

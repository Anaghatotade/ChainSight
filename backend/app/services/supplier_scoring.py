"""
Supplier Performance Scoring
============================
Composite scorecard combining four weighted dimensions, each normalized to
0-100 across the supplier population so scores are comparable:

  - On-time delivery rate      (35%)
  - Quality (inverse defect rate) (30%)
  - Cost competitiveness (inverse cost index) (20%)
  - Lead time consistency (inverse variability) (15%)

Grades: A (>=85), B (>=70), C (>=55), D (<55)
"""
import pandas as pd
import numpy as np

WEIGHTS = {
    "on_time": 0.35,
    "quality": 0.30,
    "cost": 0.20,
    "consistency": 0.15,
}


def _normalize(series: pd.Series, invert=False) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        norm = pd.Series([70.0] * len(series), index=series.index)
    else:
        norm = (series - lo) / (hi - lo) * 100
    if invert:
        norm = 100 - norm
    return norm


def score_suppliers(perf_df: pd.DataFrame) -> pd.DataFrame:
    """
    perf_df columns required: supplier_id, name, region, category,
      on_time_rate, avg_delay_days, avg_defect_rate, cost_index, lead_time_std_days
    """
    df = perf_df.copy()
    df["on_time_rate"] = df["on_time_rate"].fillna(0.5)
    df["avg_defect_rate"] = df["avg_defect_rate"].fillna(df["avg_defect_rate"].median() or 0.03)
    df["cost_index"] = df["cost_index"].fillna(1.0)
    df["lead_time_std_days"] = df["lead_time_std_days"].fillna(df["lead_time_std_days"].median() or 3)

    df["score_on_time"] = _normalize(df["on_time_rate"])
    df["score_quality"] = _normalize(df["avg_defect_rate"], invert=True)
    df["score_cost"] = _normalize(df["cost_index"], invert=True)
    df["score_consistency"] = _normalize(df["lead_time_std_days"], invert=True)

    df["composite_score"] = (
        df["score_on_time"] * WEIGHTS["on_time"] +
        df["score_quality"] * WEIGHTS["quality"] +
        df["score_cost"] * WEIGHTS["cost"] +
        df["score_consistency"] * WEIGHTS["consistency"]
    ).round(2)

    def grade(s):
        if s >= 85:
            return "A"
        if s >= 70:
            return "B"
        if s >= 55:
            return "C"
        return "D"

    df["grade"] = df["composite_score"].apply(grade)
    return df

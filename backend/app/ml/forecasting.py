"""
Demand Forecasting
==================
Uses a RandomForestRegressor over engineered lag + calendar features to
forecast future daily demand per (product, warehouse). Falls back to a
Holt-Winters-style exponential smoothing baseline when history is too
short for a supervised model.

Also computes backtested MAE / MAPE on a held-out tail of history so the
frontend can show a genuine accuracy metric (not a hardcoded number).
"""
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

FEATURE_LAGS = [1, 2, 3, 7, 14, 21, 28]
ROLLING_WINDOWS = [7, 14, 30]


def build_features(series: pd.DataFrame) -> pd.DataFrame:
    """series: DataFrame with columns ['ds','y'] sorted by ds ascending."""
    df = series.copy().reset_index(drop=True)
    df["dow"] = pd.to_datetime(df["ds"]).dt.dayofweek
    df["doy"] = pd.to_datetime(df["ds"]).dt.dayofyear
    df["month"] = pd.to_datetime(df["ds"]).dt.month
    df["sin_doy"] = np.sin(2 * np.pi * df["doy"] / 365.0)
    df["cos_doy"] = np.cos(2 * np.pi * df["doy"] / 365.0)

    for lag in FEATURE_LAGS:
        df[f"lag_{lag}"] = df["y"].shift(lag)
    for w in ROLLING_WINDOWS:
        df[f"roll_mean_{w}"] = df["y"].shift(1).rolling(w).mean()
        df[f"roll_std_{w}"] = df["y"].shift(1).rolling(w).std()
    df["trend_idx"] = np.arange(len(df))
    return df


def train_and_forecast(history_df: pd.DataFrame, horizon_days: int = 30, backtest_days: int = 21):
    """
    history_df: columns ['ds' (date), 'y' (units)]
    Returns: (forecast_df, metrics dict)
    """
    history_df = history_df.sort_values("ds").reset_index(drop=True)
    n = len(history_df)

    feature_cols = None
    metrics = {"mae": None, "mape": None, "model": "random_forest"}

    if n < 45:
        # Not enough history for supervised model -> simple exponential smoothing
        y = history_df["y"].values.astype(float)
        alpha = 0.3
        level = y[0]
        levels = [level]
        for v in y[1:]:
            level = alpha * v + (1 - alpha) * level
            levels.append(level)
        last_level = levels[-1]
        resid_std = float(np.std(y - np.array(levels))) if n > 1 else max(1.0, last_level * 0.2)
        forecast_dates = [history_df["ds"].iloc[-1] + timedelta(days=i + 1) for i in range(horizon_days)]
        forecast_vals = [max(0.0, last_level) for _ in range(horizon_days)]
        forecast_df = pd.DataFrame({
            "ds": forecast_dates,
            "yhat": forecast_vals,
            "yhat_lower": [max(0.0, v - 1.28 * resid_std) for v in forecast_vals],
            "yhat_upper": [v + 1.28 * resid_std for v in forecast_vals],
        })
        metrics["model"] = "exp_smoothing_fallback"
        return forecast_df, metrics

    feat_df = build_features(history_df)
    feature_cols = [c for c in feat_df.columns if c not in ("ds", "y")]
    feat_df_clean = feat_df.dropna().reset_index(drop=True)

    # --- backtest split ---
    if len(feat_df_clean) > backtest_days + 30:
        train = feat_df_clean.iloc[:-backtest_days]
        test = feat_df_clean.iloc[-backtest_days:]
        model_bt = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
        model_bt.fit(train[feature_cols], train["y"])
        preds = model_bt.predict(test[feature_cols])
        actual = test["y"].values
        mae = float(np.mean(np.abs(preds - actual)))
        denom = np.where(actual == 0, 1, actual)
        mape = float(np.mean(np.abs(preds - actual) / denom) * 100)
        metrics["mae"] = round(mae, 2)
        metrics["mape"] = round(min(mape, 999), 2)

    # --- train final model on full history ---
    model = RandomForestRegressor(n_estimators=300, max_depth=12, random_state=42, n_jobs=-1)
    model.fit(feat_df_clean[feature_cols], feat_df_clean["y"])

    resid = feat_df_clean["y"] - model.predict(feat_df_clean[feature_cols])
    resid_std = float(np.std(resid)) + 1e-6

    # iterative multi-step forecasting
    working = history_df.copy()
    forecast_rows = []
    for step in range(horizon_days):
        feat = build_features(working)
        last_row = feat.iloc[[-1]][feature_cols]
        # for the *next* day we need features computed as if next day appended;
        # simpler: predict using last available row's lag structure shifted by one day
        next_date = working["ds"].iloc[-1] + timedelta(days=1)
        temp = pd.concat([working, pd.DataFrame({"ds": [next_date], "y": [np.nan]})], ignore_index=True)
        feat_next = build_features(temp)
        x_next = feat_next.iloc[[-1]][feature_cols].ffill(axis=0)
        x_next = x_next.fillna(0)
        pred = float(model.predict(x_next)[0])
        pred = max(0.0, pred)

        widen = 1 + step * 0.03  # widen interval further into the future
        forecast_rows.append({
            "ds": next_date,
            "yhat": pred,
            "yhat_lower": max(0.0, pred - 1.28 * resid_std * widen),
            "yhat_upper": pred + 1.28 * resid_std * widen,
        })
        working = pd.concat([working, pd.DataFrame({"ds": [next_date], "y": [pred]})], ignore_index=True)

    forecast_df = pd.DataFrame(forecast_rows)
    return forecast_df, metrics

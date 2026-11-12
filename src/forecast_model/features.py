"""Engineered features. Every feature uses only information published before the cutoff."""
from __future__ import annotations

import numpy as np
import pandas as pd

from forecast_model.data import OBS_LAG_DAYS, Cutoff


def target_column(metric: str) -> str:
    return f"obs_{metric}_f"


def build_features(df: pd.DataFrame, metric: str, cutoff: Cutoff) -> tuple[pd.DataFrame, list[str]]:
    # Rows must be one per station per consecutive day for the lags below.
    df = df.sort_values(["station_id", "date"]).copy()
    target = target_column(metric)
    cols = [f"{s}_{metric}_f" for s in cutoff.sources]
    features = list(cols)

    forecasts = df[cols]
    df["ens_mean"] = forecasts.mean(axis=1)
    df["ens_median"] = forecasts.median(axis=1)
    df["ens_spread"] = forecasts.std(axis=1)
    df["ens_range"] = forecasts.max(axis=1) - forecasts.min(axis=1)
    features += ["ens_mean", "ens_median", "ens_spread", "ens_range"]

    for source, col in zip(cutoff.sources, cols):
        # Errors are only known once the observation is published (OBS_LAG_DAYS).
        error = (df[col] - df[target]).groupby(df["station_id"]).shift(OBS_LAG_DAYS)
        for window in (7, 30):
            name = f"{source}_bias_{window}d"
            df[name] = error.groupby(df["station_id"]).transform(
                lambda s, w=window: s.rolling(w, min_periods=max(3, w // 3)).mean())
            features.append(name)
        df[f"{source}_debiased"] = df[col] - df[f"{source}_bias_30d"]
        features.append(f"{source}_debiased")

    df["persistence"] = df.groupby("station_id")[target].shift(OBS_LAG_DAYS)
    day = pd.to_datetime(df["date"]).dt.day_of_year
    df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * day / 365.25), np.cos(2 * np.pi * day / 365.25)
    df["week"] = pd.to_datetime(df["date"]).dt.isocalendar().week.astype(int)
    features += ["persistence", "doy_sin", "doy_cos"]
    return df, features

"""Simple baselines and the error table every method is scored with."""
from __future__ import annotations

import numpy as np
import pandas as pd

from forecast_model.data import CITY, Cutoff, label


def climatology(history: pd.DataFrame, target: str) -> pd.Series:
    return history.groupby(["station_id", "week"])[target].mean()


def baselines(frame: pd.DataFrame, metric: str, cutoff: Cutoff, clim: pd.Series) -> dict[str, pd.Series]:
    out = {label(s): frame[f"{s}_{metric}_f"] for s in cutoff.sources}
    out[f"Average of {len(cutoff.sources)} sources"] = frame["ens_mean"]
    out["Average, bias-corrected (30d)"] = frame[[f"{s}_debiased" for s in cutoff.sources]].mean(axis=1)
    out["Persistence (2 days earlier)"] = frame["persistence"]
    keys = pd.MultiIndex.from_frame(frame[["station_id", "week"]])
    out["Climatology"] = pd.Series(clim.reindex(keys).to_numpy(), frame.index)
    return out


def common_days(methods: dict[str, pd.Series]) -> pd.Series:
    """Rows where every method has a prediction, so all are scored on the same days."""
    return pd.concat(methods.values(), axis=1).notna().all(axis=1)


def score(methods: dict[str, pd.Series], actual: pd.Series, stations: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    keep = common_days(methods) & actual.notna()
    actual, stations = actual[keep], stations[keep]
    rows, per_city = [], {}
    for name, pred in methods.items():
        pred = pred[keep]
        err = pred - actual
        # Observations are whole degrees; round every method so integer forecasts (MOS)
        # and continuous ones (ML) are scored the same way on exact/within-1 hits.
        rounded = np.round(pred) - actual
        rows.append({"method": name, "mae": float(np.mean(np.abs(err))),
                     "rmse": float(np.sqrt(np.mean(err ** 2))), "bias": float(err.mean()),
                     "exact": float(np.mean(rounded == 0)), "within_1f": float(np.mean(np.abs(rounded) <= 1)),
                     "n": int(len(err))})
        per_city[name] = err.abs().groupby(stations).mean()
    table = pd.DataFrame(rows).sort_values("mae").reset_index(drop=True)
    return table, pd.DataFrame(per_city).rename(index=CITY)

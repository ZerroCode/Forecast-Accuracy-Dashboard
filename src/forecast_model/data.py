"""Dataset loading, prediction cutoffs, and the fixed time split."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Cutoff:
    """The moment a prediction for day D is made, and what was published by then."""
    name: str
    description: str
    sources: tuple[str, ...]   # dataset column prefixes available at the cutoff
    prices_dir: str            # Kalshi prices snapshotted at the same moment


CUTOFFS = {
    # NWS MOS 12Z comes out ~16:00 UTC and day1 forecasts include evening runs, so
    # only the 00Z MOS run and ~48h model forecasts exist an hour after Kalshi opens.
    # HRRR does not forecast that far ahead.
    "open": Cutoff("open", "11 AM ET the day before (1 h after Kalshi opens)",
                   ("mos00", "gfs_day2", "icon_day2", "gem_day2", "ecmwf_day2"), "kalshi_prices_open"),
    "midnight": Cutoff("midnight", "Midnight before the measured day",
                       ("mos", "gfs_day1", "hrrr_day1", "icon_day1", "gem_day1", "ecmwf_day1"), "kalshi_prices"),
}

# Features may use observations through D-2 only: the official report for D-1 is
# published the morning of D, after both cutoffs.
OBS_LAG_DAYS = 2

MODEL_NAMES = {"mos": "NWS MOS", "mos00": "NWS MOS", "gfs": "GFS", "hrrr": "HRRR", "icon": "ICON",
               "gem": "GEM", "ecmwf": "ECMWF"}
CITY = {"nyc_central_park": "New York", "los_angeles_lax": "Los Angeles", "chicago_midway": "Chicago",
        "miami_international": "Miami", "dallas_fort_worth": "Dallas", "seattle_tacoma": "Seattle",
        "boston_logan": "Boston", "san_francisco_sfo": "San Francisco"}

# Split by time, never randomly. START is the first date with all sources.
# The test period is scored once, after every choice is made on validation.
START, VAL_START, TEST_START = "2024-02-05", "2025-07-01", "2026-01-01"


def label(source: str) -> str:
    return MODEL_NAMES[source.split("_")[0]]


def load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = {f"{s}_high_f" for c in CUTOFFS.values() for s in c.sources} - set(df.columns)
    if missing:
        raise ValueError(f"{path} lacks {sorted(missing)}; run src/backfill_history.py and src/build_dataset.py")
    return df


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df[df["date"] >= START]
    return (df[df["date"] < VAL_START],
            df[(df["date"] >= VAL_START) & (df["date"] < TEST_START)],
            df[df["date"] >= TEST_START])

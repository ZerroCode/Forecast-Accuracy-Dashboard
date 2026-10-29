"""Join backfilled history into one row per station per day: data/history/dataset.csv.

Columns: forecasts from each source (inputs), NOAA observed highs/lows, and the
Kalshi settled value (the official market answer) where a market existed.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_rows(paths) -> list[dict]:
    rows = []
    for path in sorted(paths):
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def build(history_dir: Path) -> tuple[list[str], list[dict]]:
    merged: dict[tuple, dict] = defaultdict(dict)
    fields = ["station_id", "date"]
    for source in ("ncei", "mos", "open_meteo"):
        for row in read_rows(history_dir.glob(f"{source}/**/*.csv")):
            merged[(row["station_id"], row["date"])].update(row)
            fields += [name for name in row if name not in fields]

    # One settled value per event; every market in the event reports the same one.
    for row in read_rows(history_dir.glob("kalshi/*.csv")):
        if row["date"] and row["settled_value_f"]:
            merged[(row["station_id"], row["date"])][f"kalshi_{row['metric']}_f"] = row["settled_value_f"]
    fields += ["kalshi_high_f", "kalshi_low_f"]

    # Weather-source rows define the date range; Kalshi-only days are dropped.
    rows = [{"station_id": key[0], "date": key[1], **values}
            for key, values in sorted(merged.items()) if "obs_high_f" in values or "mos_high_f" in values]
    return fields, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", type=Path, default=PROJECT_ROOT / "data/history")
    args = parser.parse_args()
    fields, rows = build(args.history_dir)
    output = args.history_dir / "dataset.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} station-days with {len(fields)} columns to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

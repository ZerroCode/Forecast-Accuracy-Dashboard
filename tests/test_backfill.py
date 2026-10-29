from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import backfill_history
from backfill_history import extrema, mos_rows, open_meteo_rows, ticker_date, write_csv
from build_dataset import build
from weather_pipeline.config import load_stations

NYC = load_stations(ROOT / "config/stations.csv")[0]

MOS_CSV = """runtime,ftime,model,n_x,tmp
2024-02-29 12:00:00,2024-03-01 12:00:00,GFS,29.0,30
2024-02-29 12:00:00,2024-03-02 00:00:00,GFS,44.0,40
2024-02-29 12:00:00,2024-03-01 15:00:00,GFS,,35
2024-03-01 00:00:00,2024-03-01 12:00:00,GFS,10.0,30
"""


class BackfillTests(unittest.TestCase):
    def test_ticker_date_handles_current_and_legacy_tickers(self):
        self.assertEqual(ticker_date("KXHIGHNY-26OCT20"), "2026-10-20")
        self.assertEqual(ticker_date("HIGHNY-21AUG06"), "2021-08-06")
        self.assertEqual(ticker_date("KXHIGHNY-BAD"), "")

    def test_settled_value_ignores_bracket_labels(self):
        self.assertEqual(backfill_history.settled_value("67.00"), "67.0")
        self.assertEqual(backfill_history.settled_value("70° to 71°"), "")
        self.assertEqual(backfill_history.settled_value(None), "")

    def test_extrema_rejects_partial_days(self):
        self.assertEqual(extrema(list(range(24))), (23, 0))
        self.assertEqual(extrema(list(range(23))), ("", ""))
        self.assertEqual(extrema([1] * 23 + [None]), ("", ""))

    def test_mos_uses_previous_day_12z_run(self):
        with patch.object(backfill_history, "get_text", return_value=MOS_CSV):
            rows = mos_rows(NYC, date(2024, 3, 1), date(2024, 3, 1))
        # The 00Z run's 10.0 must be ignored; only the 12Z run on D-1 counts.
        self.assertEqual(rows, [{"station_id": "nyc_central_park", "date": "2024-03-01",
                                 "mos_high_f": 44.0, "mos_low_f": 29.0}])

    def test_open_meteo_uses_local_standard_day(self):
        # NYC standard day 2024-07-01 is 05:00Z to 05:00Z, even during DST.
        times = [f"2024-07-0{d}T{h:02d}:00" for d in (1, 2) for h in range(24)]
        values = list(range(48))
        hourly = {"time": times}
        for model in backfill_history.OPEN_METEO_MODELS:
            for lead in backfill_history.OPEN_METEO_LEADS:
                hourly[f"temperature_2m_{lead}_{model}"] = values
        with patch.object(backfill_history, "get_json", return_value={"hourly": hourly}):
            [row] = open_meteo_rows(NYC, date(2024, 7, 1), date(2024, 7, 1))
        self.assertEqual((row["gfs_day1_high_f"], row["gfs_day1_low_f"]), (28, 5))

    def test_build_joins_sources_and_kalshi_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory)
            key = {"station_id": "nyc_central_park", "date": "2024-03-01"}
            write_csv(history / "ncei/nyc.csv", ["station_id", "date", "obs_high_f", "obs_low_f"],
                      [{**key, "obs_high_f": "48", "obs_low_f": "30"}])
            write_csv(history / "mos/nyc/2024.csv", ["station_id", "date", "mos_high_f", "mos_low_f"],
                      [{**key, "mos_high_f": "44", "mos_low_f": "29"}])
            write_csv(history / "kalshi/KXHIGHNY.csv", backfill_history.KALSHI_FIELDS,
                      [{**key, "metric": "high", "settled_value_f": "48"},
                       {**key, "date": "2021-08-06", "metric": "high", "settled_value_f": "90"}])
            fields, rows = build(history)
        self.assertEqual(len(rows), 1)  # Kalshi-only dates are dropped
        self.assertEqual((rows[0]["obs_high_f"], rows[0]["mos_high_f"], rows[0]["kalshi_high_f"]),
                         ("48", "44", "48"))
        self.assertIn("kalshi_low_f", fields)


if __name__ == "__main__":
    unittest.main()

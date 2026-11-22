import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from collect_forecasts import configured_providers
from weather_pipeline.archive import read_archive
from weather_pipeline.config import load_stations
from weather_pipeline.providers.meteosource import fetch_forecast
from weather_pipeline.storage import upsert_jsonl
from weather_pipeline.windows import standard_day

STATION = load_stations(ROOT / "config/stations.csv")[0]
NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
TARGET = date(2026, 11, 1)  # Fall transition: 25-hour civil day, 24-hour standard day.
WINDOW = standard_day(TARGET, STATION.timezone)
SECRET = "test-meteosource-api"
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


class MeteosourceTests(unittest.TestCase):
    def test_free_daily_capture_uses_native_extrema_and_encrypted_storage(self):
        payload = {"timezone": STATION.timezone, "units": "us", "daily": {"data": [
            {"day": "2026-10-31", "all_day": {"temperature_max": 93, "temperature_min": 83}},
            {"day": str(TARGET), "all_day": {"temperature_max": 55, "temperature_min": 30}},
        ]}}
        fetch = Mock(return_value=payload)
        row, _, url = fetch_forecast(STATION, retrieved_at=NOW, api_key=SECRET, fetch_json=fetch)
        fetch.assert_called_once_with(url, headers={"X-API-Key": SECRET})
        self.assertEqual("/api/v1/free/point", urlsplit(url).path)
        self.assertEqual(["daily"], parse_qs(urlsplit(url).query)["sections"])
        self.assertEqual((55, 30), (row["forecast_high_f"], row["forecast_low_f"]))
        self.assertEqual("2026-11-02T05:00:00Z", row["window_end_utc"])
        self.assertNotIn(SECRET, str(row))
        env = {"METEOSOURCE_API_KEY": SECRET, "DATA_ENCRYPTION_KEY": KEY,
               "METEOSOURCE_ARCHIVAL_ALLOWED": "true", "METEOSOURCE_TIER": ""}
        with patch.dict(os.environ, env, clear=True), tempfile.TemporaryDirectory() as tmp:
            provider = next(p for p in configured_providers(NOW, quiet=True) if p.slug == "meteosource")
            path = provider.output_path(Path(tmp) / "forecast.jsonl")
            upsert_jsonl(path, [row], key_fields=("provider",), encryption_key=provider.archive_key)
            self.assertEqual([row], read_archive(path, key=KEY))
            self.assertNotIn(b"forecast_high_f", path.read_bytes())
            self.assertNotIn("meteosource", [p.slug for p in configured_providers(NOW, WINDOW, quiet=True)])

    def test_daily_response_must_match_units_zone_and_target(self):
        day = {"day": str(TARGET), "all_day": {"temperature_max": 45, "temperature_min": 40}}
        base = {"units": "us", "timezone": STATION.timezone, "daily": {"data": [day]}}
        for overrides in ({"units": "metric"}, {"timezone": "UTC"}, {"daily": {"data": []}},
                          {"daily": {"data": [day, day]}},
                          {"daily": {"data": [{**day, "all_day": {"temperature_max": 2, "temperature_min": 4}}]}}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                fetch_forecast(STATION, retrieved_at=NOW, api_key=SECRET, fetch_json=Mock(return_value=base | overrides))

    def test_hourly_market_requires_the_exact_window(self):
        hours = [{"date": (WINDOW.start + timedelta(hours=i)).replace(tzinfo=None).isoformat(),
                  "temperature": 40 + i} for i in range(24)]
        fetch = Mock(return_value={"units": "us", "timezone": "UTC", "hourly": {"data": hours}})
        kwargs = dict(retrieved_at=NOW, api_key=SECRET, tier="standard", window=WINDOW, fetch_json=fetch)
        row, _, url = fetch_forecast(STATION, **kwargs)
        self.assertEqual(["hourly"], parse_qs(urlsplit(url).query)["sections"])
        self.assertEqual(24, row["sample_count"])
        self.assertEqual((63, 40), (row["forecast_high_f"], row["forecast_low_f"]))
        hours.pop()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            fetch_forecast(STATION, **kwargs)
        fetch.reset_mock()
        with self.assertRaises(ValueError):
            fetch_forecast(STATION, **(kwargs | {"retrieved_at": WINDOW.start}))
        fetch.assert_not_called()

    def test_key_alone_leaves_archive_off_and_paid_tier_enables_market(self):
        with patch.dict(os.environ, {"METEOSOURCE_API_KEY": SECRET}, clear=True):
            self.assertNotIn("meteosource", [p.slug for p in configured_providers(NOW, quiet=True)])
            os.environ.update(METEOSOURCE_ARCHIVAL_ALLOWED="true", METEOSOURCE_TIER="standard")
            with self.assertRaisesRegex(ValueError, "DATA_ENCRYPTION_KEY"):
                configured_providers(NOW, WINDOW, quiet=True)
            os.environ["DATA_ENCRYPTION_KEY"] = KEY
            self.assertIn("meteosource", [p.slug for p in configured_providers(NOW, WINDOW, quiet=True)])

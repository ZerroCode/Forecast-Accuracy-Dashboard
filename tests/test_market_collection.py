from __future__ import annotations

import io
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from collect_forecasts import EnabledProvider, configured_providers
from collect_market_forecasts import collect_events, dated_path, pilot_wait_seconds, save_contracts
from weather_pipeline.config import load_stations
from weather_pipeline.http import RequestError
from weather_pipeline.kalshi import (KalshiClient, MarketEvent, MarketMapping, discover,
                                    event_date, load_mappings, normalize_contract)
from weather_pipeline.providers.open_meteo import build_url, normalize_response
from weather_pipeline.providers.nws import normalize_response as normalize_nws
from weather_pipeline.providers.openweathermap import normalize_response as normalize_owm
from weather_pipeline.providers.tomorrow_io import normalize_response as normalize_tomorrow
from weather_pipeline.storage import read_jsonl
from weather_pipeline.temperatures import sampled_extrema
from weather_pipeline.windows import standard_day, utc_text

STATIONS = load_stations(ROOT / "config/stations.csv")
MAPPING = MarketMapping(STATIONS[0], "KXHIGHNY", "high", "CLINYC")
OPEN = datetime(2026, 10, 25, 14, tzinfo=timezone.utc)
SERIES = {"ticker": "KXHIGHNY", "settlement_sources": [
    {"name": "The Weather Company", "url": "https://weather.com/kalshi"}],
    "contract_terms_url": "https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf"}


def market(mapping=MAPPING):
    event = f"{mapping.series}-26OCT26"
    word = "maximum" if mapping.metric == "high" else "minimum"
    return {
        "ticker": event + "-T75", "event_ticker": event,
        "open_time": utc_text(OPEN), "close_time": "2026-10-27T05:00:00Z",
        "rules_primary": f"If the {word} temperature recorded at New York City ({mapping.climate_code}) "
                         "for Oct 26, 2026, is greater than 75 degrees fahrenheit according to "
                         "The Weather Company, then the market resolves to Yes.",
        "rules_secondary": "Use the final source value.", "status": "active",
    }


def event(mapping=MAPPING):
    contract = normalize_contract(mapping, market(mapping), SERIES, OPEN)
    return MarketEvent(mapping, contract["event_ticker"], OPEN,
                       standard_day(date(2026, 10, 26), mapping.station.timezone), [contract])


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class WindowTests(unittest.TestCase):
    def test_pilot_uses_eastern_opening_and_never_waits_for_tomorrow(self):
        for month, hour in ((1, 14), (7, 13)):
            start = datetime(2026, month, 20, hour, 55, tzinfo=timezone.utc)
            self.assertEqual(900, pilot_wait_seconds(start))
            self.assertEqual(0, pilot_wait_seconds(start - timedelta(hours=1)))
            self.assertEqual(60, pilot_wait_seconds(start + timedelta(minutes=14)))
            self.assertEqual(0, pilot_wait_seconds(start + timedelta(minutes=15)))

    def test_standard_day_is_24_hours_across_both_dst_transitions(self):
        for target in (date(2026, 3, 8), date(2026, 11, 1), date(2026, 10, 26)):
            with self.subTest(target=target):
                window = standard_day(target, "America/New_York")
                self.assertEqual(5, window.start.hour)
                self.assertEqual(timedelta(hours=24), window.end - window.start)
                samples = [(window.start + timedelta(hours=i), i) for i in range(24)]
                result = sampled_extrema(STATIONS[0], samples, retrieved_at=OPEN,
                                         step_hours=1, window=window)
                self.assertEqual(24, result["sample_count"])

    def test_all_sampled_adapters_use_explicit_market_date_and_window(self):
        window = standard_day(date(2026, 10, 26), "America/New_York")
        # Requested date is intentionally not tomorrow relative to retrieval time.
        retrieved = datetime(2026, 10, 24, 14, tzinfo=timezone.utc)
        points = [(window.start - timedelta(hours=1), 100)] + [
            (window.start + timedelta(hours=i), 40 + i) for i in range(24)] + [(window.end, -100)]
        payloads = [
            (normalize_response, {"hourly": {"time": [t.timestamp() for t, _ in points],
                                            "temperature_2m": [v for _, v in points]}}),
            (normalize_nws, {"properties": {"periods": [
                {"startTime": utc_text(t), "temperature": v, "temperatureUnit": "F"} for t, v in points]}}),
            (normalize_tomorrow, {"timelines": {"hourly": [
                {"time": utc_text(t), "values": {"temperature": v}} for t, v in points]}}),
        ]
        for normalize, payload in payloads:
            with self.subTest(adapter=normalize.__module__):
                row = normalize(STATIONS[0], payload, retrieved_at=retrieved, source_url="test", window=window)
                self.assertEqual(40, row["forecast_low_f"])
                self.assertEqual(63, row["forecast_high_f"])
                self.assertEqual("2026-10-26", row["target_date_local"])
                self.assertEqual("local_standard_midnight_to_midnight", row["daily_boundary"])
        three_hour = [(t, v) for t, v in points if t.hour % 3 == 0]
        row = normalize_owm(STATIONS[0], {"list": [{"dt": t.timestamp(), "main": {"temp": v}}
                                                    for t, v in three_hour]},
                            retrieved_at=retrieved, source_url="test", window=window)
        self.assertEqual(8, row["sample_count"])
        self.assertEqual(41, row["forecast_low_f"])
        self.assertEqual(62, row["forecast_high_f"])

    def test_open_meteo_market_request_is_hourly_utc(self):
        window = standard_day(date(2026, 10, 26), "America/New_York")
        query = parse_qs(urlsplit(build_url(STATIONS[0], window)).query)
        self.assertEqual(["temperature_2m"], query["hourly"])
        self.assertEqual(["UTC"], query["timezone"])
        self.assertEqual(["2026-10-27"], query["end_date"])
        self.assertNotIn("daily", query)


class DiscoveryTests(unittest.TestCase):
    def test_mappings_cover_high_low_and_correct_airports(self):
        mappings = load_mappings(ROOT / "config/kalshi_markets.json", STATIONS)
        self.assertEqual(16, len(mappings))
        self.assertEqual({"KMDW"}, {m.station.nws_station_id for m in mappings if m.climate_code == "CLIMDW"})
        self.assertEqual({"KDFW"}, {m.station.nws_station_id for m in mappings if m.climate_code == "CLIDFW"})
        self.assertEqual({"USW00014819"}, {m.station.ncei_station_id for m in mappings if m.climate_code == "CLIMDW"})
        self.assertEqual({"USW00003927"}, {m.station.ncei_station_id for m in mappings if m.climate_code == "CLIDFW"})
        self.assertEqual({s.station_id for s in STATIONS}, {m.station.station_id for m in mappings})
        self.assertNotIn("chicago_ohare", {s.station_id for s in STATIONS})
        self.assertNotIn("dallas_love_field", {s.station_id for s in STATIONS})

    def test_rule_mismatches_are_recorded_and_never_scheduled(self):
        changes = [
            {"rules_primary": market()["rules_primary"].replace("CLINYC", "CLIMDW")},
            {"rules_primary": market()["rules_primary"].replace("maximum", "minimum")},
            {"rules_primary": market()["rules_primary"].replace("Oct 26", "Oct 27")},
            {"rules_primary": market()["rules_primary"].replace("The Weather Company", "Unknown Source")},
            {"close_time": "2026-10-27T04:00:00Z"},
        ]
        for change in changes:
            with self.subTest(change=change):
                client = Mock()
                client.series.return_value = SERIES
                client.markets.return_value = [{**market(), **change}]
                events, rows, errors = discover(client, [MAPPING], OPEN)
                self.assertEqual([], events)
                self.assertTrue(rows[0]["validation_errors"])
                self.assertTrue(errors)

    def test_rules_and_opening_changes_get_new_versions_but_status_does_not(self):
        original = normalize_contract(MAPPING, market(), SERIES, OPEN)
        changed = normalize_contract(MAPPING, {**market(), "rules_secondary": "Revised rules"}, SERIES, OPEN)
        settled = normalize_contract(MAPPING, {**market(), "status": "finalized", "result": "yes"}, SERIES, OPEN)
        self.assertNotEqual(original["rules_version"], changed["rules_version"])
        self.assertEqual(original["rules_version"], settled["rules_version"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_contracts(root, [original, changed, settled])
            rows = read_jsonl(dated_path(root, "markets", "2026-10-26"))
            self.assertEqual(2, len(rows))
            self.assertIn("yes", [r["result"] for r in rows])

    def test_dst_fallback_allows_second_1am_close(self):
        chicago = next(station for station in STATIONS if station.station_id == "chicago_midway")
        mapping = replace(MAPPING, station=chicago, series="KXHIGHCHI", climate_code="CLIMDW")
        contract = normalize_contract(mapping, {
            "ticker": "KXHIGHCHI-26NOV01-T71",
            "event_ticker": "KXHIGHCHI-26NOV01",
            "open_time": "2026-10-31T14:00:00Z",
            "close_time": "2026-11-02T07:00:00Z",
            "rules_primary": ("If the maximum temperature recorded at Chicago (CLIMDW) for Nov 1, 2026, "
                              "is greater than 71 degrees fahrenheit according to The Weather Company, "
                              "then the market resolves to Yes."),
            "rules_secondary": "Use the final source value.",
            "status": "active",
        }, SERIES, OPEN)
        self.assertNotIn("close_time_does_not_match_configured_standard_day",
                         contract["validation_errors"])

    def test_close_times_used_by_kalshi_across_seasons_are_accepted(self):
        chicago = next(station for station in STATIONS if station.station_id == "chicago_midway")
        mapping = replace(MAPPING, station=chicago, series="KXHIGHCHI", climate_code="CLIMDW")
        # 1 AM CST after DST ends, and the earlier "11:59 PM ET" rule (10:59 PM CST).
        for day, opens, closes in (("Nov 3", "2026-11-02T15:00:00Z", "2026-11-04T07:00:00Z"),
                                   ("Feb 10", "2026-02-09T15:00:00Z", "2026-02-11T05:59:00Z")):
            month, number = day.split()
            ticker = f"KXHIGHCHI-26{month.upper()}{int(number):02d}"
            year = "2026"
            with self.subTest(day=day):
                contract = normalize_contract(mapping, {
                    "ticker": f"{ticker}-T71", "event_ticker": ticker,
                    "open_time": opens, "close_time": closes,
                    "rules_primary": (f"If the maximum temperature recorded at Chicago (CLIMDW) for "
                                      f"{month} {int(number)}, {year}, is greater than 71 degrees fahrenheit "
                                      "according to The Weather Company, then the market resolves to Yes."),
                    "rules_secondary": "Use the final source value.", "status": "active",
                }, SERIES, OPEN)
                self.assertEqual([], contract["validation_errors"])

    def test_pagination_includes_unopened_markets_and_detects_loops(self):
        fetch = Mock(side_effect=[{"markets": [market()], "cursor": "next"},
                                  {"markets": [{**market(), "ticker": "second"}], "cursor": ""}])
        client = KalshiClient(fetch_json=fetch, sleep=lambda _: None)
        self.assertEqual(2, len(client.markets("KXHIGHNY", OPEN)))
        query = parse_qs(urlsplit(fetch.call_args_list[1].args[0]).query)
        self.assertEqual(["next"], query["cursor"])
        self.assertNotIn("status", query)
        fetch.side_effect = None
        fetch.return_value = {"markets": [], "cursor": "loop"}
        with self.assertRaisesRegex(ValueError, "pagination"):
            client.markets("KXHIGHNY", OPEN)

    def test_bad_event_date_is_rejected(self):
        with self.assertRaises(ValueError):
            event_date("KXHIGHNY-26OCT26H1200", "KXHIGHNY")


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock(OPEN + timedelta(seconds=2))
        self.event = event()
        self.fetch = Mock(return_value=({
            "provider": "test", "station_id": STATIONS[0].station_id,
            "forecast_high_f": 70, "forecast_low_f": 50, **self.event.window.metadata(),
        }, {}, "test"))
        self.factory = lambda now, window: [EnabledProvider("test", self.fetch)]

    def collect(self, events=None):
        with patch("sys.stdout", new_callable=io.StringIO):
            return collect_events(events or [self.event], self.root, clock=self.clock,
                                  provider_factory=self.factory)

    def rows(self):
        return read_jsonl(dated_path(self.root, "market_forecasts", "2026-10-26"))

    def test_fresh_opening_precedes_late_recovery(self):
        old = replace(self.event, ticker="older", opens=OPEN - timedelta(hours=1))
        calls = []
        def fetch(station):
            calls.append(self.clock.value)
            self.clock.value += timedelta(minutes=6)
            return self.fetch.return_value
        self.factory = lambda now, window: [EnabledProvider("test", fetch)]
        self.collect([old, self.event])
        saved = {r["event_ticker"]: r for r in self.rows()}
        self.assertEqual(2, len(calls))
        self.assertTrue(saved[self.event.ticker]["eligible_for_opening_comparison"])
        self.assertFalse(saved["older"]["eligible_for_opening_comparison"])

    def test_before_open_makes_no_requests(self):
        self.clock.value = OPEN - timedelta(seconds=1)
        self.assertEqual([], self.collect())
        self.fetch.assert_not_called()
        self.assertEqual([], self.rows())

    def test_high_low_reuse_request_and_repeated_runs_preserve_first_snapshot(self):
        low = event(replace(MAPPING, series="KXLOWTNYC", metric="low"))
        self.assertEqual([], self.collect([self.event, low]))
        self.assertEqual(1, self.fetch.call_count)
        rows = self.rows()
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["eligible_for_opening_comparison"] for row in rows))
        self.clock.value += timedelta(hours=1)
        self.collect([self.event, low])
        self.assertEqual(rows, self.rows())
        self.assertEqual(1, self.fetch.call_count)

    def test_different_openings_do_not_share_forecasts(self):
        later = event(replace(MAPPING, series="KXLOWTNYC", metric="low"))
        later.opens += timedelta(seconds=1)
        self.collect([self.event, later])
        self.assertEqual(2, self.fetch.call_count)

    def test_encrypted_provider_reuses_snapshots_without_publishing_temperatures(self):
        secret = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
        self.fetch.return_value = ({
            "provider": "visual_crossing", "forecast_high_f": 71.25,
            **self.event.window.metadata(),
        }, {}, "test")
        provider = EnabledProvider("visual_crossing", self.fetch, archive_key=secret)
        self.factory = lambda now, window: [provider]
        low = event(replace(MAPPING, series="KXLOWTNYC", metric="low"))
        self.assertEqual([], self.collect([self.event, low]))
        self.assertEqual([], self.collect([self.event, low]))
        self.assertEqual(1, self.fetch.call_count)
        self.assertEqual([], self.rows())
        encrypted = provider.output_path(dated_path(self.root, "market_forecasts", "2026-10-26"))
        rows = read_jsonl(encrypted, encryption_key=secret)
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["eligible_for_opening_comparison"] for row in rows))
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"forecast_high_f", path.read_bytes())
                self.assertNotIn(secret.encode(), path.read_bytes())

    def test_late_request_uses_response_time_and_is_not_backdated(self):
        def fetch(station):
            self.clock.value += timedelta(minutes=15)
            return ({"provider": "test", **self.event.window.metadata()}, {}, "test")
        self.fetch.side_effect = fetch
        self.collect()
        row = self.rows()[0]
        self.assertEqual("late", row["capture_status"])
        self.assertEqual(902, row["seconds_after_market_open"])
        self.assertFalse(row["eligible_for_opening_comparison"])
        self.assertEqual(utc_text(self.clock()), row["retrieved_at_utc"])

    def test_after_measurement_start_is_missed_not_historical_backfill(self):
        self.clock.value = self.event.window.start
        self.collect()
        self.fetch.assert_not_called()
        self.assertEqual([], self.rows())
        audit = read_jsonl(dated_path(self.root, "market_collection", "2026-10-26"))
        self.assertEqual("missed_before_measurement_start", audit[0]["status"])

    def test_wrong_window_does_not_write_snapshot(self):
        self.fetch.return_value = ({"provider": "test", "target_date_local": "2026-10-27"}, {}, "test")
        self.assertTrue(self.collect())
        self.assertEqual([], self.rows())

    def test_one_provider_failure_preserves_success_and_allows_retry(self):
        failed = Mock(side_effect=RequestError("quota", status_code=429))
        self.factory = lambda now, window: [EnabledProvider("failed", failed), EnabledProvider("test", self.fetch)]
        self.assertTrue(self.collect())
        self.assertEqual(1, len(self.rows()))
        self.assertEqual("test", self.rows()[0]["provider"])

    def test_weatherbit_is_excluded_from_market_window(self):
        with patch.dict("os.environ", {"WEATHERBIT_API_KEY": "fake", "WEATHERBIT_ARCHIVAL_ALLOWED": "true",
                                       "DATA_ENCRYPTION_KEY": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}, clear=True), \
                patch("sys.stdout", new_callable=io.StringIO):
            self.assertNotIn("weatherbit", [p.slug for p in configured_providers(OPEN, self.event.window)])
            self.assertIn("weatherbit", [p.slug for p in configured_providers(OPEN)])


if __name__ == "__main__":
    unittest.main()

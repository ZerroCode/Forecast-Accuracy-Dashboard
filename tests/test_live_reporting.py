from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from collect_market_forecasts import save_contracts
from record_workflow_timing import annotate
from weather_pipeline.config import load_stations
from weather_pipeline.live_report import build_reports, timing_summary
from weather_pipeline.storage import upsert_jsonl, write_json
from weather_pipeline.telemetry import RunLog
from weather_pipeline.verification import Outcomes, inspect_forecast
from weather_pipeline.windows import local_day, standard_day, utc_text

STATION = load_stations(ROOT / "config/stations.csv")[0]
NOW = datetime(2026, 11, 20, 18, tzinfo=timezone.utc)
SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def forecast(day=10, provider="open_meteo", metric="high", kind="market", delay=120):
    target = date(2026, 11, day)
    opening = datetime(2026, 11, day - 1, 15, tzinfo=timezone.utc)
    anchor = opening if kind == "market" else opening.replace(hour=12, minute=17)
    window = (standard_day if kind == "market" else local_day)(target, STATION.timezone)
    return {"provider": provider, "station_id": STATION.station_id, **window.metadata(),
            "snapshot_date_utc": opening.date().isoformat(), "temperature_metric": metric,
            "event_ticker": f"TEST{metric}-{target.isoformat()}", "market_open_time_utc": utc_text(opening),
            "request_started_at_utc": utc_text(anchor), "retrieved_at_utc": utc_text(anchor + timedelta(seconds=delay)),
            "source_resolution": "1h", "sample_count": 24, "expected_sample_count": 24,
            "forecast_high_f": 73, "forecast_low_f": 52, "settlement_source_name": "The Weather Company",
            "market_contracts": [{"market_ticker": f"TEST{metric}-{target.isoformat()}-T70", "rules_version": "v1"}]}


def contract(row, value=70):
    return {**{k: row[k] for k in ("station_id", "target_date_local", "temperature_metric", "event_ticker",
                                  "market_open_time_utc", "window_start_utc", "window_end_utc", "daily_boundary",
                                  "settlement_source_name")}, **row["market_contracts"][0],
            "status": "finalized", "result": "yes", "expiration_value": str(value),
            "validation_errors": [], "retrieved_at_utc": "2026-11-17T18:00:00Z"}


def save_forecasts(root, rows, kind="market", key=None):
    category = "market_forecasts" if kind == "market" else "forecasts"
    suffix = ".jsonl.visual_crossing.enc" if key else ".jsonl"
    path = root / category / ("test" + suffix)
    keys = ("provider", "event_ticker") if kind == "market" else ("provider", "station_id", "snapshot_date_utc")
    upsert_jsonl(path, rows, key_fields=keys, encryption_key=key)
    return path


class LiveReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def report(self, **kwargs):
        return build_reports(self.root, [STATION], NOW, **kwargs)

    def test_comparison_uses_same_cases_with_known_errors_and_recomputes_corrections(self):
        rows = [forecast(day, provider) for day in range(10, 16) for provider in ("open_meteo", "nws")]
        for row in rows:
            if row["provider"] == "nws":
                row["forecast_high_f"] = 69
        save_forecasts(self.root, rows)
        save_contracts(self.root, [contract(r) for r in rows])
        health, accuracy = self.report()
        group = next(g for g in accuracy["groups"] if g["station_id"] == "all")
        self.assertEqual(6, group["common_cases"])
        self.assertEqual(["nws", "open_meteo"], group["providers"])
        self.assertEqual({"provider": "nws", "n": 6, "mae_f": 1, "bias_f": -1,
                          "within_1f": 1, "within_2f": 1}, group["metrics"][0])
        self.assertEqual(3, group["metrics"][1]["mae_f"])
        revised = contract(rows[0], 71)
        revised["retrieved_at_utc"] = "2026-11-18T18:00:00Z"
        save_contracts(self.root, [revised])
        _, updated = self.report()
        self.assertNotEqual(accuracy, updated)

    def test_near_open_milestone_counts_settled_station_days_for_full_roster(self):
        rows = [forecast(day, provider, metric)
                for day in range(10, 16) for provider in ("nws", "open_meteo")
                for metric in ("high", "low")]
        contracts = [contract(row) for row in rows]
        contracts.append(contract(forecast(16)))  # Discovered high, no provider captures.
        save_contracts(self.root, contracts)
        for row in rows:
            if row["provider"] == "nws" and row["temperature_metric"] == "low" and row["target_date_local"].endswith("15"):
                row["retrieved_at_utc"] = "2026-11-14T16:00:00Z"
        save_forecasts(self.root, rows)
        coverage = self.report()[1]["near_open_coverage"]
        self.assertEqual("reached", coverage["status"])
        self.assertEqual(5, coverage["paired_dates"])
        self.assertEqual({"expected_station_days": 7, "qualified_station_days": 6}, coverage["metrics"]["high"])
        self.assertEqual({"expected_station_days": 6, "qualified_station_days": 5}, coverage["metrics"]["low"])

    def test_failures_and_unrun_days_remain_expected(self):
        row = forecast(kind="daily")
        save_forecasts(self.root, [row], kind="daily")
        run = RunLog(self.root, "daily", clock=lambda: NOW)
        run.expect([{**row, "snapshot_date_utc": "2026-11-20", "target_date_local": "2026-11-21", "provider": p}
                    for p in ("nws", "open_meteo")])
        health, accuracy = self.report()
        self.assertEqual(["nws", "open_meteo"], accuracy["comparison_rosters"]["daily"])
        missing = [r for r in health["snapshots"] if r["collection_status"] == "missing"]
        self.assertTrue(any(r["provider"] == "nws" for r in missing))
        self.assertTrue(any(r["snapshot_date_utc"] == "2026-11-12" for r in missing))

    def test_missing_provider_time_mismatch_and_late_cohorts_are_not_ranked_together(self):
        rows = [forecast(day, provider) for day in range(10, 16) for provider in ("open_meteo", "nws")]
        rows = [r for r in rows if not (r["provider"] == "nws" and r["target_date_local"].endswith("10"))]
        for row in rows:
            if row["target_date_local"].endswith("11"):
                # Both late, but an hour apart: not a fair comparison.
                row["retrieved_at_utc"] = row["market_open_time_utc"].replace("15:00", "16:00" if row["provider"] == "nws" else "17:00")
            if row["target_date_local"].endswith("12") and row["provider"] == "nws":
                row["retrieved_at_utc"] = row["market_open_time_utc"].replace("15:00", "16:00")
        save_forecasts(self.root, rows)
        save_contracts(self.root, [contract(r) for r in rows])
        _, accuracy = self.report()
        self.assertEqual("insufficient_common_history", accuracy["ranking_status"])
        groups = [g for g in accuracy["groups"] if g["station_id"] == "all"]
        self.assertEqual(3, sum(g["common_cases"] for g in groups))
        self.assertEqual(1, sum(g["capture_time_mismatch_cases"] for g in groups))
        self.assertTrue(all(m["bias_f"] is None for g in groups for m in g["metrics"]))

    def test_high_low_events_score_once_per_metric_and_duplicate_rows_are_rejected(self):
        rows = [forecast(metric=metric) for metric in ("high", "low")]
        path = save_forecasts(self.root, rows)
        save_contracts(self.root, [contract(r, 70 if r["temperature_metric"] == "high" else 50) for r in rows])
        _, accuracy = self.report()
        groups = [g for g in accuracy["groups"] if g["station_id"] == "all"]
        self.assertEqual([("high", 1), ("low", 1)], [(g["metric"], g["common_cases"]) for g in groups])
        with path.open("a") as handle:
            handle.write(json.dumps(rows[0]) + "\n")
        health, accuracy = self.report()
        self.assertIn("duplicate_snapshot", {r.get("quality") for r in health["snapshots"]})
        self.assertFalse(any(g["metric"] == "high" for g in accuracy["groups"]))

    def test_encrypted_forecasts_stay_in_memory_and_small_scores_are_suppressed(self):
        row = forecast(provider="visual_crossing")
        row["forecast_high_f"] = 71.23456789
        save_forecasts(self.root, [row], key=SECRET)
        save_contracts(self.root, [contract(row)])
        health, accuracy = self.report(key=SECRET)
        public = json.dumps([health, accuracy])
        for private in ("71.23456789", SECRET, "forecast_high_f", "expiration_value", '"error"'):
            self.assertNotIn(private, public)
        self.assertEqual(1, accuracy["groups"][0]["common_cases"])
        self.assertIsNone(accuracy["groups"][0]["metrics"][0]["bias_f"])
        self.assertFalse((self.root / "private").exists())
        with patch.dict(os.environ, {}, clear=True):
            health, accuracy = self.report()
        self.assertEqual("partial", health["status"])
        self.assertEqual(["visual_crossing"], accuracy["excluded_providers"])
        self.assertEqual("unavailable", accuracy["near_open_coverage"]["status"])
        health, accuracy = self.report(key="wrong-key")
        self.assertEqual("archive_unreadable", health["archive_problems"][0]["reason"])

    def test_corrupt_public_archive_blocks_comparison(self):
        path = save_forecasts(self.root, [forecast()])
        path.write_text("{broken")
        health, accuracy = self.report()
        self.assertEqual("partial", health["status"])
        self.assertEqual("blocked_by_unreadable_archive", accuracy["ranking_status"])

    def test_report_does_not_use_outcomes_retrieved_after_its_timestamp(self):
        row = forecast()
        save_forecasts(self.root, [row])
        future = {**contract(row), "retrieved_at_utc": "2026-11-21T18:00:00Z"}
        save_contracts(self.root, [future])
        health, accuracy = self.report()
        saved = next(r for r in health["snapshots"] if r["collection_status"] == "saved")
        self.assertEqual("awaiting_outcome", saved["outcomes"]["high"])
        self.assertEqual([], accuracy["groups"])

    def test_missing_encryption_key_does_not_hide_known_request_failures(self):
        row = forecast(provider="visual_crossing")
        path = save_forecasts(self.root, [row], key=SECRET)
        path.rename(path.with_name("2026-11-10.jsonl.visual_crossing.enc"))
        failure = {**row, "status": "request_failed", "reason": "quota"}
        upsert_jsonl(self.root / "market_collection/test.jsonl", [failure], key_fields=("provider",))
        with patch.dict(os.environ, {}, clear=True):
            health, _ = self.report()
        failed = next(r for r in health["snapshots"] if r["provider"] == "visual_crossing")
        self.assertEqual("request_failed", failed["collection_status"])
        self.assertEqual("quota", failed["failure_reason"])


class MatchingTests(unittest.TestCase):
    def test_complete_window_and_real_capture_required(self):
        row = forecast()
        for changes, expected in (({"sample_count": 23}, "incomplete_window"),
                                  ({"forecast_high_f": float("nan")}, "invalid_temperature"),
                                  ({"retrieved_at_utc": row["window_start_utc"]}, "captured_after_measurement_start"),
                                  ({"aggregation_method": "max_min_of_3_hour_points"}, "legacy_spatial_extrema")):
            with self.subTest(expected=expected):
                self.assertEqual(expected, inspect_forecast("market", {**row, **changes}, STATION, NOW)[0])
        daily = forecast(kind="daily")
        daily.pop("request_started_at_utc")
        self.assertEqual("capture_time_unverified", inspect_forecast("daily", daily, STATION, NOW)[0])

    def test_exact_identity_source_rules_and_settled_value_required(self):
        row = forecast()
        window = standard_day(date(2026, 11, 10), STATION.timezone)
        for changes, expected in (({"station_id": "other_airport"}, "outcome_identity_mismatch"),
                                  ({"settlement_source_name": "National Weather Service"}, "outcome_source_mismatch"),
                                  ({"window_end_utc": "2026-11-11T06:00:00Z"}, "outcome_window_mismatch"),
                                  ({"rules_version": "v2"}, "contract_rules_changed"),
                                  ({"status": "closed"}, "awaiting_outcome"),
                                  ({"expiration_value": None}, "awaiting_outcome"),
                                  ({"validation_errors": ["changed_station"]}, "invalid_contract")):
            with self.subTest(expected=expected):
                outcomes = Outcomes([{**contract(row), **changes}], [])
                self.assertEqual(expected, outcomes.resolve("market", row, "high", window, STATION, NOW)[0])
        outcomes = Outcomes([contract(row)], [])
        self.assertEqual("measurement_pending", outcomes.resolve("market", row, "high", window, STATION, window.start)[0])

    def test_disagreeing_brackets_do_not_define_an_outcome(self):
        row = forecast()
        other = {**contract(row, 71), "market_ticker": "second-bracket"}
        row["market_contracts"].append({"market_ticker": "second-bracket", "rules_version": "v1"})
        outcomes = Outcomes([contract(row), other], [])
        self.assertEqual("conflicting_outcomes", outcomes.resolve(
            "market", row, "high", standard_day(date(2026, 11, 10), STATION.timezone), STATION, NOW)[0])

    def test_noaa_requires_verified_window_and_quality_and_is_not_market_settlement(self):
        row = forecast(kind="daily")
        window = local_day(date(2026, 11, 10), STATION.timezone)
        observation = {"station_id": STATION.station_id, "target_date_local": "2026-11-10",
                       "retrieved_at_utc": "2026-11-11T18:00:00Z",
                       "ncei_station_id": STATION.ncei_station_id, "actual_high_f": 70, "tmax_attributes": ",,W"}
        self.assertEqual("outcome_window_unverified", Outcomes([], [observation]).resolve(
            "daily", row, "high", window, STATION, NOW)[0])
        observation.update(window.metadata())
        self.assertEqual("ready", Outcomes([], [observation]).resolve("daily", row, "high", window, STATION, NOW)[0])
        observation["tmax_attributes"] = ",X,W"
        self.assertEqual("outcome_quality_unverified", Outcomes([], [observation]).resolve(
            "daily", row, "high", window, STATION, NOW)[0])
        self.assertEqual("awaiting_outcome", Outcomes([], [observation]).resolve(
            "market", forecast(), "high", window, STATION, NOW)[0])

    def test_dst_local_day_cannot_use_standard_day_settlement(self):
        row = forecast(kind="daily")
        target = date(2026, 11, 1)
        row.update(local_day(target, STATION.timezone).metadata())
        settled = contract(row)
        settled.update(standard_day(target, STATION.timezone).metadata())
        self.assertEqual("outcome_window_mismatch", Outcomes([settled], []).resolve(
            "daily", row, "high", local_day(target, STATION.timezone), STATION, NOW)[0])


class TimingTests(unittest.TestCase):
    def test_timing_separates_precreation_delay_setup_and_requests_and_redacts_failures(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_JOB": "collect"}, clear=True):
            root = Path(directory)
            run = RunLog(root, "market", clock=lambda: NOW)
            run.request({"market_open_time_utc": utc_text(NOW - timedelta(hours=3))},
                        NOW, NOW + timedelta(seconds=1), ValueError(SECRET))
            run.finish(1)
            fetch = Mock(side_effect=[{"created_at": utc_text(NOW - timedelta(minutes=2)),
                                      "run_started_at": utc_text(NOW - timedelta(minutes=2))},
                                     {"jobs": [{"name": "collect", "started_at": utc_text(NOW - timedelta(minutes=1))}]}])
            env = {**os.environ, "GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": SECRET}
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(0, annotate(root, environ=env, fetch=fetch))
            saved = json.loads(run.path.read_text())
            result = timing_summary(saved)
            self.assertEqual(60, result["creation_to_job_seconds"])
            self.assertEqual(60, result["job_to_collector_seconds"])
            self.assertEqual(10680, result["requests"][0]["opening_to_workflow_creation_seconds"])
            self.assertNotIn(SECRET, run.path.read_text())
            self.assertIn("/attempts/2/jobs", fetch.call_args_list[1].args[0])
            with patch("sys.stdout", new_callable=io.StringIO):
                annotate(root, environ=env, fetch=Mock(side_effect=ValueError(SECRET)))
            self.assertEqual("unavailable", json.loads(run.path.read_text())["timing_status"])


if __name__ == "__main__":
    unittest.main()

"""Capture the first available forecast after each verified Kalshi event opens.

Read-only market API access. This collector never places orders or backdates data.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Callable

from collect_forecasts import configured_providers
from weather_pipeline.config import load_stations
from weather_pipeline.http import RequestError
from weather_pipeline.kalshi import KalshiClient, MarketEvent, discover, load_mappings
from weather_pipeline.storage import read_jsonl, upsert_jsonl
from weather_pipeline.telemetry import RunLog, failure_reason
from weather_pipeline.windows import utc_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORECAST_KEYS = ("provider", "event_ticker", "market_open_time_utc")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dated_path(root: Path, category: str, target: str) -> Path:
    year, month, _ = target.split("-")
    return root / category / year / month / f"{target}.jsonl"


def save_contracts(root: Path, records: list[dict]) -> None:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["target_date_local"], []).append(record)
    for target, rows in grouped.items():
        upsert_jsonl(dated_path(root, "markets", target), rows,
                     key_fields=("market_ticker", "rules_version"), replace=True,
                     ignore_compare_fields=frozenset({"retrieved_at_utc"}))


def collect_events(
    events: list[MarketEvent], root: Path, *, clock: Callable = now_utc,
    provider_factory: Callable = partial(configured_providers, quiet=True), near_open_seconds: int = 600,
    run_log: RunLog | None = None,
) -> list[str]:
    failures = []
    # Per-run cache: matching high/low events reuse one weather request, but different
    # openings never share a response. Failed requests are also not multiplied by brackets.
    cache: dict[tuple, tuple[dict | None, str | None]] = {}
    stopped_providers = set()
    known: dict[Path, set[tuple]] = {}
    for event in sorted(events, key=lambda item: (item.opens, item.mapping.station.station_id, item.ticker)):
        now = clock()
        if now < event.opens:
            continue
        station = event.mapping.station
        target = event.window.target_date.isoformat()
        providers = provider_factory(now, event.window)
        if run_log:
            run_log.expect([{"provider": p.slug, "station_id": station.station_id,
                             "event_ticker": event.ticker, "target_date_local": target,
                             "market_open_time_utc": utc_text(event.opens)} for p in providers])
        for provider in providers:
            output = provider.output_path(dated_path(root, "market_forecasts", target))
            if output not in known:
                try:
                    known[output] = {
                        tuple(row[k] for k in FORECAST_KEYS)
                        for row in provider.existing_rows(dated_path(root, "market_forecasts", target))
                    }
                except Exception as exc:
                    failures.append(f"{event.ticker}/{provider.slug}/archive: {failure_reason(exc)}")
                    continue
            key = (provider.slug, event.ticker, utc_text(event.opens))
            if key in known[output]:
                continue
            now = clock()
            audit = {
                "provider": provider.slug, "event_ticker": event.ticker,
                "market_open_time_utc": utc_text(event.opens), "station_id": station.station_id,
                "target_date_local": target, "checked_at_utc": utc_text(now),
            }
            if now >= event.window.start:
                audit["status"] = "missed_before_measurement_start"
            elif any(row["status"] not in {"active", "open"} for row in event.contracts):
                audit["status"] = "market_not_active"
            elif provider.slug in stopped_providers:
                audit["status"] = "provider_unavailable"
            else:
                cache_key = (provider.slug, station.station_id, target, utc_text(event.opens))
                if cache_key not in cache:
                    started = clock()
                    try:
                        # Build closures with this actual request's time, not workflow start.
                        fresh = next(p for p in provider_factory(started, event.window)
                                     if p.slug == provider.slug)
                        record, _, _ = fresh.fetch(station)
                        finished = clock()
                        if run_log:
                            record["collection_run"] = run_log.path.name
                        if finished >= event.window.start:
                            raise ValueError("Forecast response arrived after the measurement day began")
                        for field, expected in event.window.metadata().items():
                            if record.get(field) != expected:
                                raise ValueError(f"Provider returned the wrong {field}")
                        delay = (finished - event.opens).total_seconds()
                        record.update({
                            "schema_version": 2, "snapshot_kind": "market_open",
                            "snapshot_date_utc": finished.date().isoformat(),
                            "request_started_at_utc": utc_text(started),
                            "retrieved_at_utc": utc_text(finished),
                            "seconds_after_market_open": round(delay, 3),
                            "capture_status": "near_open" if delay <= near_open_seconds else "late",
                            "near_open_tolerance_seconds": near_open_seconds,
                            "eligible_for_opening_comparison": 0 <= delay <= near_open_seconds,
                        })
                        cache[cache_key] = (record, None)
                        if run_log:
                            run_log.request({"provider": provider.slug, "station_id": station.station_id,
                                             "event_ticker": event.ticker, "target_date_local": target,
                                             "market_open_time_utc": utc_text(event.opens)}, started, finished)
                    except Exception as exc:
                        if run_log:
                            run_log.request({"provider": provider.slug, "station_id": station.station_id,
                                             "event_ticker": event.ticker, "target_date_local": target,
                                             "market_open_time_utc": utc_text(event.opens)}, started, clock(), exc)
                        cache[cache_key] = (None, failure_reason(exc))
                        failures.append(f"{event.ticker}/{provider.slug}: {failure_reason(exc)}")
                        if isinstance(exc, RequestError) and exc.status_code in {401, 402, 403, 429}:
                            stopped_providers.add(provider.slug)
                record, error = cache[cache_key]
                if error:
                    audit.update(status="request_failed", reason=error)
                else:
                    saved = {
                        **record, "event_ticker": event.ticker,
                        "series_ticker": event.mapping.series,
                        "temperature_metric": event.mapping.metric,
                        "market_open_time_utc": utc_text(event.opens),
                        "settlement_source_name": event.contracts[0]["settlement_source_name"],
                        "window_basis": event.contracts[0]["window_basis"],
                        "market_contracts": [{"market_ticker": row["market_ticker"],
                                              "rules_version": row["rules_version"]}
                                             for row in sorted(event.contracts, key=lambda r: r["market_ticker"])],
                        "observation_role": "forecast_only_not_official_settlement",
                    }
                    try:
                        upsert_jsonl(output, [saved], key_fields=FORECAST_KEYS,
                                     encryption_key=provider.archive_key,
                                     legacy_encryption_key=provider.legacy_archive_key)
                        known[output].add(key)
                        audit["status"] = saved["capture_status"]
                        print(f"Saved {event.ticker}/{provider.slug}: {saved['capture_status']} "
                              f"({saved['seconds_after_market_open']}s after open)")
                    except Exception as exc:
                        failures.append(f"{event.ticker}/{provider.slug}/archive: {failure_reason(exc)}")
                        audit.update(status="archive_failed", reason=failure_reason(exc))
            upsert_jsonl(dated_path(root, "market_collection", target), [audit],
                         key_fields=FORECAST_KEYS, replace=True,
                         ignore_compare_fields=frozenset({"checked_at_utc"}))
    return failures


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=PROJECT_ROOT / "config/stations.csv")
    parser.add_argument("--mappings", type=Path, default=PROJECT_ROOT / "config/kalshi_markets.json")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--discover-only", action="store_true", help="Save contracts without requesting forecasts")
    parser.add_argument("--wait-seconds", type=int, default=0,
                        help="Recheck for new openings for up to this many seconds (maximum 300)")
    parser.add_argument("--near-open-seconds", type=int, default=600,
                        help="Mark responses later than this opening-time tolerance as late")
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 300 or args.near_open_seconds < 0:
        parser.error("wait-seconds must be 0..300 and near-open-seconds must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    mappings = load_mappings(args.mappings, load_stations(args.stations))
    client = KalshiClient()
    deadline = time.monotonic() + args.wait_seconds
    failures = []
    run = RunLog(args.data_dir, "market")
    while True:
        discovery_started = now_utc()
        events, contracts, discovery_failures = discover(client, mappings, now_utc())
        run.data["discovery"].append({"started_at_utc": utc_text(discovery_started),
                                      "finished_at_utc": utc_text(now_utc()),
                                      "events": len(events), "failure_count": len(discovery_failures)})
        run.save()
        save_contracts(args.data_dir, contracts)
        failures.extend(discovery_failures)
        if not args.discover_only:
            failures.extend(collect_events(events, args.data_dir, near_open_seconds=args.near_open_seconds,
                                           run_log=run))
        print(f"Discovered {len(events)} validated events / {len(contracts)} contracts")
        remaining = deadline - time.monotonic()
        if args.discover_only or remaining <= 0:
            break
        # Keep the runner warm around typical openings; timestamps still come from
        # the API. Hourly recovery runs also discover markets opening at other times.
        future = [(event.opens - now_utc()).total_seconds() for event in events]
        positive = [delay for delay in future if delay > 0]
        time.sleep(min(remaining, 30, min(positive) if positive else 30))
    run.finish(len(failures))
    if failures:
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

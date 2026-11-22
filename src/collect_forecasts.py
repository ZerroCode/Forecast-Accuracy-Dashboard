from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from weather_pipeline.config import Station, load_stations
from weather_pipeline.encryption import configured_key
from weather_pipeline.http import RequestError
from weather_pipeline.providers.meteosource import fetch_forecast as fetch_meteosource
from weather_pipeline.providers.nws import fetch_forecast as fetch_nws
from weather_pipeline.providers.open_meteo import fetch_forecast as fetch_open_meteo
from weather_pipeline.providers.openweathermap import fetch_forecast as fetch_openweathermap
from weather_pipeline.providers.pirate_weather import fetch_forecast as fetch_pirate_weather
from weather_pipeline.providers.tomorrow_io import fetch_forecast as fetch_tomorrow_io
from weather_pipeline.providers.visual_crossing import fetch_forecast as fetch_visual_crossing
from weather_pipeline.providers.weatherbit import fetch_forecast as fetch_weatherbit
from weather_pipeline.storage import read_jsonl, upsert_jsonl, write_json
from weather_pipeline.telemetry import RunLog, failure_reason, now_utc
from weather_pipeline.windows import ForecastWindow, local_day, utc_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEY_FIELDS = ("provider", "station_id", "target_date_local", "snapshot_date_utc")


@dataclass(frozen=True)
class EnabledProvider:
    slug: str
    fetch: Callable[[Station], tuple[dict[str, Any], dict[str, Any], str]]
    archive_key: str | None = field(default=None, repr=False)
    legacy_archive_key: str | None = field(default=None, repr=False)

    def output_path(self, path: Path) -> Path:
        if self.archive_key is not None:
            return path.with_name(f"{path.name}.{self.slug}.enc")
        return path

    def existing_rows(self, path: Path) -> list[dict]:
        rows = read_jsonl(self.output_path(path), encryption_key=self.archive_key,
                          legacy_encryption_key=self.legacy_archive_key)
        if self.archive_key is not None:
            # Until migration, successful plaintext captures must still suppress a
            # replacement request. Never rewrite their original issue/arrival times.
            rows += [r for r in read_jsonl(path) if r.get("provider") == self.slug]
        return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect next-day temperature forecasts")
    parser.add_argument("--stations", type=Path, default=PROJECT_ROOT / "config/stations.csv")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument(
        "--save-raw", action="store_true", help="Also archive full API responses for debugging"
    )
    parser.add_argument(
        "--as-of",
        help="UTC collection timestamp for reproducible runs (ISO 8601)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Replace today's existing station snapshots",
    )
    return parser.parse_args()


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a UTC offset")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def configured_providers(
    retrieved_at: datetime, window: ForecastWindow | None = None, *, quiet: bool = False,
) -> list[EnabledProvider]:
    def announce(message: str) -> None:
        if not quiet:
            print(message)

    providers = [
        EnabledProvider(
            slug="open_meteo",
            fetch=lambda station: fetch_open_meteo(station, retrieved_at=retrieved_at, window=window),
        ),
        EnabledProvider(
            slug="nws",
            fetch=lambda station: fetch_nws(station, retrieved_at=retrieved_at, window=window),
        ),
    ]

    openweather_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if openweather_key:
        providers.append(
            EnabledProvider(
                slug="openweathermap",
                fetch=lambda station: fetch_openweathermap(
                    station,
                    retrieved_at=retrieved_at,
                    api_key=openweather_key,
                    window=window,
                ),
                archive_key=configured_key(),
            )
        )
    else:
        announce("OPENWEATHERMAP_API_KEY is not set; skipping OpenWeather")

    meteosource_key = os.getenv("METEOSOURCE_API_KEY")
    if meteosource_key:
        tier = (os.getenv("METEOSOURCE_TIER") or "free").strip().lower()
        if not _enabled(os.getenv("METEOSOURCE_ARCHIVAL_ALLOWED")):
            announce("Meteosource archive disabled; confirm retention and scoring rights before enabling it.")
        elif window is None or tier != "free":
            providers.append(EnabledProvider(
                slug="meteosource",
                fetch=lambda station: fetch_meteosource(
                    station, retrieved_at=retrieved_at, api_key=meteosource_key, tier=tier, window=window,
                ),
                archive_key=configured_key(),
            ))

    pirate_key = os.getenv("PIRATE_WEATHER_API_KEY")
    if pirate_key:
        providers.append(EnabledProvider(
            slug="pirate_weather",
            fetch=lambda station: fetch_pirate_weather(
                station, retrieved_at=retrieved_at, api_key=pirate_key, window=window,
            ),
            archive_key=configured_key(),
        ))
    else:
        announce("PIRATE_WEATHER_API_KEY is not set; skipping Pirate Weather")

    visual_crossing_key = os.getenv("VISUALCROSSING_API_KEY")
    if visual_crossing_key:
        providers.append(EnabledProvider(
            slug="visual_crossing",
            fetch=lambda station: fetch_visual_crossing(
                station, retrieved_at=retrieved_at, api_key=visual_crossing_key, window=window,
            ),
            archive_key=configured_key(), legacy_archive_key=visual_crossing_key,
        ))
    else:
        announce("VISUALCROSSING_API_KEY is not set; skipping Visual Crossing")

    weatherbit_key = os.getenv("WEATHERBIT_API_KEY")
    if window is not None and weatherbit_key:
        announce("Weatherbit daily aggregates cannot reproduce a standard-time window; market snapshots skip it.")
    elif weatherbit_key and _enabled(os.getenv("WEATHERBIT_ARCHIVAL_ALLOWED")):
        providers.append(
            EnabledProvider(
                slug="weatherbit",
                fetch=lambda station: fetch_weatherbit(
                    station,
                    retrieved_at=retrieved_at,
                    api_key=weatherbit_key,
                ),
                archive_key=configured_key(),
            )
        )
    elif weatherbit_key:
        announce(
            "WEATHERBIT_API_KEY is set, but archival collection is disabled. "
            "Set WEATHERBIT_ARCHIVAL_ALLOWED=true only for an active plan that permits storage."
        )

    tomorrow_key = os.getenv("TOMORROW_API_KEYS")
    if tomorrow_key and _enabled(os.getenv("TOMORROW_ARCHIVAL_ALLOWED")):
        providers.append(
            EnabledProvider(
                slug="tomorrow_io",
                fetch=lambda station: fetch_tomorrow_io(
                    station,
                    retrieved_at=retrieved_at,
                    api_key=tomorrow_key,
                    window=window,
                ),
                archive_key=configured_key(),
            )
        )
    elif tomorrow_key:
        announce(
            "TOMORROW_API_KEYS is set, but archival collection is disabled. "
            "Set TOMORROW_ARCHIVAL_ALLOWED=true after confirming retention rights."
        )

    if os.getenv("GOOGLE_MAPS_DEMO_API_KEY"):
        announce("Google Weather is not archived because daily forecast retention is limited to 24 hours.")
    if os.getenv("WEATHERAPI_API_KEY"):
        announce("WeatherAPI is not archived because forecast retention is limited to 24 hours.")

    return providers


def main() -> int:
    args = parse_args()
    retrieved_at = parse_as_of(args.as_of)
    stations = [station for station in load_stations(args.stations) if station.active]
    if not stations:
        print("No active stations; no requests made.")
        return 0
    try:
        providers = configured_providers(retrieved_at)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    clock = (lambda: retrieved_at) if args.as_of else now_utc
    run = RunLog(args.data_dir, "daily", clock=clock)
    snapshot_date = retrieved_at.date().isoformat()
    year, month, _ = snapshot_date.split("-")
    output_path = args.data_dir / "forecasts" / year / month / f"{snapshot_date}.jsonl"
    changes = 0
    failures: list[str] = []
    targets = {
        station.station_id: (
            retrieved_at.astimezone(ZoneInfo(station.timezone)).date() + timedelta(days=1)
        ).isoformat()
        for station in stations
    }
    run.expect([{"provider": p.slug, "station_id": s.station_id,
                 "target_date_local": targets[s.station_id], "snapshot_date_utc": snapshot_date}
                for p in providers for s in stations])
    audit_path = args.data_dir / "daily_collection" / year / month / f"{snapshot_date}.jsonl"

    def audit(provider, station, status, **metadata):
        upsert_jsonl(audit_path, [{"provider": provider.slug, "station_id": station.station_id,
                     "target_date_local": targets[station.station_id], "snapshot_date_utc": snapshot_date,
                     "checked_at_utc": utc_text(clock()), "status": status, **metadata}],
                     key_fields=KEY_FIELDS, replace=True,
                     ignore_compare_fields=frozenset({"checked_at_utc"}))

    for provider in providers:
        provider_path = provider.output_path(output_path)
        try:
            existing_keys = {
                tuple(row[field] for field in KEY_FIELDS)
                for row in provider.existing_rows(output_path)
            }
        except Exception as exc:
            failures.append(f"{provider.slug}/archive: {failure_reason(exc)}")
            for station in stations:
                audit(provider, station, "archive_unreadable")
            continue
        records = []
        stopped = False
        for station in stations:
            local_target = targets[station.station_id]
            expected_key = (provider.slug, station.station_id, local_target, snapshot_date)
            if expected_key in existing_keys and not args.refresh:
                print(
                    f"Skipping existing {provider.slug} snapshot for "
                    f"{station.station_id} ({local_target})"
                )
                audit(provider, station, "existing")
                continue
            if stopped:
                audit(provider, station, "provider_unavailable")
                continue
            started = clock()
            try:
                # Build the adapter with this request's time, not the job's start.
                fresh = next(p for p in configured_providers(started, quiet=True) if p.slug == provider.slug)
                record, payload, _ = fresh.fetch(station)
                finished = clock()
                if record["target_date_local"] != local_target:
                    raise ValueError("Local target date changed during collection")
                window = local_day(date.fromisoformat(local_target), station.timezone)
                if finished >= window.start:
                    raise ValueError("Forecast response arrived after the measurement day began")
                record.update(snapshot_date_utc=snapshot_date,
                              request_started_at_utc=utc_text(started), retrieved_at_utc=utc_text(finished),
                              collection_run=run.path.name, **window.metadata())
                if args.save_raw:
                    raw_path = (
                        args.data_dir
                        / "raw"
                        / provider.slug
                        / year
                        / month
                        / snapshot_date
                        / f"{station.station_id}.json"
                    )
                    write_json(provider.output_path(raw_path), payload,
                               encryption_key=provider.archive_key)
                records.append(record)
                run.request({"provider": provider.slug, "station_id": station.station_id,
                             "target_date_local": local_target}, started, finished)
                print(
                    f"Collected {provider.slug} {station.station_id} forecast "
                    f"for {record['target_date_local']}"
                )
            except Exception as exc:  # continue so one location cannot hide other successes
                run.request({"provider": provider.slug, "station_id": station.station_id,
                             "target_date_local": local_target}, started, clock(), exc)
                audit(provider, station, "request_failed", reason=failure_reason(exc))
                failures.append(f"{provider.slug}/{station.station_id}: {failure_reason(exc)}")
                if isinstance(exc, RequestError) and exc.status_code in {401, 402, 403, 429}:
                    print(f"Stopping {provider.slug}: authentication/access/quota error; see failure report.")
                    stopped = True

        try:
            changes += upsert_jsonl(
                provider_path,
                records,
                key_fields=KEY_FIELDS,
                replace=args.refresh,
                ignore_compare_fields=frozenset({"retrieved_at_utc"}),
                encryption_key=provider.archive_key,
                legacy_encryption_key=provider.legacy_archive_key,
            )
            saved = {r["station_id"] for r in records}
            for station in stations:
                if station.station_id in saved:
                    audit(provider, station, "saved")
        except Exception as exc:
            failures.append(f"{provider.slug}/archive: {failure_reason(exc)}")
            for station in stations:
                if any(r["station_id"] == station.station_id for r in records):
                    audit(provider, station, "archive_failed")
    run.finish(len(failures))
    print(f"Forecast rows changed: {changes}")
    if failures:
        print("Forecast collection failures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Download multi-year history for model training and evaluation.

Sources (all free, no keys):
  open_meteo  day-ahead model forecasts (Previous Runs API), hourly -> daily extrema
  mos         NWS GFS MOS guidance from the Iowa Environmental Mesonet archive
  ncei        NOAA/NCEI observed daily highs/lows
  kalshi      settled daily temperature markets: brackets, results, settled value

Each station/year (or Kalshi series) is cached as its own CSV under
data/history/<source>/ so interrupted runs resume. Completed past years are
skipped unless --refresh is given; the final year is always re-downloaded.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from weather_pipeline.config import Station, load_stations
from weather_pipeline.http import get_json, get_text
from weather_pipeline.kalshi import MONTHS, KalshiClient, load_mappings
from weather_pipeline.windows import standard_day


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("open_meteo", "mos", "ncei", "kalshi")
OPEN_METEO_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
OPEN_METEO_MODELS = ("gfs_seamless", "icon_seamless", "gem_seamless", "ecmwf_ifs025")
# previous_day1: each hour forecast ~24h ahead; previous_day2: ~48h ahead.
OPEN_METEO_LEADS = ("previous_day1", "previous_day2")
MOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py"
NCEI_URL = "https://www.ncei.noaa.gov/access/services/data/v1"


def parse_args() -> argparse.Namespace:
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=list(SOURCES))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2023, 1, 1),
                        help="First target date for weather sources (Kalshi always fetches all history)")
    parser.add_argument("--end", type=date.fromisoformat, default=yesterday)
    parser.add_argument("--stations", type=Path, default=PROJECT_ROOT / "config/stations.csv")
    parser.add_argument("--mappings", type=Path, default=PROJECT_ROOT / "config/kalshi_markets.json")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "data/history")
    parser.add_argument("--refresh", action="store_true", help="Re-download cached past years")
    return parser.parse_args()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def year_chunks(start: date, end: date):
    for year in range(start.year, end.year + 1):
        yield year, max(start, date(year, 1, 1)), min(end, date(year, 12, 31))


def days(start: date, end: date):
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def extrema(values: list) -> tuple:
    # Reject partial days rather than report a misleading max/min.
    if len(values) != 24 or any(value is None for value in values):
        return "", ""
    return max(values), min(values)


def open_meteo_rows(station: Station, start: date, end: date) -> list[dict]:
    variables = [f"temperature_2m_{lead}" for lead in OPEN_METEO_LEADS]
    query = urlencode({
        "latitude": station.latitude, "longitude": station.longitude,
        "start_date": (start - timedelta(days=1)).isoformat(),
        "end_date": (end + timedelta(days=1)).isoformat(),
        "hourly": ",".join(variables), "models": ",".join(OPEN_METEO_MODELS),
        "temperature_unit": "fahrenheit", "timezone": "GMT",
    })
    hourly = get_json(f"{OPEN_METEO_URL}?{query}", timeout_seconds=120)["hourly"]
    index = {text: position for position, text in enumerate(hourly["time"])}
    rows = []
    for target in days(start, end):
        window = standard_day(target, station.timezone)
        hours = [(window.start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(24)]
        row = {"station_id": station.station_id, "date": target.isoformat()}
        for model in OPEN_METEO_MODELS:
            for lead in OPEN_METEO_LEADS:
                series = hourly.get(f"temperature_2m_{lead}_{model}", [])
                values = [series[index[h]] if h in index else None for h in hours]
                name = f"{model.split('_')[0]}_{lead.replace('previous_', '')}"
                row[f"{name}_high_f"], row[f"{name}_low_f"] = extrema(values)
        rows.append(row)
    return rows


def mos_rows(station: Station, start: date, end: date) -> list[dict]:
    # 12Z run on D-1: n_x at D 12Z is the overnight low, at D+1 00Z the daytime high.
    query = urlencode({
        "station": station.nws_station_id, "model": "GFS",
        "sts": f"{start - timedelta(days=1)}T12:00Z", "ets": f"{end}T00:00Z", "format": "csv",
    })
    by_key = {}
    for record in csv.DictReader(io.StringIO(get_text(f"{MOS_URL}?{query}", timeout_seconds=180))):
        if record["runtime"].endswith("12:00:00") and record["n_x"]:
            by_key[(record["runtime"][:10], record["ftime"])] = float(record["n_x"])
    rows = []
    for target in days(start, end):
        run = (target - timedelta(days=1)).isoformat()
        rows.append({
            "station_id": station.station_id, "date": target.isoformat(),
            "mos_high_f": by_key.get((run, f"{target + timedelta(days=1)} 00:00:00"), ""),
            "mos_low_f": by_key.get((run, f"{target} 12:00:00"), ""),
        })
    return rows


def ncei_rows(station: Station, start: date, end: date) -> list[dict]:
    query = urlencode({
        "dataset": "daily-summaries", "dataTypes": "TMAX,TMIN",
        "stations": station.ncei_station_id, "startDate": start.isoformat(),
        "endDate": end.isoformat(), "format": "json", "units": "standard",
    })
    payload = get_json(f"{NCEI_URL}?{query}", timeout_seconds=120)
    return [{"station_id": station.station_id, "date": record["DATE"],
             "obs_high_f": record.get("TMAX", "").strip(), "obs_low_f": record.get("TMIN", "").strip()}
            for record in payload]


SOURCE_FIELDS = {
    "open_meteo": ["station_id", "date"] + [
        f"{model.split('_')[0]}_{lead.replace('previous_', '')}_{metric}_f"
        for model in OPEN_METEO_MODELS for lead in OPEN_METEO_LEADS for metric in ("high", "low")],
    "mos": ["station_id", "date", "mos_high_f", "mos_low_f"],
    "ncei": ["station_id", "date", "obs_high_f", "obs_low_f"],
}
SOURCE_FETCH = {"open_meteo": open_meteo_rows, "mos": mos_rows, "ncei": ncei_rows}
KALSHI_FIELDS = ["station_id", "metric", "series", "event_ticker", "date", "market_ticker",
                 "strike_type", "floor_strike", "cap_strike", "result", "settled_value_f"]


def ticker_date(event_ticker: str) -> str:
    # Covers current (KXHIGHNY-26OCT20) and legacy (HIGHNY-21AUG06) tickers.
    match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})$", event_ticker)
    if not match or match[2] not in MONTHS:
        return ""
    return date(2000 + int(match[1]), MONTHS[match[2]], int(match[3])).isoformat()


def settled_value(text) -> str:
    # Usually "67.00"; occasionally empty or a bracket label like "70° to 71°".
    try:
        return str(float(text))
    except (TypeError, ValueError):
        return ""


def kalshi_rows(client: KalshiClient, station_id: str, metric: str, series: str) -> list[dict]:
    # Kalshi serves markets settled before its historical cutoff only from
    # /historical/markets; newer ones come from the live events endpoint.
    markets = {}
    cursor = ""
    while True:
        page = client.get("historical/markets", series_ticker=series, limit=1000, cursor=cursor)
        markets.update((market["ticker"], market) for market in page.get("markets", []))
        cursor = page.get("cursor")
        if not cursor or not page.get("markets"):
            break
    cursor = ""
    while True:
        page = client.get("events", series_ticker=series, status="settled", limit=200,
                          with_nested_markets="true", cursor=cursor)
        for event in page.get("events", []):
            markets.update((market["ticker"], market) for market in event.get("markets", []))
        cursor = page.get("cursor")
        if not cursor or not page.get("events"):
            break
    return [{
        "station_id": station_id, "metric": metric, "series": series,
        "event_ticker": market["event_ticker"], "date": ticker_date(market["event_ticker"]),
        "market_ticker": ticker, "strike_type": market.get("strike_type", ""),
        "floor_strike": market.get("floor_strike", ""), "cap_strike": market.get("cap_strike", ""),
        "result": market.get("result", ""), "settled_value_f": settled_value(market.get("expiration_value")),
    } for ticker, market in sorted(markets.items())]


def main() -> int:
    args = parse_args()
    if args.start > args.end:
        print("--start must not be after --end", file=sys.stderr)
        return 2
    stations = [station for station in load_stations(args.stations) if station.active]
    failures = []

    for source in [s for s in args.sources if s != "kalshi"]:
        # NOAA is one small request per station; keep it whole for simplicity.
        chunks = ([(None, args.start, args.end)] if source == "ncei"
                  else list(year_chunks(args.start, args.end)))
        for station in stations:
            for year, start, end in chunks:
                name = f"{station.station_id}.csv" if year is None else f"{station.station_id}/{year}.csv"
                path = args.out_dir / source / name
                if path.exists() and not args.refresh and year is not None and year < args.end.year:
                    continue
                try:
                    rows = SOURCE_FETCH[source](station, start, end)
                except Exception as exc:
                    failures.append(f"{source} {station.station_id} {year or ''}: {exc}")
                    continue
                write_csv(path, SOURCE_FIELDS[source], rows)
                print(f"{source}: {station.station_id} {year or ''} -> {len(rows)} rows")
                time.sleep(1)  # be polite to free services

    if "kalshi" in args.sources:
        client = KalshiClient()
        for mapping in load_mappings(args.mappings, stations):
            try:
                rows = kalshi_rows(client, mapping.station.station_id, mapping.metric, mapping.series)
            except Exception as exc:
                failures.append(f"kalshi {mapping.series}: {exc}")
                continue
            write_csv(args.out_dir / "kalshi" / f"{mapping.series}.csv", KALSHI_FIELDS, rows)
            print(f"kalshi: {mapping.series} -> {len(rows)} markets")

    if failures:
        print("Failures (re-run to retry; finished files are kept):", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Live Meteosource Point forecasts for a station's requested reporting window."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from weather_pipeline.config import Station
from weather_pipeline.http import get_json
from weather_pipeline.temperatures import sampled_extrema
from weather_pipeline.windows import ForecastWindow, local_day, utc_text


def temperature(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Meteosource returned an invalid temperature")
    return float(value)


def daily_extrema(days, target):
    matches = [day for day in days if isinstance(day, dict) and day.get("day") == target.isoformat()]
    if len(matches) != 1 or not isinstance(matches[0].get("all_day"), dict):
        raise ValueError("Meteosource returned no unique full-day forecast for the target date")
    full_day = matches[0]["all_day"]
    high = temperature(full_day.get("temperature_max"))
    low = temperature(full_day.get("temperature_min"))
    if high < low:
        raise ValueError("Meteosource daily maximum is below its minimum")
    return {"forecast_high_f": high, "forecast_low_f": low}


def hourly_extrema(station, hours, retrieved_at, window):
    samples = []
    for point in hours:
        try:
            instant = datetime.fromisoformat(point["date"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Meteosource returned an invalid hourly timestamp") from None
        # Point returns timestamps in the requested zone, UTC for this section.
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        if window.start <= instant < window.end:
            samples.append((instant, temperature(point.get("temperature"))))
    return sampled_extrema(station, samples, retrieved_at=retrieved_at, step_hours=1, window=window)


def fetch_forecast(station: Station, *, retrieved_at: datetime, api_key: str, tier: str = "free",
                   window: ForecastWindow | None = None, fetch_json=get_json):
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", tier):
        raise ValueError("METEOSOURCE_TIER must be the endpoint tier from your account")
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")
    market = window is not None
    if market and tier == "free":
        raise ValueError("Meteosource Free has insufficient hourly coverage for opening forecasts")
    target = retrieved_at.astimezone(ZoneInfo(station.timezone)).date() + timedelta(days=1)
    window = window or local_day(target, station.timezone)
    if window.start <= retrieved_at:
        raise ValueError("Meteosource requires a reporting window that has not started")
    section = "hourly" if market else "daily"
    zone = "UTC" if market else station.timezone
    query = urlencode({"lat": station.latitude, "lon": station.longitude, "sections": section,
                       "timezone": zone, "units": "us"})
    url = f"https://www.meteosource.com/api/v1/{tier}/point?{query}"
    payload = fetch_json(url, headers={"X-API-Key": api_key})
    if not isinstance(payload, dict) or payload.get("units") != "us" or payload.get("timezone") != zone:
        raise ValueError("Meteosource returned an unexpected timezone or units")
    block = payload.get(section)
    if not isinstance(block, dict) or not isinstance(block.get("data"), list):
        raise ValueError(f"Meteosource returned no {section} forecast")
    if market:
        extrema = hourly_extrema(station, block["data"], retrieved_at, window)
    else:
        extrema = daily_extrema(block["data"], window.target_date)
    record = {
        "schema_version": 1, "provider": "meteosource",
        "station_id": station.station_id, "station_name": station.station_name,
        "latitude": station.latitude, "longitude": station.longitude, "timezone": station.timezone,
        "snapshot_date_utc": retrieved_at.astimezone(timezone.utc).date().isoformat(),
        "retrieved_at_utc": utc_text(retrieved_at), **window.metadata(), **extrema,
        "source_resolution": "1h" if market else "daily",
        "aggregation_method": "max_min_of_hourly_points" if market else "provider_daily_max_min",
        "source_url": url, "attribution": "Weather data by Meteosource (https://www.meteosource.com/)",
    }
    return record, payload, url

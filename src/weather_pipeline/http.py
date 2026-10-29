from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = (
    "ForecastAccuracyDashboard/0.1 "
    "(https://github.com/ZerroCode/Forecast-Accuracy-Dashboard)"
)


class RequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _retry_delay(value: str | None, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        seconds = int(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return fallback
    return max(fallback, seconds)


def get_json(
    url: str,
    *,
    attempts: int = 3,
    timeout_seconds: int = 30,
    headers: dict[str, str] | None = None,
    redacted_url: str | None = None,
) -> Any:
    return _fetch(url, json.load, "application/json", attempts=attempts,
                  timeout_seconds=timeout_seconds, headers=headers, redacted_url=redacted_url)


def get_text(url: str, *, attempts: int = 3, timeout_seconds: int = 60) -> str:
    return _fetch(url, lambda response: response.read().decode("utf-8"), "text/csv, */*",
                  attempts=attempts, timeout_seconds=timeout_seconds)


def _fetch(
    url: str,
    parse,
    accept: str,
    *,
    attempts: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    redacted_url: str | None = None,
) -> Any:
    if attempts < 1 or timeout_seconds <= 0:
        raise ValueError("attempts and timeout_seconds must be positive")
    request_headers = {
        "Accept": accept,
        "User-Agent": os.getenv("WEATHER_USER_AGENT", DEFAULT_USER_AGENT),
    }
    request_headers.update(headers or {})

    status_code = None
    error_type = "unknown error"
    for attempt in range(1, attempts + 1):
        delay = 2 ** (attempt - 1)
        status_code = None
        try:
            request = Request(url, headers=request_headers)
            with urlopen(request, timeout=timeout_seconds) as response:
                return parse(response)
        except HTTPError as exc:
            status_code = exc.code
            error_type = f"HTTP {exc.code}"
            delay = _retry_delay(exc.headers.get("Retry-After"), delay)
            exc.close()
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            error_type = type(exc).__name__

        if attempt < attempts:
            # Do not retry earlier than requested or stall the whole daily job.
            if delay > 60:
                break
            time.sleep(delay)

    safe_url = redacted_url or url
    # The underlying exception can contain an API key in its URL or reason.
    raise RequestError(
        f"Request failed after {attempt} attempt(s) ({error_type}): {safe_url}",
        status_code=status_code,
    ) from None

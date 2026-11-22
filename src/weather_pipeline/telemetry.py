"""Collection manifests and timing diagnostics; never store weather values or secrets."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from weather_pipeline.http import RequestError
from weather_pipeline.storage import write_json
from weather_pipeline.windows import utc_text

CONTEXT_FIELDS = {"provider", "station_id", "target_date_local", "snapshot_date_utc",
                  "event_ticker", "market_open_time_utc"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def failure_reason(exc: Exception) -> str:
    if isinstance(exc, RequestError):
        return {401: "authentication", 402: "quota", 403: "access_denied", 429: "quota"}.get(exc.status_code, "request_failed")
    message = str(exc).lower()
    if "incomplete" in message:
        return "incomplete_window"
    if "decrypt" in message or "encrypted" in message:
        return "archive_unreadable"
    return "invalid_response" if isinstance(exc, (ValueError, TypeError, KeyError)) else "collection_failed"


class RunLog:
    def __init__(self, root: Path, kind: str, *, clock=now_utc):
        self.clock = clock
        started = clock()
        run_id = os.getenv("GITHUB_RUN_ID")
        attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
        identity = f"{run_id}-{attempt}" if run_id else uuid.uuid4().hex
        self.path = root / "collection_runs" / started.strftime("%Y/%m") / f"{kind}-{identity}.json"
        self.data = {
            "schema_version": 1, "kind": kind, "status": "running",
            "collector_started_at_utc": utc_text(started),
            "github_run_id": run_id, "github_run_attempt": attempt,
            "github_job": os.getenv("GITHUB_JOB"),
            "trigger": os.getenv("GITHUB_EVENT_NAME", "local"),
            "trigger_schedule": os.getenv("TRIGGER_SCHEDULE"),
            "runner_ready_at_utc": os.getenv("RUNNER_READY_AT_UTC"),
            "expected": [], "requests": [], "discovery": [],
        }
        self.save()

    def save(self):
        write_json(self.path, self.data)

    def expect(self, items: list[dict]):
        # Repeated discovery polls must not multiply expected captures.
        for item in items:
            item = {key: value for key, value in item.items() if key in CONTEXT_FIELDS}
            if item not in self.data["expected"]:
                self.data["expected"].append(item)
        self.save()

    def request(self, context: dict, started: datetime, finished: datetime, error: Exception | None = None):
        self.data["requests"].append({
            **{key: value for key, value in context.items() if key in CONTEXT_FIELDS},
            "request_started_at_utc": utc_text(started),
            "request_finished_at_utc": utc_text(finished),
            "request_seconds": round((finished - started).total_seconds(), 3),
            "status": failure_reason(error) if error else "response_received",
        })
        self.save()

    def finish(self, failures: int):
        self.data.update(status="failed" if failures else "completed", failure_count=failures,
                         collector_finished_at_utc=utc_text(self.clock()))
        self.save()

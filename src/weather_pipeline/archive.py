"""Read live collection archives, keeping restricted forecasts in memory."""
from __future__ import annotations

import os
from pathlib import Path

from weather_pipeline.encryption import MAGIC, MAGIC_V2
from weather_pipeline.storage import read_jsonl

PROTECTED_PROVIDERS = frozenset({"meteosource", "openweathermap", "pirate_weather", "visual_crossing", "weatherbit", "tomorrow_io"})
MIGRATION_PROVIDERS = frozenset({"meteosource", "openweathermap", "pirate_weather", "visual_crossing"})


class ArchiveKeyUnavailable(ValueError):
    pass


def archive_provider(path: Path) -> str | None:
    return next((p for p in PROTECTED_PROVIDERS if path.name.endswith(f".{p}.enc")), None)


def read_archive(path: Path, *, key=None, legacy_key=None) -> list[dict]:
    provider = archive_provider(path)
    if not provider:
        raise ValueError("Unknown archive provider")
    with path.open("rb") as handle:
        magic = handle.read(len(MAGIC_V2))
    if magic == MAGIC:
        if provider != "visual_crossing":
            raise ValueError("Legacy encryption is supported only for Visual Crossing")
        secret = legacy_key or os.getenv("VISUALCROSSING_API_KEY")
    elif magic == MAGIC_V2:
        secret = key or os.getenv("DATA_ENCRYPTION_KEY")
    else:
        raise ValueError("Unknown encrypted archive format")
    if not secret:
        raise ArchiveKeyUnavailable("Archive decryption key is not available")
    rows = read_jsonl(path, encryption_key=secret)
    if any(not isinstance(r, dict) or r.get("provider") != provider for r in rows):
        raise ValueError("Archive contains an unexpected provider")
    return rows


def load_category(root: Path, category: str, *, key: str | None = None,
                  legacy_key: str | None = None) -> tuple[list[dict], list[dict]]:
    rows, problems = [], []
    for path in sorted((root / category).rglob("*.jsonl*")):
        if path.name.endswith(".tmp") or path.suffix not in {".jsonl", ".enc"}:
            continue
        provider = archive_provider(path)
        encrypted = path.suffix == ".enc"
        if encrypted and not provider:
            problems.append({"category": category, "file": path.name, "reason": "unknown_archive_format"})
            continue
        try:
            records = read_archive(path, key=key, legacy_key=legacy_key) if encrypted else read_jsonl(path)
            if not all(isinstance(row, dict) for row in records):
                raise ValueError("Archive rows must be objects")
            rows.extend(records)
        except ArchiveKeyUnavailable:
            problems.append({"category": category, "file": path.name, "provider": provider,
                             "reason": "decryption_key_unavailable"})
        except (ValueError, OSError, ImportError):
            # Never echo decrypted data, keys, or parse-error contents into public reports.
            problems.append({"category": category, "file": path.name,
                             "provider": provider if encrypted else "unknown",
                             "reason": "archive_unreadable"})
    return rows, problems


def forecast_targets(root: Path) -> set[tuple[str, str]]:
    """Only station-dates with a saved forecast, including encrypted-only successes."""
    targets = set()
    for category in ("forecasts", "market_forecasts"):
        rows, _ = load_category(root, category)
        targets.update((r["station_id"], r["target_date_local"]) for r in rows)
    for category in ("daily_collection", "market_collection"):
        rows, _ = load_category(root, category)
        targets.update((r["station_id"], r["target_date_local"]) for r in rows
                       if r.get("status") in {"saved", "existing", "near_open", "late"})
    return targets

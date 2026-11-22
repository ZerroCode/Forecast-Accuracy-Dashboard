"""Offline health reporting and fair comparisons of genuinely saved forecasts."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from weather_pipeline.archive import PROTECTED_PROVIDERS, load_category
from weather_pipeline.kalshi import parse_time
from weather_pipeline.verification import (
    DAILY_TIME, DAILY_TOLERANCE, MIN_SCORE_DATES, Outcomes, aggregate_scores,
    identity, inspect_forecast,
)
from weather_pipeline.windows import utc_text

KINDS = {"daily": "forecasts", "market": "market_forecasts"}
CONTEXT = ("provider", "station_id", "target_date_local", "snapshot_date_utc",
           "event_ticker", "market_open_time_utc")


def context(row):
    return {key: row[key] for key in CONTEXT if key in row}


def seconds(start, end):
    if not start or not end:
        return None
    return round((parse_time(end) - parse_time(start)).total_seconds(), 3)


def timing_summary(run):
    """Separate creation/queue/setup/discovery/request delays without guessing a cron slot."""
    result = {key: run.get(key) for key in (
        "kind", "status", "failure_count", "github_run_id", "github_run_attempt", "workflow_url",
        "trigger", "trigger_schedule", "opening_pilot_wait_seconds", "timing_status", "workflow_created_at_utc",
        "workflow_started_at_utc", "job_started_at_utc", "runner_ready_at_utc",
        "collector_started_at_utc", "collector_finished_at_utc")}
    for name, start, end in (
        ("creation_to_job_seconds", "workflow_created_at_utc", "job_started_at_utc"),
        ("job_to_collector_seconds", "job_started_at_utc", "collector_started_at_utc"),
        ("setup_seconds", "runner_ready_at_utc", "collector_started_at_utc"),
        ("collector_seconds", "collector_started_at_utc", "collector_finished_at_utc"),
    ):
        result[name] = seconds(run.get(start), run.get(end))
    result["discovery_seconds"] = round(sum(
        seconds(item.get("started_at_utc"), item.get("finished_at_utc")) or 0
        for item in run.get("discovery", [])), 3)
    result["requests"] = []
    for request in run.get("requests", []):
        item = {**context(request), **{k: request.get(k) for k in (
            "request_started_at_utc", "request_finished_at_utc", "request_seconds", "status")}}
        opening = request.get("market_open_time_utc")
        item["opening_to_workflow_creation_seconds"] = seconds(opening, run.get("workflow_created_at_utc"))
        item["opening_to_response_seconds"] = seconds(opening, request.get("request_finished_at_utc"))
        result["requests"].append(item)
    return result


def opening_coverage(contracts, cutoff, now, qualified, *, available):
    """Count discovered station-days once per metric, including pending outcomes."""
    events = defaultdict(list)
    for row in contracts:
        events[row["event_ticker"]].append(row)
    expected = set()
    for rows in events.values():
        if any(r.get("validation_errors") != [] for r in rows):
            continue
        identities = {(r["station_id"], r["target_date_local"], r["temperature_metric"],
                       parse_time(r["market_open_time_utc"])) for r in rows}
        if len(identities) != 1:
            continue
        station, day, metric, opening = identities.pop()
        if metric in {"high", "low"} and cutoff <= opening.date() and opening <= now:
            expected.add((station, day, metric))
    shared = qualified & expected
    by_metric = {}
    for metric in ("high", "low"):
        by_metric[metric] = {
            "expected_station_days": sum(m == metric for _, _, m in expected),
            "qualified_station_days": sum(m == metric for _, _, m in shared) if available else None,
        }
    paired_dates = {day for station, day, metric in shared
                    if metric == "high" and (station, day, "low") in shared}
    return {"metrics": by_metric, "paired_dates": len(paired_dates) if available else None,
            "required_dates": MIN_SCORE_DATES,
            "status": ("unavailable" if not available else
                       "reached" if len(paired_dates) >= MIN_SCORE_DATES else "collecting")}


def build_reports(root: Path, stations, now: datetime, *, lookback_days=30, key=None):
    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")
    by_station = {s.station_id: s for s in stations}
    cutoff = now.date() - timedelta(days=lookback_days - 1)
    problems, loaded = [], {}
    for category in (*KINDS.values(), "markets", "observations", "daily_collection", "market_collection"):
        loaded[category], errors = load_category(root, category, key=key)
        problems.extend(errors)
    runs = []
    for path in sorted((root / "collection_runs").rglob("*.json")):
        try:
            run = json.loads(path.read_text())
            started = parse_time(run["collector_started_at_utc"])
            if cutoff <= started.date() and started <= now:
                runs.append(run)
        except (ValueError, KeyError, TypeError, OSError):
            problems.append({"category": "collection_runs", "file": path.name, "reason": "invalid_manifest"})

    # An as-of report must not use outcomes published after its timestamp. Invalid
    # outcome records are reported without embedding their content in public output.
    for category in ("markets", "observations"):
        usable = []
        required = {"station_id", "target_date_local", "retrieved_at_utc"}
        if category == "markets":
            required |= {"market_ticker", "rules_version", "temperature_metric", "event_ticker",
                         "market_open_time_utc", "window_start_utc", "window_end_utc"}
        for row in loaded[category]:
            try:
                if not all(isinstance(row.get(k), str) for k in required):
                    raise ValueError("Missing outcome fields")
                date.fromisoformat(row["target_date_local"])
                if category == "markets":
                    for field in ("market_open_time_utc", "window_start_utc", "window_end_utc"):
                        parse_time(row[field])
                if parse_time(row["retrieved_at_utc"]) <= now:
                    usable.append(row)
            except (ValueError, KeyError, TypeError):
                problems.append({"category": category, "reason": "invalid_outcome_metadata"})
        loaded[category] = usable
    outcomes = Outcomes(loaded["markets"], loaded["observations"])
    details, samples, rosters = [], [], {}
    excluded = sorted({p["provider"] for p in problems if p.get("provider") in PROTECTED_PROVIDERS})
    for kind, category in KINDS.items():
        expected, saved, audits, duplicate = {}, {}, {}, set()
        first_seen = {}

        def register(row):
            item = context(row)
            unit = identity(kind, item)
            anchor = (date.fromisoformat(item["snapshot_date_utc"]) if kind == "daily"
                      else parse_time(item["market_open_time_utc"]).date())
            if anchor > now.date():
                return None
            first_seen[item["provider"]] = min(first_seen.get(item["provider"], anchor), anchor)
            if cutoff <= anchor:
                expected[unit] = item
                return unit
            return None

        for row in loaded[category]:
            try:
                unit = register(row)
                if unit is not None:
                    if unit in saved:
                        duplicate.add(unit)
                    saved[unit] = row
            except (ValueError, KeyError, TypeError):
                problems.append({"category": category, "reason": "invalid_forecast_identity"})
        for row in loaded[kind + "_collection"]:
            try:
                unit = register(row)
                if unit is not None:
                    audits[unit] = row
            except (ValueError, KeyError, TypeError):
                problems.append({"category": kind + "_collection", "reason": "invalid_audit"})
        kind_runs = sorted((r for r in runs if r["kind"] == kind), key=lambda r: r["collector_started_at_utc"])
        for run in kind_runs:
            for item in run.get("expected", []):
                register(item)
        unavailable_dates = set()
        for problem in problems:
            if problem["category"] == category and problem.get("provider") in PROTECTED_PROVIDERS:
                provider = problem["provider"]
                try:
                    day = date.fromisoformat(problem["file"][:10])
                    unavailable_dates.add((provider, day.isoformat()))
                except ValueError:
                    day = cutoff
                first_seen[provider] = min(first_seen.get(provider, day), day)
        # Current comparison roster includes configured providers that failed every request.
        rosters[kind] = sorted({r["provider"] for r in kind_runs[-1].get("expected", [])}
                               if kind_runs and kind_runs[-1].get("expected") else first_seen)

        if kind == "daily":
            # Infer missed scheduled runs after the first observed activation. Actual run
            # manifests supply that day's roster when available, including provider removals.
            manifests_by_day = defaultdict(set)
            for run in kind_runs:
                day = parse_time(run["collector_started_at_utc"]).date()
                manifests_by_day[day].update(r["provider"] for r in run.get("expected", []))
            for provider, first in first_seen.items():
                day = max(first, cutoff)
                while datetime.combine(day, DAILY_TIME) + timedelta(seconds=DAILY_TOLERANCE) <= now:
                    if provider in manifests_by_day.get(day, rosters[kind]):
                        anchor = datetime.combine(day, DAILY_TIME)
                        for station in stations:
                            if station.active:
                                register({"provider": provider, "station_id": station.station_id,
                                          "snapshot_date_utc": day.isoformat(), "target_date_local": (
                                              anchor.astimezone(ZoneInfo(station.timezone)).date() + timedelta(days=1)
                                          ).isoformat()})
                    day += timedelta(days=1)
        else:
            # Only real, validated events are expected. Never invent yesterday's opening.
            for contract in outcomes.latest.values():
                if contract.get("validation_errors") != []:
                    continue
                opening = parse_time(contract["market_open_time_utc"])
                if opening > now:
                    continue
                for provider in rosters[kind]:
                    if opening.date() >= first_seen.get(provider, now.date()):
                        register({**context(contract), "provider": provider})

        for unit, item in sorted(expected.items()):
            row, audit = saved.get(unit), audits.get(unit, {})
            detail = {"kind": kind, **item, "collection_status": "saved" if row else audit.get("status", "missing")}
            # Audit error strings from old versions can contain provider payloads: allowlist only.
            if audit.get("reason"):
                detail["failure_reason"] = audit["reason"]
            if not row:
                partition = item["snapshot_date_utc"] if kind == "daily" else item["target_date_local"]
                if item["provider"] in excluded and (
                    detail["collection_status"] in {"saved", "existing", "near_open", "late"} or
                    (not audit and (item["provider"], partition) in unavailable_dates)
                ):
                    detail["collection_status"] = "encrypted_archive_unavailable"
                elif detail["collection_status"] in {"saved", "existing", "near_open", "late"}:
                    detail["collection_status"] = "saved_archive_missing"
                details.append(detail)
                continue
            station = by_station.get(item["station_id"])
            try:
                if not station:
                    raise ValueError("Unknown station")
                quality, window, captured, cohort = inspect_forecast(kind, row, station, now)
                if unit in duplicate:
                    quality = "duplicate_snapshot"
            except (ValueError, KeyError, TypeError):
                quality, window, captured, cohort = "invalid_metadata", None, None, None
            detail.update(quality=quality, cohort=cohort)
            if captured:
                anchor = (parse_time(row["market_open_time_utc"]) if kind == "market" else
                          datetime.combine(date.fromisoformat(row["snapshot_date_utc"]), DAILY_TIME))
                detail.update(captured_at_utc=utc_text(captured), delay_seconds=(captured - anchor).total_seconds())
            if quality == "complete":
                metrics = [row.get("temperature_metric")] if kind == "market" else ["high", "low"]
                detail["outcomes"] = {}
                for metric in metrics:
                    if metric not in {"high", "low"}:
                        detail["quality"] = "invalid_metric"
                        continue
                    try:
                        status, actual, source = outcomes.resolve(kind, row, metric, window, station, now)
                    except (ValueError, KeyError, TypeError):
                        status, actual, source = "invalid_outcome_metadata", None, None
                    detail["outcomes"][metric] = status
                    if status == "ready":
                        # A market high/low pair shares a request but each scores only its own metric.
                        case = (utc_text(window.start), utc_text(window.end),
                                row["market_open_time_utc"] if kind == "market" else row["snapshot_date_utc"])
                        samples.append({"provider": row["provider"], "cohort": cohort, "metric": metric,
                                        "station_id": station.station_id, "source": source, "case": case,
                                        "captured": captured, "target_date_local": row["target_date_local"],
                                        "error": float(row[f"forecast_{metric}_f"]) - actual})
            details.append(detail)

    summaries = []
    groups = defaultdict(list)
    for detail in details:
        groups[(detail["kind"], detail["provider"], detail["station_id"])].append(detail)
    for (kind, provider, station), rows in sorted(groups.items()):
        delays = [r["delay_seconds"] for r in rows if "delay_seconds" in r]
        captures = [r["captured_at_utc"] for r in rows if "captured_at_utc" in r]
        summaries.append({"kind": kind, "provider": provider, "station_id": station, "expected": len(rows),
                          "collection_statuses": dict(Counter(r["collection_status"] for r in rows)),
                          "quality_statuses": dict(Counter(r["quality"] for r in rows if "quality" in r)),
                          "cohorts": dict(Counter(r["cohort"] for r in rows if r.get("cohort"))),
                          "outcome_statuses": dict(Counter(s for r in rows for s in r.get("outcomes", {}).values())),
                          "latest_capture_utc": max(captures) if captures else None,
                          "median_delay_seconds": median(delays) if delays else None})
    # Incomplete public forecast/outcome archives cannot establish a fair roster or
    # a consistent settlement. Encrypted-provider failures can be explicitly excluded.
    blocked = any(p.get("category") in {*KINDS.values(), "markets", "observations"} and
                  p.get("provider") not in PROTECTED_PROVIDERS for p in problems)
    near_open_cases = set()
    score_groups = [] if blocked else aggregate_scores(
        samples, rosters, excluded=excluded, near_open_cases=near_open_cases)
    coverage = opening_coverage(outcomes.latest.values(), cutoff, now, near_open_cases,
                                available=not blocked and bool(rosters["market"])
                                and not set(excluded).intersection(rosters["market"]))
    common = {"schema_version": 1, "generated_at_utc": utc_text(now), "lookback_days": lookback_days,
              "status": "partial" if problems else "complete", "archive_problems": problems,
              "comparison_rosters": rosters, "excluded_providers": excluded}
    health = {**common, "summary": summaries, "snapshots": details,
              "runs": [timing_summary(run) for run in kind_sorted(runs)]}
    accuracy = {**common, "near_open_coverage": coverage, "minimum_distinct_dates": MIN_SCORE_DATES,
                "comparison_tolerance_seconds": 600, "positive_bias_means": "forecast_too_warm",
                "ranking_status": "blocked_by_unreadable_archive" if blocked else (
                    "available" if any(g["status"] == "scored" for g in score_groups) else "insufficient_common_history"),
                "groups": score_groups}
    return health, accuracy


def kind_sorted(runs):
    return sorted(runs, key=lambda r: (r["collector_started_at_utc"], r["kind"]))


def markdown_summary(health, accuracy):
    statuses = Counter(r["collection_status"] for r in health["snapshots"])
    cohorts = Counter(r["cohort"] for r in health["snapshots"] if r.get("cohort"))
    outcomes = Counter(s for r in health["snapshots"] for s in r.get("outcomes", {}).values())
    lines = ["# Live forecast collection", "", f"As of {health['generated_at_utc']} — {health['status']} analysis.", "",
             f"Expected captures: {len(health['snapshots'])}. Ranking: {accuracy['ranking_status']}.", "",
             "| Measure | Status | Count |", "| --- | --- | ---: |"]
    for measure, counts in (("Collection", statuses), ("Timing", cohorts), ("Outcome", outcomes)):
        lines.extend(f"| {measure} | {status} | {count} |" for status, count in sorted(counts.items()))
    coverage = accuracy["near_open_coverage"]
    lines.extend(["", "## Market openings", ""])
    if coverage["status"] == "unavailable":
        lines.append("Full-roster coverage is unavailable for this report.")
    else:
        for metric, counts in coverage["metrics"].items():
            lines.append(f"- {metric.title()}: {counts['qualified_station_days']} of "
                         f"{counts['expected_station_days']} discovered station-days qualified.")
        lines.extend(["", f"Dates with a verified high and low at the same station: "
                      f"{coverage['paired_dates']} (milestone: {coverage['required_dates']})."])
    if any("meteosource" in roster for roster in accuracy.get("comparison_rosters", {}).values()):
        lines.extend(["", "Weather data by [Meteosource](https://www.meteosource.com/)."])
    if health["archive_problems"]:
        lines.extend(["", f"Archive problems: {len(health['archive_problems'])}; inspect health.json."])
    lines.extend(["", "Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.",
                  f"Scores remain unpublished until {MIN_SCORE_DATES} common target dates are available.",
                  "Individual predictions, outcomes and errors are not included in these reports."])
    return "\n".join(lines) + "\n"

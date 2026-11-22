"""Strict window/outcome matching and aggregate-only forecast scoring."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean

from weather_pipeline.kalshi import parse_time
from weather_pipeline.windows import local_day, standard_day, utc_text

DAILY_TIME = time(12, 17, tzinfo=timezone.utc)
DAILY_TOLERANCE = 3600
COMPARISON_TOLERANCE = 600
MIN_SCORE_DATES = 5


def number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def identity(kind, row):
    common = (kind, row["provider"], row["station_id"], row["target_date_local"])
    return common + ((row["event_ticker"], row["market_open_time_utc"]) if kind == "market"
                     else (row["snapshot_date_utc"],))


def inspect_forecast(kind, row, station, now):
    """Return safe diagnostics, plus the window and actual capture time for scoring."""
    target = date.fromisoformat(row["target_date_local"])
    window = (standard_day if kind == "market" else local_day)(target, station.timezone)
    for field in ("window_start_utc", "window_end_utc"):
        if field in row and row[field] != window.metadata()[field]:
            return "window_mismatch", None, None, None
    if kind == "market" and any(row.get(k) != v for k, v in window.metadata().items()):
        return "window_mismatch", None, None, None
    if row.get("aggregation_method") == "max_min_of_3_hour_points":
        return "legacy_spatial_extrema", None, None, None
    resolution = row.get("source_resolution")
    if resolution in {"1h", "3h"}:
        step = 3600 if resolution == "1h" else 10800
        expected = len(range(math.ceil(window.start.timestamp() / step) * step,
                             int(window.end.timestamp()), step))
        if row.get("sample_count") != expected or row.get("expected_sample_count") != expected:
            return "incomplete_window", None, None, None
    elif not (resolution == "daily" or (kind == "daily" and row["provider"] == "open_meteo")):
        return "coverage_unverified", None, None, None
    if any(number(row.get(f"forecast_{metric}_f")) is None for metric in ("high", "low")):
        return "invalid_temperature", None, None, None
    captured = parse_time(row["retrieved_at_utc"])
    requested = parse_time(row["request_started_at_utc"]) if row.get("request_started_at_utc") else None
    if requested and requested > captured:
        return "invalid_request_timing", None, None, None
    if captured > now:
        return "future_capture_timestamp", None, None, None
    if captured >= window.start:
        return "captured_after_measurement_start", None, None, None
    if kind == "market":
        anchor = parse_time(row["market_open_time_utc"])
        delay = (captured - anchor).total_seconds()
        if delay < 0 or (requested and requested < anchor):
            return "captured_before_open", None, None, None
        cohort = "market_near_open" if delay <= 600 else "market_late"
    else:
        anchor = datetime.combine(date.fromisoformat(row["snapshot_date_utc"]), DAILY_TIME)
        delay = (captured - anchor).total_seconds()
        cohort = "daily_before_schedule" if delay < 0 else ("daily_scheduled" if delay <= DAILY_TOLERANCE else "daily_late")
        # Old daily rows record job start, not response arrival; don't rank on guessed cutoffs.
        if not row.get("request_started_at_utc"):
            return "capture_time_unverified", window, captured, cohort
    return "complete", window, captured, cohort


class Outcomes:
    def __init__(self, contracts, observations):
        self.by_ref = {}
        self.latest = {}
        for row in sorted(contracts, key=lambda r: parse_time(r["retrieved_at_utc"])):
            self.by_ref[(row["market_ticker"], row["rules_version"])] = row
            self.latest[row["market_ticker"]] = row
        self.by_day = defaultdict(list)
        for row in self.latest.values():
            self.by_day[(row["station_id"], row["target_date_local"], row["temperature_metric"])].append(row)
        self.observations = {(r["station_id"], r["target_date_local"]): r for r in
                             sorted(observations, key=lambda r: parse_time(r["retrieved_at_utc"]))}

    @staticmethod
    def settlement(rows, station_id, target, metric, window, source=None):
        if not rows:
            return "awaiting_outcome", None, None
        for row in rows:
            if row.get("validation_errors") != []:
                return "invalid_contract", None, None
            if (row["station_id"], row["target_date_local"], row["temperature_metric"]) != (station_id, target, metric):
                return "outcome_identity_mismatch", None, None
            if any(row.get(k) != v for k, v in window.metadata().items() if k != "daily_boundary"):
                return "outcome_window_mismatch", None, None
        sources = {r.get("settlement_source_name") for r in rows}
        if len(sources) != 1 or None in sources or (source and sources != {source}):
            return "outcome_source_mismatch", None, None
        if any(r.get("status") != "finalized" or r.get("result") not in {"yes", "no"} for r in rows):
            return "awaiting_outcome", None, None
        values = {number(r.get("expiration_value")) for r in rows}
        if None in values:
            return "awaiting_outcome", None, None
        if len(values) != 1:
            return "conflicting_outcomes", None, None
        return "ready", next(iter(values)), "kalshi_settlement:" + next(iter(sources))

    def resolve(self, kind, row, metric, window, station, now):
        if now < window.end:
            return "measurement_pending", None, None
        if kind == "market":
            refs = row.get("market_contracts", [])
            if not refs:
                return "contract_reference_missing", None, None
            contracts = []
            for ref in refs:
                key = (ref["market_ticker"], ref["rules_version"])
                contract = self.by_ref.get(key)
                latest = self.latest.get(key[0])
                if latest and latest["rules_version"] != key[1]:
                    return "contract_rules_changed", None, None
                if not contract:
                    return "awaiting_outcome", None, None
                if (contract.get("event_ticker") != row.get("event_ticker") or
                        contract.get("market_open_time_utc") != row.get("market_open_time_utc")):
                    return "outcome_identity_mismatch", None, None
                contracts.append(contract)
            return self.settlement(contracts, station.station_id, row["target_date_local"], metric,
                                   window, row.get("settlement_source_name"))
        contracts = self.by_day[(station.station_id, row["target_date_local"], metric)]
        if contracts:
            return self.settlement(contracts, station.station_id, row["target_date_local"], metric, window)
        observation = self.observations.get((station.station_id, row["target_date_local"]))
        if not observation:
            return "awaiting_outcome", None, None
        if observation.get("ncei_station_id") != station.ncei_station_id:
            return "outcome_identity_mismatch", None, None
        if not all(observation.get(k) == v for k, v in window.metadata().items()
                   if k in {"window_start_utc", "window_end_utc"}):
            return "outcome_window_unverified", None, None
        attributes = str(observation.get("tmax_attributes" if metric == "high" else "tmin_attributes") or "").split(",")
        if len(attributes) < 2 or attributes[1]:
            return "outcome_quality_unverified", None, None
        value = number(observation.get(f"actual_{metric}_f"))
        return ("ready", value, "noaa_ncei_daily_summaries") if value is not None else ("awaiting_outcome", None, None)


def aggregate_scores(samples, rosters, *, excluded=(), near_open_cases=None):
    """All providers in each cohort use identical cases and arrivals within ten minutes.

    Individual predictions, outcomes and errors never leave this function. Suppress
    small aggregates, including the one-row bias that would reveal a private forecast.
    """
    cases = defaultdict(dict)
    duplicates = set()
    for sample in samples:
        key = (sample["cohort"], sample["metric"], sample["station_id"], sample["source"], sample["case"])
        if sample["provider"] in cases[key]:
            duplicates.add(key)
        cases[key][sample["provider"]] = sample
    groups = defaultdict(list)
    counts = defaultdict(lambda: {"candidate_cases": 0, "missing_provider_cases": 0,
                                  "capture_time_mismatch_cases": 0, "duplicate_cases": 0})
    for key, by_provider in cases.items():
        cohort, metric, station, source, case = key
        kind = "market" if cohort.startswith("market_") else "daily"
        roster = sorted(set(rosters[kind]) - set(excluded))
        for location in (station, "all"):
            group = (cohort, metric, location, source, tuple(roster))
            counts[group]["candidate_cases"] += 1
            if key in duplicates:
                counts[group]["duplicate_cases"] += 1
                continue
            if not roster or any(p not in by_provider for p in roster):
                counts[group]["missing_provider_cases"] += 1
                continue
            selected = [by_provider[p] for p in roster]
            times = [s["captured"] for s in selected]
            if (max(times) - min(times)).total_seconds() > COMPARISON_TOLERANCE:
                counts[group]["capture_time_mismatch_cases"] += 1
                continue
            groups[group].append(selected)
            if (near_open_cases is not None and location == "all" and cohort == "market_near_open"
                    and len(roster) == len(rosters[kind])):
                near_open_cases.add((station, selected[0]["target_date_local"], metric))
    result = []
    for group in sorted(counts):
        cohort, metric, station, source, roster = group
        selected = groups[group]
        distinct_dates = len({batch[0]["target_date_local"] for batch in selected})
        publish = distinct_dates >= MIN_SCORE_DATES
        metrics = []
        for i, provider in enumerate(roster):
            errors = [batch[i]["error"] for batch in selected]
            metrics.append({"provider": provider, "n": len(errors),
                            "mae_f": round(mean(abs(e) for e in errors), 4) if publish else None,
                            "bias_f": round(mean(errors), 4) if publish else None,
                            "within_1f": round(mean(abs(e) <= 1 for e in errors), 4) if publish else None,
                            "within_2f": round(mean(abs(e) <= 2 for e in errors), 4) if publish else None})
        result.append({"cohort": cohort, "metric": metric, "station_id": station, "outcome_source": source,
                       "providers": list(roster), "common_cases": len(selected), "distinct_dates": distinct_dates,
                       "status": "scored" if publish else "insufficient_common_history", **counts[group],
                       "metrics": metrics})
    return result

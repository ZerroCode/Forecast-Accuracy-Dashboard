# Reports and scoring

## Read the latest provider comparison

Both accuracy files contain daily and market comparisons. The [public report reader](../src/public_reports.mjs)
loads the two published files and selects the one with the newest `generated_at_utc`.
Daily wins a timestamp tie. A newer partial or blocked report takes precedence over
older scores. If only one file loads successfully, `unavailableWorkflows` names
the missing or unreadable publication. If neither loads, the reader raises an error.

This example assumes the importing page or module is at the root of the served repository.

```js
import { loadLatestReport, getComparison } from "./src/public_reports.mjs";

const { workflow, report, unavailableWorkflows } = await loadLatestReport();
const comparison = getComparison(report, {
  stationId: "all",
  metric: "high",
  cohort: "daily_late",
  outcomeSource: "kalshi_settlement:The Weather Company",
});
```

The default URLs resolve relative to the module in a web-served repository.
For another layout, pass the absolute URL of the public verification directory,
including its trailing slash. Filters use the identifiers in `report.groups`.
A scored comparison returns the published provider metrics sorted by mean absolute
error. A pending comparison returns a waiting message, shared case and date counts,
and an empty score list. A blocked comparison returns the archive error message.
For a partial report, display `comparison.excludedProviders` alongside any scores.
The public accuracy files supply all inputs to this reader.

## Stations

[`config/stations.csv`](../config/stations.csv) is the single registry for forecasts
and NOAA observations. [`config/kalshi_markets.json`](../config/kalshi_markets.json)
maps those stations to 16 daily high/low market series.

| City | Station | NWS ID |
| --- | --- | --- |
| New York City | Central Park | KNYC |
| Los Angeles | Los Angeles International Airport | KLAX |
| Chicago | Midway Airport | KMDW |
| Miami | Miami International Airport | KMIA |
| Dallas | Dallas/Fort Worth International Airport | KDFW |
| Seattle | Seattle-Tacoma International Airport | KSEA |
| Boston | Logan International Airport | KBOS |
| San Francisco | San Francisco International Airport | KSFO |

Historical O'Hare and Love Field records retain their original station IDs.
Exclude them from comparisons with Midway and DFW markets.

## Comparing the data

Morning snapshots target the next local calendar day, midnight to midnight with
daylight saving. Market snapshots use an explicit 24-hour **local-standard-time**
window, which appears as 1 AM to 1 AM during daylight saving. Keep these datasets
separate when comparing accuracy.

Before collecting a market forecast, the collector checks the contract's station
code, date, temperature metric, units, settlement source, and closing time against
the configured mapping and window. Mismatches are reported for review. Contract
rules are versioned so each forecast can be traced to the rules used at collection.

| Market capture status | Meaning |
| --- | --- |
| `near_open` | Response arrived within 10 minutes of opening by default |
| `late` | Response arrived later, but before the measurement day began |
| `missed_before_measurement_start` | No snapshot was captured before the measurement day began |

For opening-time analysis, filter `eligible_for_opening_comparison=true` and inspect
`seconds_after_market_open`. A near-opening snapshot is not an exact opening-second
forecast. Manual runs cannot reconstruct forecasts from a past opening.

Hourly and three-hourly extrema can miss temperatures between samples. Incomplete
sample coverage is rejected. NOAA observations are comparison data, not automatically
the official settlement result: follow each contract's recorded source. Contracts
checked in October 2026 named The Weather Company. The daily workflow refreshes
known events linked to saved forecasts, including old unresolved settlements and
14 days of recent corrections. It does not discover a historical archive or request
replacement forecasts for missed openings.

Files are stored as date-partitioned JSONL under `data/`. Full API responses are
off by default. See [data/README.md](../data/README.md) for file layout, schema notes,
and historical calculation caveats.

## Live health and accuracy reports

`src/report_collection.py` reads saved data without network calls and writes
`health.json`, `accuracy.json`, and `summary.md`. Local output goes to the ignored
`reports/live/` directory. Actions commits the latest reports under
`data/verification/daily/` or `data/verification/market/` and adds a job summary.

Health reports show expected versus saved captures, missing/failed requests,
complete reporting windows, capture delays, and pending or rejected outcomes.
Run manifests preserve providers that failed every request. Missing daily runs are
inferred from previously observed activation and the configured schedule; before
manifests existed, those expectations are estimates. Market expectations use only
validated events actually discovered, so a completely undiscovered event cannot be
reported as missing.

Scoring follows these rules:

- Match the station, target date, high/low metric, reporting-window boundaries,
  and outcome source. Market snapshots also require the original contract versions
  and opening time. A changed rule or conflicting bracket outcome blocks scoring.
- Use numeric `expiration_value` only from finalized contracts with a yes/no result.
  A NOAA daily value is eligible only with verified window boundaries and an empty
  quality flag. Current NCEI archives lack those boundaries, so they remain
  `outcome_window_unverified` when no matching settlement is available. Local civil
  days and standard days are not interchangeable during daylight saving.
- Separate `daily_scheduled` (12:17–13:17 UTC), `daily_before_schedule`, `daily_late`,
  `market_near_open` (within 10 minutes), and `market_late`. Legacy daily snapshots
  recorded a job timestamp instead of response arrival and remain
  `capture_time_unverified`; their timestamps are never reconstructed.
- Compare the current provider roster only on common station-days with arrivals
  within 10 minutes of each other. Missing providers and timing mismatches exclude
  a case for everyone. High and low events score only their own metric, even when
  both reused the same weather request. Incomplete windows and legacy OpenWeather
  spatial extrema are excluded.
- Publish sample count, mean absolute error, signed bias (positive means too warm),
  and fractions within 1°F/2°F by station, metric, capture group, and outcome source.
  Error statistics remain null until at least five common target dates exist.
  This is a publication minimum, not a claim of statistical significance.

Protected forecasts are decrypted in memory using `DATA_ENCRYPTION_KEY` (or the
original Visual Crossing API key for unmigrated legacy files).
Public reports contain no individual predictions, outcome values, or errors.
Missing/wrong keys produce an explicit partial-analysis report; affected providers
are excluded and the reduced comparison roster is shown. No decrypted file is written.
Corrections are picked up when reports are regenerated; errors are not appended or
counted twice. `--as-of` excludes outcomes retrieved after the requested time, but
does not reconstruct overwritten historical settlement revisions.

Timing diagnostics distinguish workflow creation, job start, setup, discovery, and
request duration. They do not invent a scheduled trigger timestamp: a cron expression
does not identify which delayed run GitHub eventually created. For example, market
[run 43623868507](https://github.com/ZerroCode/Forecast-Accuracy-Dashboard/actions/runs/43623868507)
was created at 17:57 UTC on November 14, almost three hours after the 15:00 opening.

### Market opening coverage

The report’s **Market openings** section shows qualified versus expected station-days
for each metric within the report lookback. Expected counts cover validated, discovered
events whose openings have passed, including still-pending outcomes. Each station/date
counts once per metric. Qualifying requires verified outcomes and comparable near-opening
captures from the full current market roster. A date counts toward the five-date
milestone when at least one station qualifies for both high and low on that date.
Coverage is marked unavailable when archive problems prevent a full comparison.

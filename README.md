# Forecast Accuracy Dashboard

This project compares daily temperature forecasts at the eight stations used by
Kalshi’s high and low temperature markets. Scheduled workflows capture forecasts
and verify them against observed temperatures or contract settlements. A separate
historical evaluation tests forecast models and can download Kalshi price snapshots
on demand for comparison. The dashboard is planned.

## Latest reports

Each workflow publishes a snapshot of the analysis. The summary shows collection
health, timing, and provider accuracy across stations. It lists providers by mean
absolute error and shows signed bias, shared station-days, and distinct target
dates for each high/low metric, capture window, and outcome source. The accuracy
file also contains station-level scores and sample counts.

| Publishing workflow | Collection summary | Provider scores |
| --- | --- | --- |
| Daily weather | [Summary](data/verification/daily/summary.md) | [Accuracy](data/verification/daily/accuracy.json) |
| Market openings | [Summary](data/verification/market/summary.md) | [Accuracy](data/verification/market/accuracy.json) |

### Read the latest provider comparison

Both accuracy files contain daily and market comparisons. The [public report reader](src/public_reports.mjs)
loads the two published files and selects the one with the newest `generated_at_utc`.
Daily wins a timestamp tie. A newer partial or blocked report takes precedence over
older scores. If only one file loads successfully, `unavailableWorkflows` names
the missing or unreadable publication. If neither loads, the reader raises an error.

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

### Generate a report offline

From the repository root, use Python 3.11 or newer and install the collection
dependencies once in your Python environment. Then build the report from saved files:

```shell
python -m pip install -r requirements-collection.txt
python src/report_collection.py
```

Open `reports/live/summary.md` for the summary or `reports/live/accuracy.json` for
scores. The report command makes no network requests. Without the archive key it
uses the public forecasts and lists the excluded providers. If you have the existing
key in a local `.env`, pass `--key-file .env` to include protected forecasts.
See the [scoring rules](#live-health-and-accuracy-reports) for how comparisons qualify.

## Automatic collection

Two GitHub Actions workflows share the same [station registry](config/stations.csv).

| Workflow | Schedule (UTC) | What it collects |
| --- | --- | --- |
| [Collect daily weather data](.github/workflows/collect-weather.yml) | Daily at 12:17 | Tomorrow's forecasts, outcomes for saved forecast targets, and verification reports |
| [Collect Kalshi opening forecasts](.github/workflows/collect-market-weather.yml) | Hourly at :07, plus 13:57 and 14:57 | Contract metadata and the first available forecast after each market opens |

The extra market runs poll for at least a five-minute window, and scheduled runs
that start near 10 AM Eastern use the [opening pilot](#market-opening-pilot). Opening times come from
Kalshi's API; the schedule provides opportunities to check them. GitHub may delay
runs, so every snapshot records its actual response arrival time. Each collection
also saves an expected provider/station list and request timings, even if a provider
fails. Tests run in [separate CI](.github/workflows/test.yml), outside the timed
collection path. Both workflows regenerate health and accuracy reports after capture.

### Enable the workflows

1. Merge the collection code into `main`.
2. Under **Settings > Actions > General > Workflow permissions**, allow
   **Read and write permissions** so the workflows can commit collected data.
3. In **Actions**, run each workflow once on `main` and check its result.
4. Enable failure notifications. Subsequent runs are scheduled automatically.

Leave **Replace an existing forecast snapshot for the current UTC day** unchecked
for normal runs. Existing snapshots are skipped; missing ones are collected.
Checking it replaces daily forecasts with newer predictions. Market-opening
snapshots are immutable and have no replacement option.

Successful records are saved even when another provider fails, and the workflow
reports the failure. If a push is blocked, check repository permissions and branch
rules. The market workflow schedules 26 runs per day; account for Actions minutes
when using a private repository.

## Providers and credentials

Open-Meteo, NWS, NOAA/NCEI, and Kalshi's public market API need no keys.

| Source | Data | Configuration |
| --- | --- | --- |
| Open-Meteo | Daily forecasts; hourly temperatures for market windows | Enabled by default |
| NWS | Hourly forecasts | Enabled by default |
| NOAA/NCEI | Observed daily highs/lows | Enabled by default |
| Kalshi | Opening times, rules, thresholds, sources, and available result fields | Enabled in the market workflow |
| OpenWeather | Three-hour forecasts; encrypted storage | Secret: `OPENWEATHERMAP_API_KEY` |
| [Meteosource](https://www.meteosource.com/) | Next-day highs/lows; full hourly market windows on eligible paid tiers | Secret: `METEOSOURCE_API_KEY`; variable: `METEOSOURCE_ARCHIVAL_ALLOWED=true` |
| Pirate Weather | Live hourly forecasts in both workflows; encrypted storage | Secret: `PIRATE_WEATHER_API_KEY` |
| Visual Crossing | Live hourly forecasts in both workflows; encrypted storage | Secret: `VISUALCROSSING_API_KEY` |
| Tomorrow.io | Hourly forecasts | Secret: `TOMORROW_API_KEYS`; variable: `TOMORROW_ARCHIVAL_ALLOWED=true` |
| Weatherbit | Daily forecasts, morning workflow only | Secret: `WEATHERBIT_API_KEY`; variable: `WEATHERBIT_ARCHIVAL_ALLOWED=true` |

Add secrets and variables under **Settings > Secrets and variables > Actions**,
using the corresponding **Secrets** and **Variables** tabs. Enable archival
variables only when your provider plan permits the intended storage. Weatherbit's
daily aggregates cannot be shifted to the market reporting window. All keyed
forecast providers also require the separate `DATA_ENCRYPTION_KEY` secret. Missing
or malformed archive keys stop keyed collection instead of writing plaintext.

The scheduled workflows collect live forecasts. NOAA requests cover completed
station-dates with saved forecasts. Missing outcomes remain eligible, and the
collector checks recent outcomes for corrections for 14 days.

Meteosource uses the live [Point endpoint](https://www.meteosource.com/documentation).
The default `free` tier supplies tomorrow’s local daily high and low. Its one-day
hourly horizon is too short for regular market-opening captures, so it is omitted
from that roster. On a paid plan, set the Actions variable `METEOSOURCE_TIER` to
the tier segment of your account’s Point URL. Market collection then requests UTC
hours and requires every hour in the contract window. Set `METEOSOURCE_ARCHIVAL_ALLOWED=true`
only after confirming your plan permits encrypted retention and public aggregate
accuracy reporting. See the [API terms](https://www.meteosource.com/terms-of-service)
and [plan coverage](https://www.meteosource.com/pricing). No historical endpoint is used.

Provider keys authenticate requests. The archive key encrypts saved forecasts and
optional raw responses from keyed providers. Keep `WEATHERBIT_ARCHIVAL_ALLOWED`
and `TOMORROW_ARCHIVAL_ALLOWED` false unless your agreement permits the intended
use. For key setup, migration, rotation, and private exports, see the
[archive maintenance guide](data/README.md#archive-key-setup-and-migration).

## Stations

[`config/stations.csv`](config/stations.csv) is the single registry for forecasts
and NOAA observations. [`config/kalshi_markets.json`](config/kalshi_markets.json)
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
off by default. See [data/README.md](data/README.md) for file layout, schema notes,
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
### Market opening pilot

A worker that starts between 9:53 AM and 10:10 AM New York time keeps polling the
validated Kalshi markets through 10:10. Daylight saving changes are handled by
`America/New_York`. Each event’s API opening time, active status and actual response
arrival still determine eligibility. Outside that window a pilot dispatch runs a
single recovery pass. Regular scheduled runs also use the pilot window when they
arrive in time. The two special cron runs retain their five-minute minimum.

To avoid depending on GitHub cron delivery for the pilot, schedule this command
on an always-on host at **9:55 AM America/New_York** each day:

```shell
gh workflow run collect-market-weather.yml --repo ZerroCode/Forecast-Accuracy-Dashboard --ref main -f opening_pilot=true
```

The timer host needs authenticated GitHub CLI access to dispatch this repository’s
workflow (Actions write). Provider secrets, the archive key and data commits stay
in the normal Actions workflow. Dispatch is asynchronous and still depends on
runner availability. Inspect `runs` in `health.json` for the actual collector
start, pilot wait budget, discovery duration and response delays. A host running
the collector directly can use `python src/collect_market_forecasts.py --opening-pilot`
in an isolated checkout with its own credentials and data directory.

The report’s **Market openings** section shows qualified versus expected station-days
for each metric within the report lookback. Expected counts cover validated, discovered
events whose openings have passed, including still-pending outcomes. Each station/date
counts once per metric. Qualifying requires verified outcomes and comparable near-opening
captures from the full current market roster. A date counts toward the five-date
milestone when at least one station qualifies for both high and low on that date.
Coverage is marked unavailable when archive problems prevent a full comparison.

## Run locally

For local collection, install the dependencies in the [offline quick start](#generate-a-report-offline).
Set provider credentials and archive settings in your shell environment. GitHub
Actions supplies its secrets only to the workflows.

```shell
python -m unittest discover -s tests -v
```

The following commands make live requests and write to `data/`:

```shell
python src/collect_forecasts.py
python src/collect_market_forecasts.py
python src/collect_observations.py
python src/refresh_settlements.py
```

Use `--discover-only` with the market collector to save contract metadata without
calling weather providers, or `--wait-seconds 300` to poll near an upcoming opening.
The observation collector accepts `--lookback-days 30` to extend correction checks
for saved forecast targets. The daily forecast and observation collectors accept
`--save-raw` for debugging when the provider permits retention.

## Historical backfill

Live collection began in October 2026, which is too short for model training.
`src/backfill_history.py` downloads 2023-to-date history from free sources:

| Source | Data | Coverage |
| --- | --- | --- |
| Open-Meteo Previous Runs API | GFS, HRRR, ICON, GEM, ECMWF forecasts made ~24h (`day1`) and ~48h (`day2`; not HRRR) ahead | GFS 2023+, others 2024+ |
| Iowa Environmental Mesonet | NWS GFS MOS guidance from the previous day’s 00Z and 12Z runs | 2023+ |
| NOAA/NCEI | Observed daily highs/lows | 2023+ |
| Kalshi (live and `/historical` endpoints) | Settled brackets, results, and settled values | Varies by series |

Model forecasts are converted to daily extrema over the local-standard-time day
used by Kalshi, and days with missing hours are left blank. Per-station files are
cached under `data/history/<source>/`, so interrupted runs resume where they stopped.
`src/build_dataset.py` joins them into `data/history/dataset.csv`, one row per
station per day. NOAA highs matched Kalshi settled values on 99.7% of overlapping days.

```shell
python src/backfill_history.py            # all sources; re-run to retry failures
python src/backfill_history.py --sources kalshi
python src/build_dataset.py
```

## Models and evaluation

[`src/forecast_model/`](src/forecast_model/) combines the six forecasts with machine
learning and evaluates the result:

| Module | Purpose |
| --- | --- |
| `data.py` | Loads `dataset.csv`; fixed time split (train to Jun 2025, validate Jul–Dec 2025, test 2026) |
| `features.py` | Ensemble mean/median/spread, trailing 7/30-day bias per source, bias-corrected forecasts, season, persistence |
| `models.py` | Ridge regression and gradient boosting, tuned on validation, refit, then scored on test once |
| `uncertainty.py` | Model 3: a per-day forecast uncertainty and tail shape, learned from out-of-fold errors |
| `evaluation.py` | Baselines (each source, averages, persistence, climatology) and the error table |
| `markets.py` | Bracket probabilities from forecasts; scoring against settled brackets and Kalshi prices, paper trading, market/model blend |
| `plots.py` | Report figures |

Kalshi pays on brackets, so each prediction also needs an uncertainty. Model 3 predicts
it per day from source disagreement, how far forecasts moved since the previous run,
recent error in that city, and season, instead of using one value per city. It learns
from the mean model's errors on days held out of its training (contiguous time blocks,
with a 32-day gap after each held-out block) and chooses a normal or Student-t tail on
validation. It is scored against every settled 2026 bracket, which needs no prices.

Every result is computed at two prediction cutoffs, each using only what was
published by then:

| Cutoff | Moment | Forecasts used | Kalshi price at |
| --- | --- | --- | --- |
| `open` (main) | 11 AM ET the day before | NWS MOS 00Z run; GFS, ICON, GEM, ECMWF ~48h ahead | Same moment |
| `midnight` | Start of the measured day | NWS MOS 12Z run; all five models ~24h ahead, incl. HRRR | Same moment |

Observed temperatures enter features only through two days before the target day,
because the previous day's official report is published after both cutoffs. Every
method is scored on the same station-days. Tests enforce both rules.

```shell
python -m pip install -r requirements.txt
python src/evaluate_models.py
```

For a comparison against historical market prices, download quotes for the desired
series and cutoffs, then rerun evaluation:

```shell
python src/backfill_prices.py --cutoff open --series KXHIGHNY KXHIGHCHI --start 2026-01-01
python src/backfill_prices.py --cutoff midnight --series KXHIGHNY KXHIGHCHI --start 2026-01-01
python src/evaluate_models.py   # writes outputs/<cutoff>/metrics.json and figures/
```

The [model results notebook](notebooks/model_results.ipynb) reads metrics and
figures from the locally generated `outputs/` directory. Running the notebook
starts model evaluation if either cutoff’s `metrics.json` is missing or if you
set `RERUN = True`.

## Extending collection

Add provider adapters under [`src/weather_pipeline/providers/`](src/weather_pipeline/providers/),
register them in `configured_providers`, and test normalization and reporting-window
coverage. Preserve source attribution, confirm archival rights, and keep API keys
out of committed files and logs.

# Forecast Accuracy Dashboard

Collect weather forecasts for the stations used by Kalshi's daily temperature
markets, then build a history for comparing forecast accuracy. The collection
pipeline and live verification reports are implemented. The dashboard is planned.

The project saves forecast highs/lows, NOAA observations, and Kalshi contract
metadata. It does not place trades or collect market prices.

## Automatic collection

Two GitHub Actions workflows share the same [station registry](config/stations.csv).

| Workflow | Schedule (UTC) | What it collects |
| --- | --- | --- |
| [Collect daily weather data](.github/workflows/collect-weather.yml) | Daily at 12:17 | Tomorrow's forecasts, outcomes for saved forecast targets, and verification reports |
| [Collect Kalshi opening forecasts](.github/workflows/collect-market-weather.yml) | Hourly at :07, plus 13:57 and 14:57 | Contract metadata and the first available forecast after each market opens |

The extra market runs poll for up to five minutes. Opening times come from
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

`GOOGLE_MAPS_DEMO_API_KEY` and `WEATHERAPI_API_KEY` are not used by the collectors.
AccuWeather, Ambee, and Meteomatics are not integrated. Provider attribution and
storage notes are in [data/README.md](data/README.md).

Pirate Weather and Visual Crossing collect only fresh forecasts for the configured
stations and comparison windows. They do not request past weather, reanalysis,
historical forecasts, or paid historical add-ons. NOAA requests cover only completed
station-dates with saved forecasts: missing outcomes remain eligible, while complete
outcomes are refreshed for corrections within the last 14 days. Gaps and unrelated
station-dates are not filled. Add historical data only when its issue time, station,
and reporting window make it usable for this project's accuracy evaluation.

Meteosource uses the live [Point endpoint](https://www.meteosource.com/documentation).
The default `free` tier supplies tomorrow’s local daily high and low. Its one-day
hourly horizon is too short for regular market-opening captures, so it is omitted
from that roster. On a paid plan, set the Actions variable `METEOSOURCE_TIER` to
the tier segment of your account’s Point URL. Market collection then requests UTC
hours and requires every hour in the contract window. Set `METEOSOURCE_ARCHIVAL_ALLOWED=true`
only after confirming your plan permits encrypted retention and public aggregate
accuracy reporting. See the [API terms](https://www.meteosource.com/terms-of-service)
and [plan coverage](https://www.meteosource.com/pricing). No historical endpoint is used.

New protected archives use a dedicated, randomly generated `DATA_ENCRYPTION_KEY`.
API keys authenticate requests; they no longer encrypt new files. Meteosource, OpenWeather,
Pirate Weather, and Visual Crossing forecasts and optional raw responses are
encrypted. Public-source observations, market metadata, and the existing historical
training CSVs keep their current formats. Encryption does not grant retention,
redistribution, model-training, or benchmarking rights.

Keep `WEATHERBIT_ARCHIVAL_ALLOWED` and `TOMORROW_ARCHIVAL_ALLOWED` false unless the
applicable agreement permits the intended use. Their existing records are left
for a separate cleanup and are never selected by the encryption migration.

## Archive key setup and migration

Create a key once on a trusted machine:

```shell
python src/create_archive_key.py
```

This creates a gitignored `.env` with owner-only permissions and a random 32-byte
key encoded as URL-safe base64. It never prints the key and refuses to overwrite
an existing file. Copy the value into the **GitHub Actions repository secret**
`DATA_ENCRYPTION_KEY` and keep a secure backup. Do not put it in repository variables,
committed configuration, logs, or chat. The scripts do not automatically source
`.env`; migration, reports, and private exports accept `--key-file .env` locally.

The collection workflows migrate permitted older archives after capture, outside
the timed request path. **Migrate encrypted forecast archives** also runs when its
workflow or migration/encryption code is pushed to `main`, and can be run manually
in Actions. It performs migration only, without weather API calls. GitHub supplies both
the new secret and the original `VISUALCROSSING_API_KEY` needed by legacy files.

For local migration:

```shell
# Read-only plan. Legacy Visual Crossing files need the original API key in the environment.
python src/migrate_archives.py --key-file .env

# Apply after all selected inputs have been read and validated.
python src/migrate_archives.py --key-file .env --apply

# If only the dedicated key is available locally, migrate these two providers first.
python src/migrate_archives.py --key-file .env --providers openweathermap pirate_weather --apply
```

Migration splits selected providers out of shared JSONL files, preserves their
original records and capture times, and encrypts optional raw responses. It verifies
encrypted outputs before removing plaintext originals. Missing/wrong keys, damaged
archives, and conflicting snapshots stop preflight without changing files. An
interrupted write can leave identical duplicate copies; rerunning safely completes
the migration. It never replaces originals with newly fetched forecasts.

Once migrated, reading current archives needs only `DATA_ENCRYPTION_KEY`; teammates
can work with saved data without provider credentials. Legacy `FAD1` Visual Crossing
files still require their original API key. Preserve that key for old Git revisions
and backups. This migration changes the working tree only; it does not remove past
plaintext from Git history, forks, or existing clones.

To rotate the dedicated key, retain the old key securely and run a complete migration
with `--key-file NEW_PRIVATE_FILE --previous-key-file OLD_PRIVATE_FILE --apply`.
Then update the Actions secret to match the migrated archives. Coordinate this with
collection jobs; do not discard old keys while old revisions or backups are needed.

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
Faster setup cannot recover that gap. A reliably scheduled worker is the next step
if near-opening capture is required; GitHub schedules have
[documented delays](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows).

## Run locally

Use Python 3.11 or newer. Collection uses `tzdata` and `cryptography` (for encrypted
provider archives); the larger analysis dependencies in `requirements.txt` are
optional for this stage.

```shell
python -m pip install -r requirements-collection.txt
python -m unittest discover -s tests -v

python src/collect_forecasts.py
python src/collect_observations.py
python src/collect_market_forecasts.py
python src/refresh_settlements.py
python src/report_collection.py
```

Optional provider credentials must be available as environment variables locally.
GitHub Actions secrets are available only within the workflows.

With the archive key available locally, decrypt saved forecasts for analysis:

```shell
python src/export_private_forecasts.py --key-file .env
```

This makes no API calls. It writes JSONL under the gitignored
`data/private/<provider>/` directories, preserving separate `forecasts/` and
`market_forecasts/` datasets. The historical model-training dataset is not
automatically extended with these new live providers. Live verification reads the
encrypted archives directly, so it does not require this export. A missing or wrong
decryption key never overwrites an archive.

```shell
# Save contract metadata without requesting weather forecasts.
python src/collect_market_forecasts.py --discover-only

# Poll near an upcoming opening for up to five minutes.
python src/collect_market_forecasts.py --wait-seconds 300

# Extend corrections only for station-dates with saved forecasts.
python src/collect_observations.py --lookback-days 30

# Analyze the last 30 capture dates offline; no historical API requests.
python src/report_collection.py --lookback-days 30

# Also retain permitted raw responses for new daily snapshots.
python src/collect_forecasts.py --save-raw
python src/collect_observations.py --save-raw
```

## Historical backfill

Live collection began in October 2026, which is too short for model training.
`src/backfill_history.py` downloads 2023-to-date history from free sources:

| Source | Data | Coverage |
| --- | --- | --- |
| Open-Meteo Previous Runs API | GFS, HRRR, ICON, GEM, ECMWF forecasts made ~24h (`day1`) and ~48h (`day2`; not HRRR) ahead | GFS 2023+, others 2024+ |
| Iowa Environmental Mesonet | NWS GFS MOS guidance, 12Z run on the previous day | 2023+ |
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
python -m pip install pandas numpy scikit-learn matplotlib
python src/backfill_prices.py --cutoff open --series KXHIGHNY KXHIGHCHI --start 2026-01-01
python src/backfill_prices.py --cutoff midnight --series KXHIGHNY KXHIGHCHI --start 2026-01-01
python src/evaluate_models.py   # writes outputs/<cutoff>/metrics.json and figures/
```

`outputs/` is generated and not committed; re-run the script to recreate it.
[`notebooks/model_results.ipynb`](notebooks/model_results.ipynb) displays those outputs as
tables and figures without recomputing them.

## Extending collection

Add provider adapters under [`src/weather_pipeline/providers/`](src/weather_pipeline/providers/),
register them in `configured_providers`, and test normalization and reporting-window
coverage. Preserve source attribution, confirm archival rights, and keep API keys
out of committed files and logs.

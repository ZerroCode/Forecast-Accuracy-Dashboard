# Forecast Accuracy Dashboard

Collect weather forecasts for the stations used by Kalshi's daily temperature
markets, then build a history for comparing forecast accuracy. The collection
pipeline is implemented; analysis and the dashboard are planned.

The project saves forecast highs/lows, NOAA observations, and Kalshi contract
metadata. It does not place trades or collect market prices.

## Automatic collection

Two GitHub Actions workflows share the same [station registry](config/stations.csv).

| Workflow | Schedule (UTC) | What it collects |
| --- | --- | --- |
| [Collect daily weather data](.github/workflows/collect-weather.yml) | Daily at 12:17 | Tomorrow's forecasts and the previous 14 days of NOAA observations, including corrections |
| [Collect Kalshi opening forecasts](.github/workflows/collect-market-weather.yml) | Hourly at :07, plus 13:57 and 14:57 | Contract metadata and the first available forecast after each market opens |

The extra market runs poll for up to five minutes. Opening times come from
Kalshi's API; the schedule provides opportunities to check them. GitHub may delay
runs, so every market snapshot records its actual retrieval time and opening delay.

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
| OpenWeather | Three-hour forecasts | Secret: `OPENWEATHERMAP_API_KEY` |
| Pirate Weather | Live hourly forecasts in both workflows | Secret: `PIRATE_WEATHER_API_KEY` |
| Visual Crossing | Live hourly forecasts in both workflows; encrypted storage | Secret: `VISUALCROSSING_API_KEY` |
| Tomorrow.io | Hourly forecasts | Secret: `TOMORROW_API_KEYS`; variable: `TOMORROW_ARCHIVAL_ALLOWED=true` |
| Weatherbit | Daily forecasts, morning workflow only | Secret: `WEATHERBIT_API_KEY`; variable: `WEATHERBIT_ARCHIVAL_ALLOWED=true` |

Add secrets and variables under **Settings > Secrets and variables > Actions**,
using the corresponding **Secrets** and **Variables** tabs. Enable archival
variables only when your provider plan permits the intended storage. Weatherbit's
daily aggregates cannot be shifted to the market reporting window.

`GOOGLE_MAPS_DEMO_API_KEY` and `WEATHERAPI_API_KEY` are not used by the collectors.
AccuWeather, Ambee, and Meteomatics are not integrated. Provider attribution and
storage notes are in [data/README.md](data/README.md).

Pirate Weather and Visual Crossing collect only fresh forecasts for the configured
stations and comparison windows. They do not request past weather, reanalysis,
historical forecasts, or paid historical add-ons. The NOAA observation lookback
remains relevant: it supplies actual temperatures and corrections for scoring the
forecasts already collected. Add historical data only when its issue time, station,
and reporting window make it usable for this project's accuracy evaluation.

Visual Crossing archives are encrypted with `VISUALCROSSING_API_KEY` because this
repository is public. No additional secret or repository variable is required.
**Preserve the original key securely before rotating it:** it is needed to read
files encrypted with that key, even after the API credential is revoked. Keys and
decrypted exports must stay out of Git. Pirate Weather snapshots use the ordinary
JSONL files. Neither provider's credentials are included in saved source URLs.

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
checked in October 2026 named The Weather Company. Kalshi result fields are refreshed
for recently closed contracts; long-delayed settlements need a separate backfill.

Files are stored as date-partitioned JSONL under `data/`. Full API responses are
off by default. See [data/README.md](data/README.md) for file layout, schema notes,
and historical calculation caveats.

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
```

Optional provider credentials must be available as environment variables locally.
GitHub Actions secrets are available only within the workflows.

With `VISUALCROSSING_API_KEY` exported locally, decrypt saved forecasts for analysis:

```shell
python src/export_private_forecasts.py
```

This makes no API calls. It writes JSONL under the gitignored
`data/private/visual_crossing/` directory, preserving separate `forecasts/` and
`market_forecasts/` datasets. The historical model-training dataset is not
automatically extended with these new live providers; compare them once matching
outcomes are available. A missing or wrong decryption key never overwrites an archive.

```shell
# Save contract metadata without requesting weather forecasts.
python src/collect_market_forecasts.py --discover-only

# Poll near an upcoming opening for up to five minutes.
python src/collect_market_forecasts.py --wait-seconds 300

# Extend the NOAA observation correction/backfill window.
python src/collect_observations.py --lookback-days 30

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
| `evaluation.py` | Baselines (each source, averages, persistence, climatology) and the error table |
| `markets.py` | Bracket probabilities from forecasts; scoring against Kalshi prices, paper trading, market/model blend |
| `plots.py` | Report figures |

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

## Extending collection

Add provider adapters under [`src/weather_pipeline/providers/`](src/weather_pipeline/providers/),
register them in `configured_providers`, and test normalization and reporting-window
coverage. Preserve source attribution, confirm archival rights, and keep API keys
out of committed files and logs.

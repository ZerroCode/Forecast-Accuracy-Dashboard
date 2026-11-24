# Forecast collection

## Automatic collection

Two GitHub Actions workflows share the same [station registry](../config/stations.csv).

| Workflow | Schedule (UTC) | What it collects |
| --- | --- | --- |
| [Collect daily weather data](../.github/workflows/collect-weather.yml) | Daily at 12:17 | Tomorrow's forecasts, outcomes for saved forecast targets, and verification reports |
| [Collect Kalshi opening forecasts](../.github/workflows/collect-market-weather.yml) | Hourly at :07, plus 13:57 and 14:57 | Contract metadata and the first available forecast after each market opens |

The extra market runs poll for at least a five-minute window, and scheduled runs
that start near 10 AM Eastern use the [opening pilot](#market-opening-pilot). Opening times come from
Kalshi's API; the schedule provides opportunities to check them. GitHub may delay
runs, so every snapshot records its actual response arrival time. Each collection
also saves an expected provider/station list and request timings, even if a provider
fails. Tests run in [separate CI](../.github/workflows/test.yml), outside the timed
collection path. Both workflows regenerate health and accuracy reports after capture.

### Enable the workflows

1. Merge the collection code into `main`.
2. Under **Settings > Actions > General > Workflow permissions**, allow
   **Read and write permissions** so the workflows can commit collected data.
3. In **Actions**, check the first scheduled run of each workflow on `main`.
4. Enable failure notifications. Subsequent runs are scheduled automatically.

Leave **Replace an existing forecast snapshot for the current UTC day** unchecked
for normal runs. Existing snapshots are skipped; missing ones are collected.
Checking it replaces daily forecasts with newer predictions. Market-opening
snapshots are immutable and have no replacement option.

Successful records are saved even when another provider fails, and the workflow
reports the failure. If a push is blocked, check repository permissions and branch
rules. The market workflow schedules 26 runs per day; account for Actions minutes
when using a private repository.

### Market opening pilot

A worker that starts between 9:53 AM and 10:10 AM New York time keeps polling the
validated Kalshi markets through 10:10. Daylight saving changes are handled by
`America/New_York`. Each event’s API opening time, active status and actual response
arrival still determine eligibility. Outside that window a pilot dispatch runs a
single recovery pass. Regular scheduled runs also use the pilot window when they
arrive in time. The two special cron runs retain their five-minute minimum.

An optional always-on host can dispatch the pilot at **9:55 AM America/New_York** each day.
Use this command for its timer.

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

See [market opening coverage](reports-and-scoring.md#market-opening-coverage) to check how many station-days qualify.

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
[archive maintenance guide](../data/README.md#archive-key-setup-and-migration).

## Run locally

Run the commands below from the repository root. Install the collection dependencies
using the [offline quick start](../README.md#generate-a-report-offline).
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

## Extending collection

Add provider adapters under [`src/weather_pipeline/providers/`](../src/weather_pipeline/providers/),
register them in `configured_providers`, and test normalization and reporting-window
coverage. Preserve source attribution, confirm archival rights, and keep API keys
out of committed files and logs.

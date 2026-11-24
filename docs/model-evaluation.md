# Historical data and model evaluation

Run the commands in this guide from the repository root.

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

[`src/forecast_model/`](../src/forecast_model/) combines the six forecasts with machine
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

The [model results notebook](../notebooks/model_results.ipynb) reads metrics and
figures from the locally generated `outputs/` directory. Running the notebook
starts model evaluation if either cutoff’s `metrics.json` is missing or if you
set `RERUN = True`.

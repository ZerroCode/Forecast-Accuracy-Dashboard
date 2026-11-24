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

## Generate a report offline

From the repository root, use Python 3.11 or newer and install the collection
dependencies once in your Python environment. Then build the report from saved files.

```shell
python -m pip install -r requirements-collection.txt
python src/report_collection.py
```

Open `reports/live/summary.md` for the summary or `reports/live/accuracy.json` for
scores. The report command makes no network requests. Without the archive key it
uses the public forecasts and lists the excluded providers. If you have the existing
key in a local `.env`, pass `--key-file .env` to include protected forecasts.

## Documentation

| Guide | Use it to |
| --- | --- |
| [Reports and scoring](docs/reports-and-scoring.md) | Read the newest comparison, understand which station-days qualify, and interpret pending or partial scores. |
| [Forecast collection](docs/collection.md) | Configure scheduled workflows, provider credentials and retention settings, or run the collectors locally. |
| [Historical data and model evaluation](docs/model-evaluation.md) | Build the historical dataset, evaluate forecasts at each prediction cutoff, and compare results with market prices. |
| [Data and archive maintenance](data/README.md) | Look up file formats and attribution, migrate encrypted archives, or rotate the archive key. |

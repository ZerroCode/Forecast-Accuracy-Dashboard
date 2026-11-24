# Live forecast collection

As of 2026-11-24T10:52:13Z — complete analysis.

Expected captures: 3600. Ranking: available.

| Measure | Status | Count |
| --- | --- | ---: |
| Collection | missed_before_measurement_start | 232 |
| Collection | missing | 13 |
| Collection | request_failed | 2 |
| Collection | saved | 3353 |
| Timing | daily_before_schedule | 18 |
| Timing | daily_late | 1269 |
| Timing | market_late | 1996 |
| Timing | market_near_open | 64 |
| Outcome | awaiting_outcome | 160 |
| Outcome | measurement_pending | 160 |
| Outcome | ready | 2440 |

## Market openings

- High: 0 of 232 discovered station-days qualified.
- Low: 0 of 232 discovered station-days qualified.

Dates with a verified high and low at the same station: 0 (milestone: 5).

## Provider accuracy across stations

Lower mean absolute error is better. Positive bias means the forecast was too warm.

### Late daily forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 46 shared station-days and 6 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.61 | -0.96 |
| Open-Meteo | 1.77 | -1.02 |
| Visual Crossing | 2.13 | -1.86 |
| Pirate Weather | 2.31 | -1.87 |
| OpenWeather | 2.35 | -1.14 |

### Late daily forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 46 shared station-days and 6 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.83 | +0.22 |
| Pirate Weather | 1.88 | +0.00 |
| Visual Crossing | 2.22 | +0.32 |
| OpenWeather | 2.72 | -0.70 |
| Open-Meteo | 3.42 | -2.89 |

### Late market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 77 shared station-days and 10 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.77 | -1.01 |
| OpenWeather | 2.29 | -0.97 |
| Pirate Weather | 2.30 | -1.92 |
| Visual Crossing | 2.40 | -2.26 |
| Open-Meteo | 2.48 | -2.09 |

### Late market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 77 shared station-days and 10 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.62 | +0.27 |
| Pirate Weather | 1.81 | +0.33 |
| Visual Crossing | 2.09 | +0.47 |
| OpenWeather | 2.80 | -0.50 |
| Open-Meteo | 2.95 | -2.57 |

### Near-opening market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

### Near-opening market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.
Scores remain unpublished until 5 common target dates are available.
Individual predictions, outcomes and errors are not included in these reports.

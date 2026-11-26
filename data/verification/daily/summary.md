# Live forecast collection

As of 2026-11-26T21:42:08Z — complete analysis.

Expected captures: 3728. Ranking: available.

| Measure | Status | Count |
| --- | --- | ---: |
| Collection | missed_before_measurement_start | 232 |
| Collection | missing | 13 |
| Collection | request_failed | 2 |
| Collection | saved | 3481 |
| Timing | daily_late | 1309 |
| Timing | market_late | 2108 |
| Timing | market_near_open | 64 |
| Outcome | awaiting_outcome | 10 |
| Outcome | measurement_pending | 320 |
| Outcome | ready | 2782 |

## Market openings

- High: 0 of 240 discovered station-days qualified.
- Low: 0 of 240 discovered station-days qualified.

Dates with a verified high and low at the same station: 0 (milestone: 5).

## Provider accuracy across stations

Lower mean absolute error is better. Positive bias means the forecast was too warm.

### Late daily forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 70 shared station-days and 9 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.81 | -0.79 |
| Visual Crossing | 2.14 | -1.88 |
| Open-Meteo | 2.18 | -1.52 |
| OpenWeather | 2.26 | -0.75 |
| Pirate Weather | 2.28 | -1.63 |

### Late daily forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 69 shared station-days and 9 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.67 | +0.30 |
| Pirate Weather | 1.72 | +0.13 |
| Visual Crossing | 2.05 | +0.34 |
| OpenWeather | 2.42 | -0.29 |
| Open-Meteo | 3.36 | -2.80 |

### Late market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 99 shared station-days and 13 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.87 | -0.88 |
| OpenWeather | 2.23 | -0.82 |
| Pirate Weather | 2.28 | -1.70 |
| Visual Crossing | 2.31 | -2.13 |
| Open-Meteo | 2.52 | -2.10 |

### Late market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 98 shared station-days and 13 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.55 | +0.27 |
| Pirate Weather | 1.68 | +0.37 |
| Visual Crossing | 1.98 | +0.48 |
| OpenWeather | 2.57 | -0.29 |
| Open-Meteo | 2.90 | -2.45 |

### Near-opening market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

### Near-opening market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.
Scores remain unpublished until 5 common target dates are available.
Individual predictions, outcomes and errors are not included in these reports.

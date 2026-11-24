# Live forecast collection

As of 2026-11-24T00:47:31Z — complete analysis.

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
| Outcome | measurement_pending | 320 |
| Outcome | ready | 2440 |

## Market openings

- High: 0 of 232 discovered station-days qualified.
- Low: 0 of 232 discovered station-days qualified.

Dates with a verified high and low at the same station: 0 (milestone: 5).

## Provider accuracy across stations

Lower mean absolute error is better. Positive bias means the forecast was too warm.

### Late daily forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 41 shared station-days and 6 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.71 | -0.98 |
| Open-Meteo | 1.82 | -1.00 |
| Visual Crossing | 2.19 | -1.89 |
| Pirate Weather | 2.40 | -1.92 |
| OpenWeather | 2.49 | -1.32 |

### Late daily forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 41 shared station-days and 6 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.73 | +0.12 |
| Pirate Weather | 1.84 | -0.14 |
| Visual Crossing | 2.25 | +0.17 |
| OpenWeather | 2.48 | -1.04 |
| Open-Meteo | 3.50 | -2.91 |

### Late market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 72 shared station-days and 10 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.86 | -1.11 |
| Pirate Weather | 2.35 | -1.95 |
| OpenWeather | 2.36 | -1.05 |
| Visual Crossing | 2.46 | -2.31 |
| Open-Meteo | 2.57 | -2.16 |

### Late market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 72 shared station-days and 10 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.57 | +0.24 |
| Pirate Weather | 1.78 | +0.27 |
| Visual Crossing | 2.09 | +0.39 |
| OpenWeather | 2.66 | -0.68 |
| Open-Meteo | 3.02 | -2.63 |

### Near-opening market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

### Near-opening market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.
Scores remain unpublished until 5 common target dates are available.
Individual predictions, outcomes and errors are not included in these reports.

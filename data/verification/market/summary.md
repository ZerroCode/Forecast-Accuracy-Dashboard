# Live forecast collection

As of 2026-11-25T22:56:38Z — complete analysis.

Expected captures: 3712. Ranking: available.

| Measure | Status | Count |
| --- | --- | ---: |
| Collection | missed_before_measurement_start | 232 |
| Collection | missing | 13 |
| Collection | request_failed | 2 |
| Collection | saved | 3465 |
| Timing | daily_late | 1309 |
| Timing | market_late | 2092 |
| Timing | market_near_open | 64 |
| Outcome | measurement_pending | 320 |
| Outcome | ready | 2696 |

## Market openings

- High: 0 of 240 discovered station-days qualified.
- Low: 0 of 240 discovered station-days qualified.

Dates with a verified high and low at the same station: 0 (milestone: 5).

## Provider accuracy across stations

Lower mean absolute error is better. Positive bias means the forecast was too warm.

### Late daily forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 62 shared station-days and 8 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.79 | -0.95 |
| Visual Crossing | 2.19 | -1.97 |
| Open-Meteo | 2.22 | -1.49 |
| Pirate Weather | 2.28 | -1.76 |
| OpenWeather | 2.28 | -0.98 |

### Late daily forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 62 shared station-days and 8 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.77 | +0.29 |
| Pirate Weather | 1.79 | +0.06 |
| Visual Crossing | 2.19 | +0.32 |
| OpenWeather | 2.51 | -0.42 |
| Open-Meteo | 3.55 | -2.97 |

### Late market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 91 shared station-days and 12 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.86 | -1.00 |
| OpenWeather | 2.25 | -0.99 |
| Pirate Weather | 2.28 | -1.80 |
| Visual Crossing | 2.36 | -2.21 |
| Open-Meteo | 2.58 | -2.14 |

### Late market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 91 shared station-days and 12 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.62 | +0.25 |
| Pirate Weather | 1.73 | +0.35 |
| Visual Crossing | 2.08 | +0.48 |
| OpenWeather | 2.64 | -0.38 |
| Open-Meteo | 2.99 | -2.54 |

### Near-opening market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

### Near-opening market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.
Scores remain unpublished until 5 common target dates are available.
Individual predictions, outcomes and errors are not included in these reports.

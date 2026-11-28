# Live forecast collection

As of 2026-11-28T03:52:18Z — complete analysis.

Expected captures: 3640. Ranking: available.

| Measure | Status | Count |
| --- | --- | ---: |
| Collection | missed_before_measurement_start | 232 |
| Collection | missing | 13 |
| Collection | request_failed | 2 |
| Collection | saved | 3393 |
| Timing | daily_late | 1269 |
| Timing | market_late | 2060 |
| Timing | market_near_open | 64 |
| Outcome | awaiting_outcome | 10 |
| Outcome | measurement_pending | 320 |
| Outcome | ready | 2814 |

## Market openings

- High: 0 of 232 discovered station-days qualified.
- Low: 0 of 232 discovered station-days qualified.

Dates with a verified high and low at the same station: 0 (milestone: 5).

## Provider accuracy across stations

Lower mean absolute error is better. Positive bias means the forecast was too warm.

### Late daily forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 78 shared station-days and 10 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.81 | -0.65 |
| Visual Crossing | 2.07 | -1.82 |
| Open-Meteo | 2.24 | -1.47 |
| Pirate Weather | 2.26 | -1.48 |
| OpenWeather | 2.29 | -0.67 |

### Late daily forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 77 shared station-days and 10 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.62 | +0.35 |
| Pirate Weather | 1.70 | +0.26 |
| Visual Crossing | 1.97 | +0.43 |
| OpenWeather | 2.36 | -0.13 |
| Open-Meteo | 3.21 | -2.66 |

### Late market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 105 shared station-days and 14 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.83 | -0.82 |
| OpenWeather | 2.25 | -0.79 |
| Visual Crossing | 2.28 | -2.09 |
| Pirate Weather | 2.28 | -1.67 |
| Open-Meteo | 2.53 | -2.08 |

### Late market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 104 shared station-days and 14 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.55 | +0.32 |
| Pirate Weather | 1.64 | +0.40 |
| Visual Crossing | 1.97 | +0.55 |
| OpenWeather | 2.54 | -0.16 |
| Open-Meteo | 2.84 | -2.35 |

### Near-opening market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

### Near-opening market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.
Scores remain unpublished until 5 common target dates are available.
Individual predictions, outcomes and errors are not included in these reports.

# Live forecast collection

As of 2026-11-28T12:54:32Z — complete analysis.

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
| Outcome | awaiting_outcome | 110 |
| Outcome | measurement_pending | 160 |
| Outcome | ready | 2874 |

## Market openings

- High: 0 of 232 discovered station-days qualified.
- Low: 0 of 232 discovered station-days qualified.

Dates with a verified high and low at the same station: 0 (milestone: 5).

## Provider accuracy across stations

Lower mean absolute error is better. Positive bias means the forecast was too warm.

### Late daily forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 81 shared station-days and 11 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.74 | -0.63 |
| Visual Crossing | 2.08 | -1.84 |
| Pirate Weather | 2.19 | -1.44 |
| Open-Meteo | 2.28 | -1.54 |
| OpenWeather | 2.28 | -0.69 |

### Late daily forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 80 shared station-days and 11 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.62 | +0.40 |
| Pirate Weather | 1.70 | +0.32 |
| Visual Crossing | 1.94 | +0.42 |
| OpenWeather | 2.34 | -0.19 |
| Open-Meteo | 3.19 | -2.63 |

### Late market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 108 shared station-days and 15 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.78 | -0.80 |
| OpenWeather | 2.22 | -0.79 |
| Pirate Weather | 2.23 | -1.64 |
| Visual Crossing | 2.28 | -2.10 |
| Open-Meteo | 2.56 | -2.12 |

### Late market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 107 shared station-days and 15 distinct target dates.

| Provider | Mean absolute error (°F) | Signed bias (°F) |
| --- | ---: | ---: |
| NWS | 1.56 | +0.36 |
| Pirate Weather | 1.66 | +0.45 |
| Visual Crossing | 1.94 | +0.55 |
| OpenWeather | 2.52 | -0.16 |
| Open-Meteo | 2.83 | -2.34 |

### Near-opening market forecasts · high temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

### Near-opening market forecasts · low temperatures

Verified against Kalshi settlement from The Weather Company over 0 shared station-days and 0 distinct target dates.

Waiting for 5 common target dates.

Comparisons require identical station-days, outcome sources, capture cohort and arrivals within 10 minutes.
Scores remain unpublished until 5 common target dates are available.
Individual predictions, outcomes and errors are not included in these reports.

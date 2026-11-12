from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import numpy as np
    import pandas as pd
    import sklearn  # noqa: F401
except ImportError:  # The collection workflows install only tzdata.
    pd = None

if pd is not None:
    from forecast_model.data import CUTOFFS, START, TEST_START, VAL_START, split
    from forecast_model.evaluation import score
    from forecast_model.features import build_features

    CUTOFF = CUTOFFS["midnight"]
    from forecast_model.markets import bracket_prob, complete_events, normalized_blend


def synthetic(days: int = 60) -> "pd.DataFrame":
    dates = pd.date_range("2024-01-01", periods=days).strftime("%Y-%m-%d")
    rng = np.random.default_rng(0)
    rows = []
    for station in ("nyc_central_park", "miami_international"):
        obs = 60 + rng.normal(0, 5, days)
        row = {"station_id": station, "date": dates, "obs_high_f": obs.round()}
        for i, source in enumerate(CUTOFF.sources):
            row[f"{source}_high_f"] = obs + i - 2 + rng.normal(0, 1, days)
        rows.append(pd.DataFrame(row))
    return pd.concat(rows, ignore_index=True)


@unittest.skipIf(pd is None, "analysis packages not installed")
class FeatureTests(unittest.TestCase):
    def test_features_never_use_unpublished_observations(self):
        # Predicting Feb 15: neither Feb 15 nor Feb 14 is officially reported yet.
        for changed_day in ("2024-02-15", "2024-02-14"):
            with self.subTest(changed_day=changed_day):
                df = synthetic()
                changed = df.copy()
                day = (changed.station_id == "nyc_central_park") & (changed.date == changed_day)
                changed.loc[day, "obs_high_f"] += 100
                before, features = build_features(df, "high", CUTOFF)
                after, _ = build_features(changed, "high", CUTOFF)
                row = (before.station_id == "nyc_central_park") & (before.date == "2024-02-15")
                pd.testing.assert_series_equal(before.loc[row, features].iloc[0],
                                               after.loc[row, features].iloc[0])

    def test_trailing_bias_matches_hand_calculation(self):
        df, _ = build_features(synthetic(), "high", CUTOFF)
        nyc = df[df.station_id == "nyc_central_park"].reset_index(drop=True)
        errors = nyc["mos_high_f"] - nyc["obs_high_f"]
        # Day 20 may use errors from days 12-18: the last 7 days published two days earlier.
        self.assertAlmostEqual(nyc.loc[20, "mos_bias_7d"], errors[12:19].mean())

    def test_bias_does_not_leak_between_cities(self):
        df, _ = build_features(synthetic(), "high", CUTOFF)
        first_miami = df[df.station_id == "miami_international"].iloc[0]
        self.assertTrue(np.isnan(first_miami["mos_bias_7d"]))
        self.assertTrue(np.isnan(first_miami["persistence"]))


@unittest.skipIf(pd is None, "analysis packages not installed")
class ScoringTests(unittest.TestCase):
    def test_all_methods_are_scored_on_the_same_days(self):
        actual = pd.Series([70.0, 71, 72, 73])
        methods = {"complete": pd.Series([70.0, 70, 70, 70]),
                   "gappy": pd.Series([70.0, None, 72, 73])}
        table, _ = score(methods, actual, pd.Series(["nyc_central_park"] * 4))
        self.assertEqual(set(table.n), {3})  # the day "gappy" missed is dropped for both
        self.assertAlmostEqual(table.set_index("method").loc["complete", "mae"], (0 + 2 + 3) / 3)


@unittest.skipIf(pd is None, "analysis packages not installed")
class SplitTests(unittest.TestCase):
    def test_periods_are_ordered_and_disjoint(self):
        dates = pd.date_range("2023-06-01", "2026-10-28").strftime("%Y-%m-%d")
        train, val, test = split(pd.DataFrame({"date": dates}))
        self.assertEqual(train.date.min(), START)
        self.assertLess(train.date.max(), val.date.min())
        self.assertLess(val.date.max(), test.date.min())
        self.assertEqual((val.date.min(), test.date.min()), (VAL_START, TEST_START))
        self.assertEqual(len(train) + len(val) + len(test), (dates >= START).sum())


@unittest.skipIf(pd is None, "analysis packages not installed")
class MarketTests(unittest.TestCase):
    # A typical Kalshi day: two tails and four 2°F brackets covering every integer.
    BRACKETS = [("less", None, 70), ("between", 70, 71), ("between", 72, 73), ("between", 74, 75),
                ("between", 76, 77), ("greater", 77, None)]

    def test_bracket_probabilities_sum_to_one(self):
        for mu, sigma in ((73.4, 1.7), (65.0, 2.0), (80.2, 0.8)):
            total = sum(bracket_prob(kind, floor, cap, mu, sigma) for kind, floor, cap in self.BRACKETS)
            self.assertAlmostEqual(total, 1.0, places=9)

    def test_bracket_covers_whole_degrees_it_settles_on(self):
        # 72-73 settles yes on 72 or 73, i.e. a true value in [71.5, 73.5).
        p = bracket_prob("between", 72, 73, 72.5, 1.0)
        self.assertAlmostEqual(p, 0.6826894921, places=6)
        self.assertGreater(bracket_prob("greater", 77, None, 80, 1.0), 0.99)
        self.assertLess(bracket_prob("less", None, 70, 80, 1.0), 0.01)

    def test_blend_renormalizes_and_events_need_one_winner(self):
        m = pd.DataFrame({"event_ticker": ["A", "A", "B", "B"], "won": [1, 0, 0, 0],
                          "market_p": [0.6, 0.4, 0.5, 0.5], "model_p": [0.3, 0.3, 0.2, 0.2]})
        blended = normalized_blend(m, "market_p", "model_p", 0.5)
        self.assertAlmostEqual(blended[:2].sum(), 1.0)
        self.assertEqual(list(complete_events(m).event_ticker.unique()), ["A"])


if __name__ == "__main__":
    unittest.main()

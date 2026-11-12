"""Turn temperature forecasts into Kalshi bracket probabilities and score them against prices."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


MIN_SIGMA = 0.8  # floor on per-city uncertainty, °F, so no bracket gets near-certainty


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bracket_prob(strike_type: str, floor: float, cap: float, mu: float, sigma: float) -> float:
    # Settled values are whole degrees; integrate the normal over each bracket's integers.
    if strike_type == "between":
        return phi((cap + 0.5 - mu) / sigma) - phi((floor - 0.5 - mu) / sigma)
    if strike_type == "greater":
        return 1 - phi((floor + 0.5 - mu) / sigma)
    if strike_type == "less":
        return phi((cap - 0.5 - mu) / sigma)
    return float("nan")


def load_priced_markets(history: Path, prices_dir: str) -> pd.DataFrame:
    """Settled brackets that have a price snapshot, with a normalized market probability."""
    frames = []
    for prices_path in sorted((history / prices_dir).glob("*.csv")):
        markets = pd.read_csv(history / "kalshi" / prices_path.name)
        prices = pd.read_csv(prices_path)[["market_ticker", "yes_bid", "yes_ask"]]
        frames.append(markets.merge(prices, on="market_ticker"))
    if not frames:
        return pd.DataFrame()
    m = pd.concat(frames)
    m = m[m.strike_type.isin(["between", "greater", "less"]) & m.result.isin(["yes", "no"])]
    m = m[m.yes_ask.notna() & m.yes_bid.notna() & (m.yes_ask > 0)].copy()
    m["won"] = (m.result == "yes").astype(int)
    m["market_p"] = (m.yes_bid + m.yes_ask) / 2
    # Normalize each event's mid prices so brackets sum to 1, like a probability.
    m["market_p"] = m.market_p / m.groupby("event_ticker").market_p.transform("sum")
    return m


def add_model_probs(m: pd.DataFrame, column: str, mu: pd.Series, sigma: dict[str, float]) -> pd.DataFrame:
    p = [bracket_prob(r.strike_type, r.floor_strike, r.cap_strike, mu_i, max(sigma[r.station_id], MIN_SIGMA))
         for r, mu_i in zip(m.itertuples(), mu)]
    return m.assign(**{column: np.clip(p, 1e-4, 1 - 1e-4)})


def complete_events(m: pd.DataFrame) -> pd.DataFrame:
    # Keep events where exactly one priced bracket won, so scores compare like with like.
    return m[m.groupby("event_ticker").won.transform("sum") == 1]


def scores(m: pd.DataFrame, column: str) -> dict:
    top = m.loc[m.groupby("event_ticker")[column].idxmax()]
    return {"brier": float(np.mean((m[column] - m.won) ** 2)),
            "log_loss": float(-np.mean(np.log(np.clip(m.loc[m.won == 1, column], 1e-4, 1)))),
            "top_bracket_hit_rate": float(top.won.mean())}


def paper_trade(m: pd.DataFrame, column: str, edge: float) -> tuple[dict, pd.DataFrame]:
    """Buy YES at the ask when the model sees more than `edge` extra probability.

    The fee approximates Kalshi's taker fee, ceil(0.07 * p * (1 - p)) cents per
    contract. Order size and slippage are ignored.
    """
    trades = m[m[column] - m.yes_ask > edge].copy()
    fee = np.ceil(7 * trades.yes_ask * (1 - trades.yes_ask)) / 100
    trades["pnl"] = trades.won - trades.yes_ask - fee
    summary = {"trades": int(len(trades)),
               "win_rate": float(trades.won.mean()) if len(trades) else None,
               "avg_profit_per_contract": float(trades.pnl.mean()) if len(trades) else None,
               "total_profit_1_contract_each": float(trades.pnl.sum())}
    return summary, trades


def normalized_blend(m: pd.DataFrame, a: str, b: str, weight_a: float) -> pd.Series:
    p = weight_a * m[a] + (1 - weight_a) * m[b]
    return p / p.groupby(m.event_ticker).transform("sum")


def blend_test(m: pd.DataFrame, model_column: str, holdout_start: str) -> dict:
    """Choose a market/model weight before `holdout_start`; score only after it."""
    tune, hold = m[m.date < holdout_start], m[m.date >= holdout_start]

    def log_loss(frame, p):
        return float(-np.mean(np.log(np.clip(p[frame.won == 1], 1e-4, 1))))

    weights = np.round(np.arange(0, 1.01, 0.1), 1)
    best = float(min(weights, key=lambda w: log_loss(tune, normalized_blend(tune, "market_p", model_column, w))))
    hold = hold.assign(blend_p=normalized_blend(hold, "market_p", model_column, best))
    return {"market_weight": best, "holdout_start": holdout_start,
            "holdout_events": int(hold.event_ticker.nunique()),
            "market": scores(hold, "market_p"), "model": scores(hold, model_column),
            "blend": scores(hold, "blend_p")}

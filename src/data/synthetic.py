"""Generate synthetic 15-min index OHLCV data.

This lets the whole pipeline run end-to-end offline, before you plug in real
broker/exchange data. The generator deliberately produces price action with
ranges, breakouts and pullbacks so the support/resistance logic has something
to chew on. It is NOT a substitute for real data when judging the strategy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# NSE regular session: 09:15 -> 15:30 IST. On a 15-min timeframe that is 25
# candles per day (09:15, 09:30, ... 15:15).
BARS_PER_DAY = 25
SESSION_START = "09:15"


def generate(
    days: int = 60,
    start_price: float = 22000.0,
    seed: int = 42,
    start_date: str = "2024-01-01",
) -> pd.DataFrame:
    """Return a DataFrame indexed by tz-naive IST timestamps with OHLCV columns.

    The model: a slow random-walk trend + intraday mean-reversion around a
    daily "value" level, so the series naturally forms support/resistance.
    """
    rng = np.random.default_rng(seed)

    timestamps: list[pd.Timestamp] = []
    day = pd.Timestamp(start_date)
    made = 0
    # Build only weekday sessions.
    while made < days:
        if day.weekday() < 5:  # Mon-Fri
            session = pd.date_range(
                f"{day.date()} {SESSION_START}", periods=BARS_PER_DAY, freq="15min"
            )
            timestamps.extend(session)
            made += 1
        day += pd.Timedelta(days=1)

    n = len(timestamps)
    # Per-bar log return: small drift + noise, with occasional volatility bursts.
    vol = 0.0012 + 0.0006 * (rng.random(n) < 0.1)  # burst on ~10% of bars
    drift = 0.00002
    rets = rng.normal(drift, vol)

    close = start_price * np.exp(np.cumsum(rets))

    # Build OHLC around the close path with realistic wicks.
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    bar_range = np.abs(rets) * close * rng.uniform(1.5, 3.0, n) + 1.0
    high = np.maximum(open_, close) + bar_range * rng.uniform(0.2, 0.8, n)
    low = np.minimum(open_, close) - bar_range * rng.uniform(0.2, 0.8, n)
    volume = rng.integers(50_000, 250_000, n)

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=pd.DatetimeIndex(timestamps, name="datetime"),
    )
    return df.round(2)


if __name__ == "__main__":  # pragma: no cover
    d = generate()
    print(d.head())
    print(f"\n{len(d)} bars, {d.index[0]} -> {d.index[-1]}")

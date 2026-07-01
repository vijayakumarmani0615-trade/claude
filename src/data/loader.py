"""Load OHLCV data from the configured source into a normalized DataFrame.

Normalized contract (what the rest of the code relies on):
  - index : tz-naive pandas DatetimeIndex, ascending, named "datetime" (IST)
  - columns: open, high, low, close, volume  (lowercase, float)
"""
from __future__ import annotations

import pandas as pd

from . import synthetic

REQUIRED = ["open", "high", "low", "close", "volume"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Find a datetime column if it isn't already the index.
    if not isinstance(df.index, pd.DatetimeIndex):
        for cand in ("datetime", "date", "timestamp", "time"):
            if cand in df.columns:
                df[cand] = pd.to_datetime(df[cand])
                df = df.set_index(cand)
                break
        else:
            raise ValueError(
                "No datetime index or column found. Expected one of: "
                "datetime/date/timestamp/time."
            )

    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df.index.name = "datetime"

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    df = df[REQUIRED].astype(float)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df


def load_csv(path: str) -> pd.DataFrame:
    return _normalize(pd.read_csv(path))


def load_yfinance(symbol: str, period: str, interval: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "yfinance not installed. Run: pip install yfinance"
        ) from e

    raw = yf.download(
        symbol, period=period, interval=interval, progress=False, auto_adjust=False
    )
    if raw.empty:  # pragma: no cover
        raise ValueError(f"yfinance returned no data for {symbol} ({period}/{interval})")
    # yfinance can return a MultiIndex column when multiple tickers are requested.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _normalize(raw)


def load(cfg: dict) -> pd.DataFrame:
    """Dispatch to the configured source and return normalized OHLCV."""
    d = cfg["data"]
    source = d.get("source", "synthetic")

    if source == "synthetic":
        df = synthetic.generate()
    elif source == "csv":
        df = load_csv(d["csv_path"])
    elif source == "yfinance":
        interval = d.get("timeframe", "15m")
        df = load_yfinance(d["symbol"], d.get("yf_period", "60d"), interval)
    else:
        raise ValueError(f"Unknown data.source: {source!r}")

    if df.empty:
        raise ValueError("Loaded dataset is empty.")
    return df

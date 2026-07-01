"""Resample the raw 1-minute Nifty files into a single 15-minute OHLC dataset.

Raw files: data/nifty_YYYY.csv with columns [ , date, open, high, low, close, volume]
where `date` is IST (+05:30) 1-minute candles. We combine the yearly files,
strip the timezone (keeping IST wall-clock), resample to 15-min bars aligned to
the 09:15 session open, and write data/nifty_15m.csv.
"""
from __future__ import annotations

import glob
import os

import pandas as pd

RAW_GLOB = "data/nifty_20*.csv"
OUT = "data/nifty_15m.csv"
# Exclude the stray duplicate export (overlaps nifty_2026.csv).
EXCLUDE = {"data/nifty_202620260618_210529.csv"}

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def main() -> None:
    files = sorted(f for f in glob.glob(RAW_GLOB) if f not in EXCLUDE)
    print(f"Combining {len(files)} yearly files:")
    for f in files:
        print(f"  {f}")

    frames = []
    for f in files:
        d = pd.read_csv(f, usecols=["date", "open", "high", "low", "close", "volume"])
        d["date"] = pd.to_datetime(d["date"], utc=False).dt.tz_localize(None)
        frames.append(d)

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="date").set_index("date").sort_index()
    print(f"\n1-min rows: {len(df):,}  ({df.index[0]} -> {df.index[-1]})")

    # Resample per day so bins never span the overnight gap, aligned to 09:15.
    out = (
        df.resample("15min", origin="start_day", offset="9h15min")
        .agg(AGG)
        .dropna(subset=["open"])
    )
    out.index.name = "datetime"
    # Keep only the regular NSE session (09:15–15:30); drop stray after-hours bars.
    session = (out.index.time >= pd.Timestamp("09:15").time()) & (
        out.index.time <= pd.Timestamp("15:30").time()
    )
    dropped = (~session).sum()
    out = out[session]
    print(f"Dropped {dropped} out-of-session bars")
    out.to_csv(OUT)
    print(f"15-min bars: {len(out):,}")
    print(f"Wrote {OUT}")
    print("\nSample:")
    print(out.head(3).to_string())


if __name__ == "__main__":
    main()

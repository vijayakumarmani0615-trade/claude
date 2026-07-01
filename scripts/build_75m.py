"""Resample the existing 15-min Nifty dataset into 75-min bars.

75 = 5 x 15, and the NSE session (09:15-15:30, 375 min) divides evenly into
five 75-min bars (09:15, 10:30, 11:45, 13:00, 14:15), so resampling the
already-built 15-min OHLC (data/nifty_15m.csv) gives identical results to
resampling the raw 1-min files directly -- OHLC aggregation (first/max/min/
last/sum) is associative across nested bins that align on both ends, which
09:15-aligned 15-min bars do for a 75-min target. Avoids re-reading the much
larger raw yearly files.
"""
from __future__ import annotations

import pandas as pd

SRC = "data/nifty_15m.csv"
OUT = "data/nifty_75m.csv"

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def main() -> None:
    df = pd.read_csv(SRC, parse_dates=["datetime"]).set_index("datetime")
    print(f"15-min rows: {len(df):,}  ({df.index[0]} -> {df.index[-1]})")

    out = (
        df.resample("75min", origin="start_day", offset="9h15min")
        .agg(AGG)
        .dropna(subset=["open"])
    )
    out.index.name = "datetime"
    session = (out.index.time >= pd.Timestamp("09:15").time()) & (
        out.index.time <= pd.Timestamp("15:30").time()
    )
    dropped = (~session).sum()
    out = out[session]
    print(f"Dropped {dropped} out-of-session bars")
    out.to_csv(OUT)
    print(f"75-min bars: {len(out):,}")
    print(f"Wrote {OUT}")
    print("\nSample:")
    print(out.head(6).to_string())


if __name__ == "__main__":
    main()

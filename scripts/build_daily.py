"""Resample intraday Nifty spot into DAILY OHLC bars for EOD backtests.

NSE bhavcopy option data is end-of-day, so pair it with one spot bar per day.
Each daily bar is stamped at the session close (15:15) to line up with the
option rows written by scripts/build_options_chain.py.

Usage:
    python scripts/build_daily.py data/nifty_15m.csv -o data/nifty_daily.csv
    python scripts/build_daily.py data/nifty_2024.csv data/nifty_2025.csv -o data/nifty_daily.csv
"""
from __future__ import annotations

import argparse

import pandas as pd

EOD = pd.Timedelta(hours=15, minutes=15)


def main() -> None:
    p = argparse.ArgumentParser(description="Resample intraday spot -> daily bars")
    p.add_argument("inputs", nargs="+", help="intraday OHLC CSV(s)")
    p.add_argument("-o", "--out", default="data/nifty_daily.csv")
    args = p.parse_args()

    frames = []
    for path in args.inputs:
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        dt = next(c for c in ("datetime", "date", "timestamp", "time") if c in df.columns)
        df[dt] = pd.to_datetime(df[dt])
        frames.append(df.set_index(dt))
    raw = pd.concat(frames).sort_index()
    raw = raw[~raw.index.duplicated(keep="first")]

    daily = raw.resample("1D").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
    ).dropna()
    daily.index = daily.index.normalize() + EOD          # stamp at session close
    daily.index.name = "datetime"

    daily.to_csv(args.out)
    print(f"Wrote {args.out}: {len(daily)} daily bars "
          f"({daily.index[0].date()} -> {daily.index[-1].date()})")


if __name__ == "__main__":
    main()

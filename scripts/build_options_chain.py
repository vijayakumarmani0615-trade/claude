"""Convert NSE F&O bhavcopy files into the long-format option chain the iron fly
backtester expects (data/nifty_options.csv).

NSE publishes a **free, historical, end-of-day** F&O bhavcopy for every trading
day — the realistic way to get real Nifty option prices without a paid feed or
broker login. This script accepts either layout NSE has used:

  * classic  : columns INSTRUMENT, SYMBOL, EXPIRY_DT, STRIKE_PR, OPTION_TYP,
               CLOSE, SETTLE_PR, TIMESTAMP, ...   (file: foDDMMMYYYYbhav.csv)
  * UDiFF     : columns TradDt, TckrSymb, XpryDt, StrkPric, OptnTp, ClsPric,
               SttlmPric, FinInstrmTp, ...        (file: BhavCopy_NSE_FO_..._F_0000.csv)

Input can be any mix of .csv, .csv.zip, or a directory of them.

Usage:
    # one file, a whole folder, or globs — all fine
    python scripts/build_options_chain.py data/bhavcopy/ -o data/nifty_options.csv
    python scripts/build_options_chain.py data/fo*bhav.csv.zip --symbol NIFTY

Output columns (one row per option per day): datetime, expiry, strike,
option_type, close. `datetime` is the trade date at the session close (15:15)
so it lines up with the daily spot bars from scripts/build_daily.py.

Note: bhavcopy is END-OF-DAY. Each option gets ONE price per day (its close /
settlement). Run the backtest at daily resolution (source: csv with daily spot
bars). For intraday fills you need a broker/vendor feed instead — see DATA.md.
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import sys
import zipfile

import pandas as pd

EOD_TIME = " 15:15:00"          # stamp EOD rows at the session close


def _read_any(path: str) -> pd.DataFrame:
    """Read a bhavcopy .csv or .csv.zip into a DataFrame."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as f:
                return pd.read_csv(io.BytesIO(f.read()))
    return pd.read_csv(path)


def _expand(inputs: list[str]) -> list[str]:
    files: list[str] = []
    for item in inputs:
        if os.path.isdir(item):
            for ext in ("*.csv", "*.csv.zip", "*.zip"):
                files += glob.glob(os.path.join(item, "**", ext), recursive=True)
        else:
            files += glob.glob(item)
    return sorted(set(files))


def _normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """Map one bhavcopy frame (either layout) to our long format, NIFTY options."""
    cols = {c.strip().upper(): c for c in df.columns}

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    sym_c = col("SYMBOL", "TCKRSYMB")
    exp_c = col("EXPIRY_DT", "XPRYDT")
    strk_c = col("STRIKE_PR", "STRKPRIC")
    typ_c = col("OPTION_TYP", "OPTNTP")
    close_c = col("CLOSE", "CLSPRIC")
    settle_c = col("SETTLE_PR", "STTLMPRIC")
    date_c = col("TIMESTAMP", "TRADDT", "BIZDT")
    instr_c = col("INSTRUMENT", "FININSTRMTP")

    if not all([sym_c, exp_c, strk_c, typ_c, date_c]):
        return None                                  # not a recognizable bhavcopy

    d = df.copy()
    d[sym_c] = d[sym_c].astype(str).str.strip().str.upper()
    d[typ_c] = d[typ_c].astype(str).str.strip().str.upper()

    mask = (d[sym_c] == symbol) & (d[typ_c].isin(["CE", "PE"]))
    if instr_c is not None:                          # index options only, if flagged
        instr = d[instr_c].astype(str).str.strip().str.upper()
        mask &= instr.isin(["OPTIDX", "IDO"])
    d = d[mask]
    if d.empty:
        return None

    price = d[close_c] if close_c else d[settle_c]
    if close_c and settle_c:                         # prefer close, fall back to settle
        price = d[close_c].where(d[close_c] > 0, d[settle_c])

    out = pd.DataFrame({
        # NSE dates are either DD-MMM-YYYY (classic, month name) or YYYY-MM-DD
        # (UDiFF, ISO) — both unambiguous, so no dayfirst (it would corrupt ISO).
        "datetime": pd.to_datetime(d[date_c].astype(str).str.strip(),
                                   format="mixed").dt.normalize(),
        "expiry": pd.to_datetime(d[exp_c].astype(str).str.strip(),
                                 format="mixed").dt.normalize(),
        "strike": pd.to_numeric(d[strk_c], errors="coerce"),
        "option_type": d[typ_c],
        "close": pd.to_numeric(price, errors="coerce"),
    }).dropna(subset=["strike", "close"])
    out["datetime"] = out["datetime"].astype(str) + EOD_TIME
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="NSE F&O bhavcopy -> iron fly option chain")
    p.add_argument("inputs", nargs="+", help="bhavcopy file(s), glob(s), or folder")
    p.add_argument("-o", "--out", default="data/nifty_options.csv")
    p.add_argument("--symbol", default="NIFTY")
    args = p.parse_args()

    files = _expand(args.inputs)
    if not files:
        sys.exit(f"No input files matched: {args.inputs}")

    frames, used, skipped = [], 0, 0
    for f in files:
        try:
            norm = _normalize(_read_any(f), args.symbol.upper())
        except Exception as e:                       # noqa: BLE001 - report and continue
            print(f"  ! {os.path.basename(f)}: {e}")
            skipped += 1
            continue
        if norm is None or norm.empty:
            skipped += 1
            continue
        frames.append(norm)
        used += 1

    if not frames:
        sys.exit("No usable NIFTY option rows found in the inputs.")

    chain = pd.concat(frames, ignore_index=True)
    chain = chain.drop_duplicates(subset=["datetime", "expiry", "strike", "option_type"])
    chain = chain.sort_values(["datetime", "expiry", "strike", "option_type"])

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    chain.to_csv(args.out, index=False)

    print(f"Files: {used} used, {skipped} skipped")
    print(f"Rows : {len(chain):,}")
    print(f"Dates: {chain['datetime'].min()[:10]} -> {chain['datetime'].max()[:10]}")
    print(f"Expiries: {chain['expiry'].nunique()}   Strikes: {chain['strike'].nunique()}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

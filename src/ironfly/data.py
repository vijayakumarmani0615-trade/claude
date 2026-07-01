"""Data layer for the iron fly backtester.

Two inputs:
  * spot bars   - 15-min Nifty OHLCV, for ATM selection and zone-break detection
                  (reuses the same CSV format as the S/R backtester).
  * option chain- long-format per-strike option prices.

Both can be produced synthetically (Black-Scholes) so the pipeline runs and
tests pass offline. Real backtests load them from CSV.

Option-chain CSV contract (columns case-insensitive; extra columns ignored):

    datetime, expiry, strike, option_type, close
    2024-01-05 09:15:00, 2024-01-11, 22000, CE, 145.5
    2024-01-05 09:15:00, 2024-01-11, 22000, PE, 138.0
    ...

  - datetime      : bar timestamp (any parseable format). Aliases: date/timestamp.
  - expiry        : the option's expiry date. Aliases: expiry_date/expiry_dt.
  - strike        : numeric strike.
  - option_type   : CE/PE (also accepts CALL/PUT, C/P). Aliases: type/right/cp.
  - close         : option price at that bar. Aliases: price/ltp/settle.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import pricing

_TYPE_MAP = {
    "CE": "CE", "C": "CE", "CALL": "CE",
    "PE": "PE", "P": "PE", "PUT": "PE",
}


# --------------------------------------------------------------------------- #
# Option chain                                                                #
# --------------------------------------------------------------------------- #
@dataclass
class OptionChain:
    """Fast lookup over per-(expiry, strike, type) option price series."""

    series: dict            # (expiry, strike, opt_type) -> pd.Series(datetime->price)
    expiries: list          # sorted unique expiry Timestamps
    strikes: dict           # expiry -> sorted np.ndarray of available strikes

    def has_expiry(self, expiry) -> bool:
        return pd.Timestamp(expiry).normalize() in self.strikes

    def nearest_strike(self, expiry, target: float) -> float:
        arr = self.strikes[pd.Timestamp(expiry).normalize()]
        return float(arr[int(np.abs(arr - target).argmin())])

    def price(self, expiry, strike: float, opt_type: str, t) -> float | None:
        """Last known option price at/before time `t`. None if the leg is unknown."""
        key = (pd.Timestamp(expiry).normalize(), float(strike), opt_type)
        s = self.series.get(key)
        if s is None:
            return None
        val = s.asof(pd.Timestamp(t))          # last price at or before t
        if pd.isna(val):
            return None
        return float(val)


def _build_chain(df: pd.DataFrame) -> OptionChain:
    series: dict = {}
    strikes: dict = {}
    for (exp, strike, otype), g in df.groupby(["expiry", "strike", "option_type"]):
        exp = pd.Timestamp(exp).normalize()
        s = g.set_index("datetime")["close"].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        series[(exp, float(strike), otype)] = s
        strikes.setdefault(exp, set()).add(float(strike))
    strikes = {e: np.array(sorted(v)) for e, v in strikes.items()}
    expiries = sorted(strikes)
    return OptionChain(series=series, expiries=expiries, strikes=strikes)


def load_chain_csv(path: str) -> OptionChain:
    raw = pd.read_csv(path)
    raw.columns = [str(c).strip().lower() for c in raw.columns]

    def pick(*names):
        for n in names:
            if n in raw.columns:
                return n
        raise ValueError(f"Option CSV missing a column for any of: {names}")

    dt_c = pick("datetime", "date", "timestamp", "time")
    exp_c = pick("expiry", "expiry_date", "expiry_dt", "expirydate")
    strk_c = pick("strike", "strike_price", "strikeprice")
    type_c = pick("option_type", "type", "right", "cp", "opt_type", "instrument_type")
    px_c = pick("close", "price", "ltp", "settle", "last")

    df = pd.DataFrame({
        "datetime": pd.to_datetime(raw[dt_c]),
        "expiry": pd.to_datetime(raw[exp_c]),
        "strike": pd.to_numeric(raw[strk_c], errors="coerce"),
        "option_type": raw[type_c].astype(str).str.strip().str.upper().map(_TYPE_MAP),
        "close": pd.to_numeric(raw[px_c], errors="coerce"),
    })
    bad = df["option_type"].isna()
    if bad.any():
        raise ValueError(
            f"{int(bad.sum())} rows have an unrecognized option_type "
            f"(expected CE/PE/CALL/PUT)."
        )
    df = df.dropna(subset=["strike", "close"])
    if df.empty:
        raise ValueError("Option chain is empty after parsing.")
    return _build_chain(df)


# --------------------------------------------------------------------------- #
# Spot bars                                                                    #
# --------------------------------------------------------------------------- #
def load_spot_csv(path: str) -> pd.DataFrame:
    """15-min spot OHLCV -> normalized frame (open/high/low/close, datetime index)."""
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if not isinstance(df.index, pd.DatetimeIndex):
        for cand in ("datetime", "date", "timestamp", "time"):
            if cand in df.columns:
                df[cand] = pd.to_datetime(df[cand])
                df = df.set_index(cand)
                break
        else:
            raise ValueError("Spot CSV needs a datetime/date/timestamp column.")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df.index.name = "datetime"
    need = ["open", "high", "low", "close"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Spot CSV missing columns: {missing}")
    df = df[need].astype(float)
    return df[~df.index.duplicated(keep="first")].sort_index()


# --------------------------------------------------------------------------- #
# Synthetic generator (offline sanity / tests only)                           #
# --------------------------------------------------------------------------- #
def _weekly_cycles(start: pd.Timestamp, weeks: int):
    """Yield (entry_friday, expiry_thursday) for `weeks` consecutive cycles."""
    # Snap start to a Friday.
    d = start
    while d.weekday() != 4:            # 4 = Friday
        d += pd.Timedelta(days=1)
    for _ in range(weeks):
        entry = d
        expiry = entry + pd.Timedelta(days=6)   # Friday -> next Thursday
        yield entry, expiry
        d = entry + pd.Timedelta(days=7)


def _session_bars(day: pd.Timestamp):
    """15-min bar timestamps 09:15..15:15 for a trading day."""
    base = day.normalize()
    return [base + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(minutes=15 * i)
            for i in range(25)]


def generate_synthetic(cfg: dict):
    """Return (spot_df, OptionChain) from a Black-Scholes synthetic world."""
    s = cfg.get("synthetic", {})
    weeks = int(s.get("weeks", 24))
    start = pd.Timestamp(s.get("start", "2024-01-05"))
    spot0 = float(s.get("spot0", 22000))
    annual_vol = float(s.get("annual_vol", 0.14))
    iv = float(s.get("iv", 0.12))
    seed = int(s.get("seed", 7))
    step = int(cfg["strategy"]["strike_step"])

    rng = np.random.default_rng(seed)
    bars_per_year = 252 * 25
    per_bar_vol = annual_vol / np.sqrt(bars_per_year)

    spot_rows = []
    chain_rows = []
    price = spot0

    for entry, expiry in _weekly_cycles(start, weeks):
        # Trading days in this cycle: entry (Fri) through expiry (Thu), weekdays.
        days = [d for d in pd.date_range(entry, expiry, freq="D") if d.weekday() < 5]
        # Strike band wide enough for wings + a few rolls.
        band = int(cfg["strategy"]["wing_width"]) + \
            int(cfg["strategy"].get("roll_step", 300)) * \
            int(cfg["strategy"].get("max_rolls_per_side", 3)) + 300
        expiry_dt = expiry.normalize() + pd.Timedelta(hours=15, minutes=30)

        for day in days:
            for t in _session_bars(day):
                # Evolve spot one bar (GBM), build an OHLC around it.
                price *= float(np.exp(-0.5 * per_bar_vol ** 2 +
                                      per_bar_vol * rng.standard_normal()))
                wig = price * per_bar_vol
                o = price
                c = price * float(np.exp(per_bar_vol * rng.standard_normal() * 0.5))
                hi = max(o, c) + abs(rng.standard_normal()) * wig
                lo = min(o, c) - abs(rng.standard_normal()) * wig
                spot_rows.append((t, o, hi, lo, c))

                tte = max((expiry_dt - t).total_seconds() / (365 * 24 * 3600), 1e-6)
                center = round(price / step) * step
                for k in range(int(center - band), int(center + band) + 1, step):
                    for otype in ("CE", "PE"):
                        px = pricing.bs_price(price, k, tte, iv, otype)
                        chain_rows.append((t, expiry.normalize(), float(k), otype,
                                           round(max(px, 0.05), 2)))

    spot_df = pd.DataFrame(spot_rows, columns=["datetime", "open", "high", "low", "close"])
    spot_df = spot_df.set_index("datetime").sort_index()

    chain_df = pd.DataFrame(chain_rows,
                            columns=["datetime", "expiry", "strike", "option_type", "close"])
    return spot_df, _build_chain(chain_df)


def load(cfg: dict):
    """Dispatch to the configured source -> (spot_df, OptionChain)."""
    src = cfg["data"].get("source", "synthetic")
    if src == "synthetic":
        return generate_synthetic(cfg)
    if src == "csv":
        spot = load_spot_csv(cfg["data"]["spot_csv"])
        chain = load_chain_csv(cfg["data"]["options_csv"])
        return spot, chain
    raise ValueError(f"Unknown data.source: {src!r}")

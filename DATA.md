# Getting real Nifty weekly option data

The backtester needs **real option premiums** — per strike, per expiry, per day.
This environment can't fetch them (NSE and market-data hosts are blocked by the
egress policy, and broker APIs need your credentials), so you download the data
on your own machine and drop it into `data/`. Two realistic sources:

---

## Option A — NSE F&O bhavcopy (free, end-of-day) — recommended to start

NSE publishes a **free daily F&O bhavcopy** with every option contract's OHLC /
settlement price. Historical, no login. It is **end-of-day**: one price per
option per day. That's enough for a first, honest pass at this weekly strategy
(entry, daily zone-break checks, expiry settlement) — just at daily resolution.

**1. Download the bhavcopy files** for the dates you want. Either format works:

- Classic (up to ~mid-2024):
  `https://archives.nseindia.com/content/historical/DERIVATIVES/<YYYY>/<MMM>/fo<DD><MMM><YYYY>bhav.csv.zip`
  e.g. `.../2024/JUN/fo20JUN2024bhav.csv.zip`
- UDiFF (current):
  `https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip`
  e.g. `.../BhavCopy_NSE_FO_0_0_0_20241226_F_0000.csv.zip`

Put all the `.csv` / `.csv.zip` files in one folder, say `data/bhavcopy/`.
(NSE blocks scripted downloads without browser headers/cookies; a browser, or a
maintained helper like the `jugaad-data` / `nsepython` Python packages run
**locally**, is the least painful way to pull a date range.)

**2. Convert them to the chain format** (handles both layouts, filters to NIFTY
index options, keeps close/settlement):

```bash
python scripts/build_options_chain.py data/bhavcopy/ -o data/nifty_options.csv
```

**3. Build matching daily spot bars** from the intraday spot already in `data/`:

```bash
python scripts/build_daily.py data/nifty_15m.csv -o data/nifty_daily.csv
```

**4. Validate coverage, then backtest:**

```bash
python scripts/validate_chain.py --spot data/nifty_daily.csv --options data/nifty_options.csv
python -m src.ironfly_cli --spot data/nifty_daily.csv --options data/nifty_options.csv
```

**Limitation:** EOD means rolls fill at the day's close, not at the moment spot
crossed the zone, and a spike that reverses intraday is invisible. Good enough to
see whether the edge plausibly exists; not the final word on execution.

---

## Option B — broker / vendor intraday (paid, matches the engine best)

For intraday fills (15-min, matching the strategy's real behaviour) you need a
feed with per-strike intraday history:

- **Zerodha Kite** historical API (`kite.historical_data` on option instrument
  tokens), **Fyers**, **Upstox**, **Angel SmartAPI** — need an account + API key
  and (Kite) a historical-data subscription.
- Vendors: **GDFL / GlobalDataFeeds**, **TrueData** — CSV or API, paid.

Export a long CSV and point the backtester straight at it (no converter needed —
the loader accepts these column names, case-insensitive; extras ignored):

```csv
datetime,expiry,strike,option_type,close
2024-06-14 09:15:00,2024-06-20,23500,CE,142.5
2024-06-14 09:15:00,2024-06-20,23500,PE,131.0
```

Aliases accepted: `date/timestamp` for datetime, `expiry_date` for expiry,
`type/right/cp` for option_type, `price/ltp/settle/last` for close. Run with the
intraday 15-min spot (`data/nifty_15m.csv`) instead of the daily bars.

```bash
python -m src.ironfly_cli --spot data/nifty_15m.csv --options data/your_intraday_chain.csv
```

---

## What the converter keeps

From each bhavcopy it keeps rows where the symbol is `NIFTY`, the instrument is
an index option (`OPTIDX` / `IDO`), and the type is `CE`/`PE`. It prefers the
traded `CLOSE`; if that's zero (untraded strike) it falls back to the
settlement price. Duplicate (date, expiry, strike, type) rows are dropped.

Whatever the source, run `scripts/validate_chain.py` first — it reports how many
weekly cycles are actually tradable and flags legs that would settle at
intrinsic because a strike is missing near expiry.

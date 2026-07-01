# Indian Index S/R Reversal — Trading Automation

Automating a **support/resistance rejection** strategy for Indian indices
(Nifty / Bank Nifty) on 15-minute candles. Two setups: **reversal** (bounce off
a level) and **false breakout/breakdown** (trap the failed break).

We are building this **backtest-first, then paper, then live** — no real orders
until the edge is proven on historical data.

> The exact, mechanical definition of the strategy lives in
> **[STRATEGY.md](STRATEGY.md)** — read that and tell me what to adjust.

## Status

- [x] **Stage 1 — Backtesting engine** (this repo). Level detection, signal
      logic, event-driven backtester, metrics, tests. Runs offline on synthetic
      data today; plug in real data next.
- [ ] Stage 2 — Paper trading on live data (broker feed, no real orders)
- [ ] Stage 3 — Live automation (real orders, once validated)

## Quick start

```bash
pip install -r requirements.txt

# Run on built-in synthetic data (works offline, sanity check the pipeline)
python -m src.cli --config config.yaml

# Run on your own 15-min CSV (see format below)
python -m src.cli --csv data/nifty_15m.csv

# Run the tests
python -m pytest tests/ -v
```

Results are written to `results/`:
- `summary.json` — headline performance metrics
- `trades.csv` — every trade with entry/exit/stop/target/pnl/R

## Getting real data

The synthetic generator is only for wiring up the pipeline; a mean-reversion
strategy *should* lose on random data. To judge the strategy you need real
15-minute index candles. Options:

1. **CSV** (recommended to start). Any source that gives 15-min OHLCV. Point
   `--csv` at it. Required columns (case-insensitive):

   ```csv
   datetime,open,high,low,close,volume
   2024-06-03 09:15:00,22500.1,22540.5,22485.0,22530.2,0
   2024-06-03 09:30:00,22530.2,22560.0,22520.0,22548.7,0
   ```

2. **yfinance** (free, quick, but only ~60 days of 15-min history and index
   volume is often 0):

   ```bash
   pip install yfinance
   python -m src.cli --source yfinance --symbol "^NSEI"
   ```

3. **Broker historical API** (best quality; needs credentials). This is what we
   wire in at Stage 2 once you've picked a broker.

## Configuration

All strategy parameters live in `config.yaml` — level-detection method,
break/touch tolerances, stop/target method, risk %, costs, etc. Each field is
commented. Start with defaults, run, then tune against how you actually read
charts.

## Project layout

```
config.yaml              # all tunable parameters
src/
  data/
    loader.py            # normalize CSV / yfinance / synthetic -> OHLCV
    synthetic.py         # offline test data generator
  indicators/
    levels.py            # swing pivots + daily pivot points -> S/R zones
    atr.py               # ATR for volatility-based stops
  strategy/
    sr_reversal.py       # reversal + false-break signal logic
  backtest/
    engine.py            # event-driven, no-lookahead backtester
    metrics.py           # win rate, profit factor, drawdown, expectancy, R
  cli.py                 # entry point + report
tests/                   # pytest suite
```

## Iron Fly (Nifty weekly) — separate strategy

A second, independent strategy lives under `src/ironfly/`: a **market-neutral
iron fly** on Nifty weekly options (sell the ATM straddle, buy 300-pt protective
wings), entered the day after weekly expiry, with the tested side **rolled 300
pts further out** when spot breaks the spread zone. The precise mechanical rules
are in **[STRATEGY_IRONFLY.md](STRATEGY_IRONFLY.md)** — read that and correct
anything that doesn't match how you trade it.

```bash
# Sanity-check the pipeline on a synthetic Black-Scholes world (offline)
python -m src.ironfly_cli --config config_ironfly.yaml

# Judge it on REAL data: 15-min spot bars + a weekly option chain
python -m src.ironfly_cli --spot data/nifty_15m.csv --options data/nifty_options.csv

python -m pytest tests/test_ironfly.py -v
```

Results are written to `results_ironfly/`: `summary.json`, `cycles.csv` (one row
per weekly fly), and `legs.csv` (every leg incl. rolls, with entry/exit/pnl).

**You need real option prices** — the synthetic generator only wires up the
pipeline, it can't tell you whether the edge is real. Full sourcing guide in
**[DATA.md](DATA.md)**. The free path is NSE's end-of-day F&O bhavcopy:

```bash
# 1. drop downloaded bhavcopy files (classic or UDiFF, .csv/.csv.zip) in a folder
python scripts/build_options_chain.py data/bhavcopy/ -o data/nifty_options.csv
# 2. daily spot bars to match the EOD chain
python scripts/build_daily.py data/nifty_15m.csv -o data/nifty_daily.csv
# 3. check coverage, then backtest
python scripts/validate_chain.py --spot data/nifty_daily.csv --options data/nifty_options.csv
python -m src.ironfly_cli --spot data/nifty_daily.csv --options data/nifty_options.csv
```

For intraday fills use a broker/vendor feed (Kite/Fyers/GDFL) instead — the
loader takes a long-format CSV directly (columns case-insensitive, extras
ignored):

```csv
datetime,expiry,strike,option_type,close
2024-06-14 09:15:00,2024-06-20,23500,CE,142.5
2024-06-14 09:15:00,2024-06-20,23500,PE,131.0
```

`option_type` accepts CE/PE (also CALL/PUT, C/P). All iron fly parameters —
wing width, roll trigger/step, roll scope, costs, lot size — live in
`config_ironfly.yaml`.

## Important disclaimer

This is software for **research and education**. Backtested results do not
guarantee future performance. Trading leveraged index instruments carries
substantial risk of loss. Validate thoroughly on paper before risking capital,
and never automate live orders you don't understand.

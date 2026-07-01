# Indian Index Strategy Automation

Automating mechanical trading strategies for Indian indices (Nifty / Bank
Nifty) on 15-minute candles, backtested on the same shared engine.

- **S/R reversal** — bounce off a level (`reversal`) or a failed
  break/breakdown (`false_break`). Spec: **[STRATEGY.md](STRATEGY.md)**.
- **EMA(8) trend pullback** — trending day, first pullback touch of the 8
  EMA. Spec: **[STRATEGY_EMA_PULLBACK.md](STRATEGY_EMA_PULLBACK.md)**.

Read the relevant spec and tell me what to adjust — every number in it maps
to a config file knob.

We are building this **backtest-first, then paper, then live** — no real orders
until the edge is proven on historical data.

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

# Run the EMA(8) pullback strategy instead of S/R reversal
python -m src.cli --config config_ema_pullback.yaml --strategy ema_pullback

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

## Important disclaimer

This is software for **research and education**. Backtested results do not
guarantee future performance. Trading leveraged index instruments carries
substantial risk of loss. Validate thoroughly on paper before risking capital,
and never automate live orders you don't understand.

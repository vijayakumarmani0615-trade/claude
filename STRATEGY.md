# Strategy specification

This is my precise, mechanical interpretation of your idea:

> *"Indices, 15-min, support & resistance reversal and false breakout/breakdown,
> with target and stop-loss."*

Read this and correct anything that doesn't match how you actually trade. Every
number here maps to a knob in `config.yaml`.

## 1. Instrument & timeframe
- Index (e.g. Nifty 50 `^NSEI`, Bank Nifty `^NSEBANK`).
- 15-minute candles, regular session 09:15–15:30 IST.
- Intraday: every position is squared off at 15:15 (`data.square_off`).

## 2. How a "level" is defined (the crucial part)
Your eye picks support/resistance discretionarily. The code approximates it with
two sources (`levels.method: both`):

- **Swing pivots (fractals).** A swing high = a bar whose high is the highest of
  the `swing_left` bars before and `swing_right` bars after it (and a swing low,
  the mirror). A swing needs `swing_right` future bars to *confirm*, so it only
  becomes tradable that many bars later — no cheating with future data.
- **Daily pivot points.** Classic PP / R1 / R2 / S1 / S2 from the *previous*
  day's High/Low/Close. Index intraday traders lean on these, so they're
  included as fixed daily reference levels.

Nearby levels are merged into a **zone** (within `zone_pct`, default 0.15%), and
only levels formed within the last `lookback_bars` bars stay active.

## 3. Entry rules
For the nearest resistance above / support below the current price:

**Reversal (bounce)**
- SHORT: bar's high reaches into the resistance zone but the bar closes back
  below the level (and closes red). Sellers defended it.
- LONG: bar's low reaches into the support zone but the bar closes back above
  the level (and closes green). Buyers defended it.

**False breakout / breakdown (trap)**
- SHORT: bar pokes **above** resistance by `break_buffer_pct` (default 0.10%)
  but closes back **below** the level. Failed breakout.
- LONG: bar pokes **below** support by `break_buffer_pct` but closes back
  **above** the level. Failed breakdown.

A signal is generated on the **close** of the signal bar. The fill happens at
the **next bar's open** by default (`backtest.entry: next_open`) — realistic,
no filling on the very bar that produced the signal.

## 4. Exit rules
- **Stop-loss** (`risk.sl_method`):
  - `structure` (default): just beyond the signal bar's low (long) / high
    (short), plus `sl_buffer_pct`.
  - `atr`: `atr_mult × ATR(atr_period)`.
  - `fixed`: `sl_fixed_points` index points.
- **Target** (`risk.target_method`):
  - `rr` (default): `rr_multiple × risk` (e.g. 1.5R).
  - `fixed`: `target_fixed_points` points.
- **Time exit:** squared off at `square_off` (15:15) if still open.
- If a single bar touches both stop and target, the stop is assumed hit first
  (`backtest.sl_priority`) — conservative.

## 5. Position sizing & risk
- Risk-based: quantity = (`capital × risk_per_trade_pct`) ÷ (entry − stop).
  So each trade risks a fixed fraction of capital regardless of stop distance.
- `max_trades_per_day` caps daily entries (default 3).
- `one_position_at_a_time` prevents overlapping positions (default true).

## 6. Costs modelled
- Slippage `slippage_pct` per side (applied against you on entry and exit).
- Flat `brokerage_per_trade` (round-trip) — set this to your broker's real
  intraday charges for an honest picture.

## Open questions for you (defaults chosen for now)
1. Should the target snap to the **next opposing level** instead of a fixed R
   multiple? (Currently R-multiple.)
2. Any **time-of-day filter** — e.g. skip the first 15 min (09:15 candle) or the
   last hour?
3. Any **trend filter** — only take longs above a moving average, shorts below?
4. Do you want the false-break setup to also require a **volume spike** on the
   poke?

Tell me which of these matter and I'll wire them in.

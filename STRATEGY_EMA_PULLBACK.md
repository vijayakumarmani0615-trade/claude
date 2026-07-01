# Strategy specification — EMA(8) trend pullback

This is my mechanical interpretation of your idea:

> *"Indices, 15-min. Day has to be trending, then take the trade on the first
> visit to the 8 EMA. Capital ₹2,00,000, 1 lot."*

Read this and correct anything that doesn't match how you actually trade.
Every number maps to a knob in `config_ema_pullback.yaml`.

## 1. Instrument & timeframe
- Index (Nifty 50 by default, since the repo's data pipeline already has
  `data/nifty_15m.csv`; point `csv_path` at another index's 15-min data to
  switch — e.g. Bank Nifty).
- 15-minute candles, regular session 09:15–15:30 IST.
- Intraday: every position squared off at 15:15 (`data.square_off`), same as
  the S/R strategy.

## 2. "Day has to be trending" — the trend filter
Computed on the same 15-min chart (no extra data feed), using two EMAs:
`ema_fast` (8) and `ema_slow` (50). Both are computed **continuously across
the whole series**, not reset each morning — this is how EMAs behave on a
chart.

- **Uptrend**: close > ema_slow, ema_fast > ema_slow, AND ema_slow has risen
  over the last `trend_slope_bars` (10) bars.
- **Downtrend**: mirror (close < ema_slow, ema_fast < ema_slow, ema_slow
  falling).
- Anything else (EMAs tangled/flat): no trend that bar, no trade.

Only longs are taken on an uptrend day, only shorts on a downtrend day.

## 3. "First visit to the 8 EMA" — entry rule
For each bar, if the day's trend is up:
- The bar's **low touches into ema_fast** (within `touch_pct`, 0.15%).
- The bar **closes back above** ema_fast **and green** (close > open) —
  confirms buyers defended it, not just a wick through.
- Price must have been meaningfully **away from ema_fast recently**
  (`require_extension`: at least `extension_pct` = 0.15% away at some point
  in the last `extension_lookback_bars` = 6 bars). This is what makes it a
  *pullback* rather than chop sitting on the average — flag if this isn't
  what you meant by "visit."

Downtrend is the mirror (high touches ema_fast, closes back below, red).

A signal fires on the **close** of the signal bar; fill is the **next bar's
open** (`backtest.entry: next_open`), same convention as the S/R strategy.

**Only the first qualifying touch per day is traded** — enforced via
`risk.max_trades_per_day: 1`. If the trend direction flips intraday, the
day's trade is already used up (no second attempt in the new direction).

## 4. Exit rules — you said "will decide later"
Placeholder, reusing the same defaults as the S/R strategy so the backtest
runs end-to-end. **Not validated, please replace:**
- Stop: `structure` — beyond the signal bar's low (long) / high (short) +
  buffer.
- Target: `rr` — 1.5x the stop distance.
- Time exit: squared off at 15:15 if still open.

Natural alternatives for an EMA-pullback strategy, once you decide:
- Stop beyond the ema_slow line instead of the signal bar (wider, trend-
  following).
- Trail the stop under/over ema_fast as the trend continues, instead of a
  fixed target.
- Target the prior swing high/low (reusing `src/indicators/levels.py`).

## 5. Position sizing & risk
- **Fixed size**, not risk-based: `lot_size` (75, confirm current NSE Nifty
  lot size before trusting this) x `lots` (1) per trade, regardless of stop
  distance.
- Capital ₹2,00,000 (`risk.capital`) — used for return/drawdown % reporting,
  not for sizing (since sizing is fixed-lot, not risk-per-trade).
- `max_trades_per_day: 1`, `one_position_at_a_time: true`.

## 6. Costs modelled
Same as the S/R strategy: slippage per side + flat brokerage per round trip.

## Open questions for you (defaults chosen for now)
1. **Exits** — you said you'd decide later. The placeholder above is
   untested for this strategy; tell me your actual stop/target rule (or "use
   whatever backtests best") and I'll wire it in and re-run.
2. Is the **extension-before-pullback filter** what you meant by "visit," or
   should *any* touch of the 8 EMA count, even without a prior extended move?
3. Should a **trend flip mid-day** (e.g. up in the morning, down after lunch)
   allow a second trade in the new direction, or does "1 trade/day" mean
   exactly one shot regardless?
4. Which **index** — confirm Nifty 50, or did you mean Bank Nifty / another
   index? Lot size and data source depend on this.

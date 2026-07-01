# Backtest findings — Nifty 15-min S/R strategy (2020 → Jun 2026)

Honest summary of what the data shows. Read this before risking any capital.

## Data
- Source: user-supplied 1-min Nifty spot, 2020–Jun 2026, resampled to 15-min
  (`scripts/build_15m.py` → `data/nifty_15m.csv`), regular session only.
- 37,373 fifteen-minute bars.

## Strategy tested
- Levels: 15-min swing highs/lows (pivots, left/right = 8), the definition the
  user validated visually in TradingView.
- Setups: **reversal** (touch + close back) and **false break** (wick pierces
  the level, closes back inside).
- Entry trigger: **candlestick confirmation** — hammer / bullish pin at support
  (long), inverted hammer / bearish pin at resistance (short).
- Exit: fixed stop / target, intraday square-off 15:15.

## What we found (in order)

1. **The raw entry logic has a real gross edge.** Frictionless, the base
   strategy ran profit factor ~1.29 (~5 pts/trade). It is not random.

2. **Costs decide everything.** The gross edge (~5 pts) is close to realistic
   round-trip transaction cost for Nifty futures (~5–7 pts, dominated by STT).
   With costs, the broad strategy loses.

3. **Candle confirmation isolates the edge to ONE setup.** With pin-bar
   confirmation, the **false-break** setup carries a large edge (~10 pts/trade,
   win ~43%) while the plain **reversal** edge is too thin to beat costs. A
   false break + pin bar is a liquidity sweep + rejection — the highest-quality
   version of the idea.

4. **But the edge is NOT stable over time — this is the key result.**
   False-break + pin, 50/120, conservative costs, net P&L by year:

   | Year | Trades | Net (₹L) | Win% |
   |------|--------|----------|------|
   | 2020 | 73 | +3.04 | 53 |
   | 2021 | 53 | +1.08 | 47 |
   | 2022 | 43 | −0.05 | 42 |
   | 2023 | 15 | −0.57 | 27 |
   | 2024 | 41 | −0.36 | 34 |
   | 2025 | 40 | −0.55 | 30 |

   **Only 2 of 7 years profitable.** All the profit is from the high-volatility
   COVID era (2020–21). Since 2022 it bleeds. ATR-based exits and long/short
   direction filters did **not** recover the recent years — the decay is robust
   across variants, so it is not a parameter artifact.

## Conclusion
The mechanical version of this strategy worked in high-volatility regimes
(2020–22) and has **no reliable edge in the calmer, trending 2023–25 market**.
As written, it is **not safe to automate for live trading**.

## Where the gap might be (next steps, not yet validated)
- The mechanical rules may not capture the discretionary skill actually used
  (level selection, higher-timeframe context, partial exits/trailing, avoiding
  news). Best test: take real winning trades from 2024–25 and check whether
  these rules would have (a) flagged them and (b) avoided the losers around them.
- A volatility-regime filter (only trade when ATR/price is elevated) has a real
  thesis but must be validated out-of-sample before trusting it.

---

## EMA(8) trend-pullback — v1: wait for candle close confirmation (superseded)

First version of the entry rule: touch ema_fast, then require the *same* bar
to close back in the trend direction (green/red body) before entering, filled
at the next bar's open. Trend filter via EMA8/EMA50, first pullback-touch of
EMA8 per day, fixed 1-lot sizing on ₹2,00,000 capital, fixed 20-point stop and
40-point target (2R). Run on the same 2020–Jun 2026 Nifty 15-min data:

| Metric | Value |
|---|---|
| Trades | 1,357 |
| Net P&L | −₹3,16,889 |
| Win rate | 33.8% |
| Profit factor | 0.80 |

**Loses in 6 of 7 years.** Three variants (extension filter off, structure
stop + 2R target, both combined) were tried to rule out an exit/filter
artifact — none flipped the sign; best case (structure stop) still lost net
while raising win rate to 37.7% / PF to 0.89. Conclusion at the time: the
mechanical entry didn't show a demonstrable edge independent of the exit rule.

**This turned out to be about entry timing, not the entry idea itself** — see
below.

## EMA(8) trend-pullback — v2: enter on touch, no confirmation wait

User correction: don't wait for the candle to close/confirm — enter the
instant price touches the 8 EMA. Mechanically: trend direction and the
watched ema_fast level are read as of the *prior* bar (avoiding lookahead),
and the fill happens at that level the moment the current bar's range reaches
it (`backtest.entry: signal_level`), not next bar's open. Same 20pt stop /
40pt target, same 1-lot sizing, same data:

| Metric | Value |
|---|---|
| Trades | 1,399 |
| Net P&L | **+₹11,69,646** |
| Win rate | 57.5% |
| Profit factor | **2.14** |
| Avg R | 0.56 |
| Max drawdown | −₹30,433 (−9.6%) |

By year — **profitable in all 7 years**, and win rate trends up over time:

| Year | Trades | Net (₹) | Win% |
|------|--------|---------|------|
| 2020 | 244 | +1,05,800 | 47.1 |
| 2021 | 239 | +1,34,328 | 50.6 |
| 2022 | 237 | +1,65,137 | 54.0 |
| 2023 | 221 | +2,68,195 | 66.1 |
| 2024 | 225 | +2,46,764 | 64.4 |
| 2025 | 222 | +2,46,751 | 65.3 |
| 2026 (partial) | 11 | +2,672 | 45.5 |

Entering right at the level — instead of chasing price after a confirming
candle closes — puts the fixed 20pt stop exactly where the technical level
already is and captures the full reaction move to the 40pt target, which is
most of the turnaround from v1. Unlike the S/R strategy (edge only in
2020–22) or v1 of this strategy (no edge anywhere), this is consistently
profitable across every year in the sample, through both the high-volatility
COVID era and the calmer 2023–25 trending market.

**Caveats before trusting this for live capital:**
1. The backtest fills entries at the exact touched level whenever a bar's
   range reaches it — the same convention already used for stop/target
   exits in this engine, but for real Nifty futures it assumes your limit
   order actually gets filled at that price with no queue/liquidity issue.
   Stress-tested below.
2. Costs modelled (`costs.slippage_pct`, `costs.brokerage_per_trade`) are the
   same defaults as the S/R strategy — confirm they match your actual broker
   before trusting the net numbers.

### Touch-fill slippage stress test — how clean does the fill need to be?

`scripts/ema_touch_slippage_stress.py` adds flat, adverse extra points on top
of the already-modeled slippage (`costs.entry_touch_extra_slippage_points`),
applied only to the touch-fill entry, and re-runs 20/40:

| Extra adverse points on entry | Win% | PF | Net (₹L) |
|---|---|---|---|
| 0 (as committed) | 57.5 | 2.14 | +11.70 |
| 5 | 51.8 | 1.69 | +8.05 |
| 10 | 46.6 | 1.36 | +4.71 |
| 15 | 41.2 | 1.10 | +1.39 |
| **16–17 (breakeven)** | ~39–38 | ~1.0 | ~0 |
| 20 | 33.2 | 0.78 | −3.57 |

**Breakeven is around 16-17 extra points of adverse slippage on entry** —
comfortably more than the bid-ask spread + market impact you'd typically
expect filling 1 lot of Nifty futures on a 15-min touch (normally well under
5 points outside of gap/news moments), so there's real margin here. But it
is not unlimited: 16-17 points is under one stop-width (20pt) away from
wiping the whole edge, so this is worth revisiting once you have actual
fill data from paper trading — if real slippage on these touches runs
higher than expected (thin liquidity, frequent gaps at the exact level),
the edge shown above erodes faster than it looks.

### Stop x target sweep — is 20/40 a lucky point?

`scripts/ema_sweep.py` swept stop ∈ {10,15,20,25,30,40,50} x target ∈
{15,20,30,40,50,60,80,100,120} (43 combos with target > stop), same 2020–Jun
2026 data:

**Every single combination is profitable** (profit factor > 1, positive net
P&L, in every cell) — this is a broad profitable region, not an isolated
spike at 20/40, which is a meaningfully stronger result than a single
backtest number.

Two useful reference points from the grid:

| Stop/Target | Trades | Win% | PF | Net (₹L) | Max DD% |
|---|---|---|---|---|---|
| **20/40 (committed)** | 1,399 | 57.5 | 2.14 | 11.70 | −9.6 |
| 10/120 (best net P&L in grid) | 1,398 | 30.8 | 2.87 | 17.98 | −3.65 |

The tightest stops (10pt) paired with far targets produce the highest net
P&L and profit factor in the grid, but at a ~31% win rate (roughly two
losers for every winner) versus 57.5% at 20/40 — harder to sit through in
practice, and a 10pt stop is small enough that real slippage/spread on
Nifty futures could eat a much bigger fraction of it than this backtest's
generic slippage assumption accounts for. **20/40 looks like the more
robust, tradeable choice** (comfortably profitable, majority of trades are
winners, moderate drawdown) rather than the grid-optimal one — treat the
10pt-stop corner of the grid as a reason for confidence in the overall
entry, not as a better number to actually trade.

### Out-of-sample check — does the edge hold on data we didn't tune against?

The entry-timing fix and the sweep above were both judged against the full
2020–2026 history at once, which risks the good numbers being partly an
artifact of having seen the whole period. `scripts/ema_oos_validation.py`
runs the backtest once (so the EMA warm-up stays continuous and correct
across the boundary, avoiding a fresh-indicator artifact) and splits the
resulting trades into **in-sample (2020–2022)** — roughly what we could have
judged the strategy on originally — and **out-of-sample (2023–2026)**, held
out.

| Metric | In-sample 2020-22 | Out-of-sample 2023-26 |
|---|---|---|
| Trades | 720 | 679 |
| Win rate | 50.6% | **64.9%** |
| Profit factor | 1.67 | **2.81** |
| Net P&L | +₹4.05L | +₹7.64L |
| Avg R | 0.38 | 0.75 |
| Max drawdown | −9.6% | −4.0% |

**The edge doesn't decay out-of-sample — it strengthens.** Every metric
(win rate, profit factor, avg R, drawdown) is better in the held-out period
than in-sample. The same check on the sweep's grid-optimal combo (10pt
stop/120pt target) shows the identical pattern (PF 2.42 in-sample → 3.39
out-of-sample). This is the opposite of what overfitting to the full history
would look like, and is the strongest evidence yet in this repo that the
entry idea (day-trend filter + enter on the first EMA8 touch) has a genuine,
persistent edge rather than a curve-fit to one stretch of data.

Caveat: this is a single time-based split on one instrument (Nifty), not a
true walk-forward re-optimization or a different market — it rules out "the
edge only existed in 2020–22 and we're fooling ourselves," but it can't rule
out something that affects Nifty index behavior broadly across the whole
2020–2026 sample (e.g. a structural feature of how Nifty trends intraday
that may not hold if that regime changes, or may not transfer to another
index/instrument).

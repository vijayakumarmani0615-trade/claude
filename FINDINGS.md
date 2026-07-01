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

> **⚠️ SUPERSEDED — a bug inflated every result in this section (and
> everything under it, through the 75-min re-tune).** `touch_pct: 0.0015`
> created a ~35-40pt tolerance band around the EMA8 line at Nifty's price
> level — comparable to a whole bar's average range — so 60% of "touches"
> never actually reached the line at all. See the **"v3: corrected touch
> definition"** section near the end of this file for what happens with a
> literal touch requirement (short version: the edge shown below does not
> survive the fix). Left in place for the historical record of how the bug
> was found and what it looked like before the fix, not as something to
> trust.

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

### Risk management review — is ₹2,00,000 / 1 lot actually safe?

Everything above is about whether the entry+exit has an edge. This is a
different question: given the edge is real, **does it fit inside the stated
capital?** `src/risk/margin.py` adds rough futures-margin math (SPAN +
exposure margin ≈ `margin_pct` of contract value — a stand-in, confirm the
real figure with your broker) and two scripts use it.

**`scripts/margin_check.py`** — required margin for 1 lot over the whole
backtested history, since margin scales with the index price (~12,000 in
2020 → ~26,300 at its peak → ~23,850 today), not a fixed number:

| | Value |
|---|---|
| Min margin needed (2020 low) | ₹68,161 |
| Max margin needed (Nov 2025 high) | ₹236,679 |
| Margin needed **today** | **₹2,14,685** |
| Bars where margin alone > ₹2,00,000 capital | 29.5% (first: Feb 2024) |
| Bars where margin + 20pt stop risk > 70%-buffered threshold | 76.6% (first: Feb 2021) |
| Capital needed to stay safe (30% buffer) for the **entire** history | **₹3,40,256** |

**1 lot does not fit inside ₹2,00,000 today** — margin alone (₹2.15L, rough
estimate) already exceeds the stated capital, before even counting the risk
of a losing trade or leaving any buffer for adverse marks. This has been
true since early 2024 on margin alone, and on a risk-adjusted basis
(margin + stop-loss buffer) since early 2021 — i.e. for most of the backtest
period, the ₹2L/1-lot combination as specified would not have been safe to
actually run, independent of how good the entry/exit turned out to be.

**`scripts/ema_risk_sweep.py`** — re-ran the full stop/target grid annotated
with worst losing streak and capital-at-risk at the worst historical index
price (₹26,298, Nov 2025): **every single combination comes back "NOT
safe"** at that price, because capital-at-risk is driven by margin (which
only depends on price and lot size) plus the stop distance — changing the
stop/target doesn't fix an undersized-capital problem, it only moves the
capital-at-risk figure by a few thousand rupees either way.

For the committed 20/40 combo specifically: worst losing streak in the whole
history was **10 consecutive losses**, totaling **−₹17,085** — useful to know
concretely what a bad patch looks like, separate from the margin issue.

**Bottom line: the entry/exit edge looks real (see the out-of-sample section
above), but the capital sizing (₹2,00,000 for 1 Nifty futures lot) is not
safe as specified, and hasn't been for most of the backtest period.** Before
this goes anywhere near live capital, one of these needs to change:
1. Increase capital to something with real headroom (₹3.5–4L, per the
   margin_check output) if you want to keep trading Nifty futures 1 lot.
2. Trade a smaller-notional instrument instead (e.g. Nifty options with
   defined, much smaller capital requirements) if ₹2L is a hard ceiling.
3. At minimum, confirm the real `margin_pct` with your broker — 12% is a
   rough estimate and the true SPAN + exposure figure moves with volatility.

---

## EMA(8) trend-pullback — same config on 75-min bars

Also fixed a real bug while setting this up: the square-off check compared
each bar's start time against 15:15, which only ever matches on 15-min bars.
75-min session bars start at 09:15/10:30/11:45/13:00/14:15 — none reach
15:15 — so positions would never have been forced flat and could carry
across days. `Backtester._compute_square_off_mask` now also treats the
*last bar of each trading day* as a square-off trigger, which generalizes to
any bar size. This also quietly fixed 4 pre-existing truncated/half-days in
the Nifty data (e.g. 2021-02-24, last bar 10:00) where the old time-only
check would have carried a position into the next day even at 15-min —
net P&L on the 15-min/20/40 backtest shifts by about ₹2,300 because of it
(₹11,69,646 → ₹11,67,332), not because anything about the strategy changed.

`scripts/build_75m.py` resamples the existing 15-min data to 75-min (5 bars
covering the session evenly), and `config_ema_pullback_75m.yaml` runs the
*exact same* strategy/risk parameters — same 20pt stop, 40pt target, same
`trend_slope_bars: 10`, `touch_pct`, etc. — against it:

| Metric | 15-min (committed) | 75-min (same config) |
|---|---|---|
| Trades | 1,399 | 1,021 |
| Win rate | 57.5% | 40.9% |
| Profit factor | 2.14 | **1.06** |
| Net P&L | +₹11.67L | +₹0.68L |
| Max drawdown | −9.6% | **−42.4%** |
| Worst losing streak | 10 | 13 |

By year (75-min): profitable in 2020, 2023, 2024, roughly flat in 2025,
**losing in 2021, 2022, and 2026 (partial)** — much less consistent than the
15-min version's 7-for-7 record. Long side stays profitable (+₹1.34L,
win 44.9%) but short flips net negative (−₹0.66L, win 35.7%).

**This isn't really an apples-to-apples test, and the weak result reflects
that more than it reflects "75-min doesn't work":** every strategy parameter
here is counted in *bars*, not wall-clock time. `trend_slope_bars: 10` spans
~2.5 hours at 15-min but ~2 trading days at 75-min; `touch_pct`/
`extension_pct` are percentages, but a 75-min bar's typical high-low range
is much wider than a 15-min bar's, so the same 0.15% tolerance means a
very different thing at each scale. Most tellingly, the stop-hit rate jumps
to 59% (vs 42% at 15-min) with the *same* 20pt stop — a strong sign the
stop is simply too tight for how far price moves inside a 75-min bar,
not that the underlying pullback idea fails at this timeframe.

### Re-tuned for 75-min — the idea holds, it just needed rescaled parameters

`scripts/ema_75m_retune.py` swept `trend_slope_bars` x `extension_lookback_bars`
(4 wall-clock-equivalent pairs, from the original bar-counts down to ~2 bars)
against a stop/target grid scaled ~2x the 15-min one (75-min bars measured
~2.1x the average high-low range of 15-min bars) — 184 combos with at least
30 trades, on the same 2020–2026 data:

| Config | Trades | Win% | PF | Net (₹L) | Max DD | Worst streak |
|---|---|---|---|---|---|---|
| Same 15-min config, reused (baseline) | 1,021 | 40.9 | 1.06 | +0.68 | −42.4% | 13 |
| **Committed: slope=2, ext=1, 20/120** | 722 | 45.3 | **2.70** | +11.46 | **−11.1%** | 16 |
| Best net/PF: slope=3, ext=2, 20/150 | 825 | 41.3 | 2.45 | +12.00 | −9.0% | 18 |

The stop stayed at 20 points in every strong combo — the entry itself (a
precise EMA8 touch) doesn't need a wider stop even at 75-min. What needed to
change was the trend/extension lookback (fewer bars, matching the same
wall-clock window as the 15-min defaults) and, especially, the target
(120–150pt vs 40pt) — 75-min bars run further before reversing, so a small
target left a lot of the move on the table and dragged in a worse win/loss
mix. With those two things fixed, 75-min lands **back in the same ballpark
as 15-min** (PF 2.70 vs 2.14, net +11.46L vs +11.67L), just with a lower win
rate (45.3% vs 57.5%) since the reward is a bigger multiple of the risk.

By year for the committed 75-min config: profitable in 6 of 7 years — only
2026 (partial, 6 trades) is slightly negative — a similar consistency
pattern to 15-min, though this hasn't had a dedicated out-of-sample split
run against it the way the 15-min config did.

### Out-of-sample check for the 75-min re-tune

`scripts/ema_75m_oos_validation.py` runs the same in-sample (2020-2022) vs
out-of-sample (2023-2026) split used for the 15-min config, for both the
committed 75-min combo and the next-best alternative from the sweep:

| Metric | Committed (20/120) in-sample | out-of-sample | Alt (20/150) in-sample | out-of-sample |
|---|---|---|---|---|
| Win rate | 39.3% | **51.6%** | 36.0% | **46.8%** |
| Profit factor | 2.19 | **3.35** | 2.01 | **2.98** |
| Max drawdown | −11.1% | **−2.9%** | −9.0% | **−4.8%** |

**Same result as 15-min: the edge strengthens out-of-sample rather than
decays, for both candidates.** This rules out the retuned 75-min numbers
being a full-period curve-fit to the specific sweep that produced them —
the held-out 2023-2026 stretch is markedly better on every metric than the
in-sample period the combo was picked from, not just similar. Combined with
the 15-min result, this is now two independent timeframes on the same
instrument showing the same "gets better, not worse, out of sample"
pattern, which is a meaningfully stronger signal than either one alone.

Same caveat as before applies: still one instrument (Nifty), one time-based
split — not a different market or a true walk-forward re-optimization.

---

## EMA(8) trend-pullback — v3: corrected touch definition (the real result)

**A user question about one specific trade (Dec 1, 2025) uncovered a real
bug that invalidates every EMA-pullback result above.** The trade's recorded
entry level (EMA8 ≈ 26,238.79) was 24.76 points below the actual low of the
bar that supposedly "touched" it — the bar never came close to the line.

**Root cause:** `touch_pct: 0.0015` (0.15%) was meant as a small tolerance
for a "close enough" touch. At Nifty's price level (~26,000), 0.15% is a
**~35-40 point band** — comparable to a *whole average 15-min bar's range*
(34.9 points, measured earlier in this file). Checking every trade in the
15-min backtest:

| | Count | % |
|---|---|---|
| Genuine touch (bar actually reached the EMA8 line) | 554 | 39.6% |
| **Near miss (only within the tolerance, never reached the line)** | **845** | **60.4%** |

Average near-miss trade entered 17.9 points away from the real EMA8 line
(worst: 38.5 points away). **Most of the "EMA8 touches" behind every result
in this file, from the entry-timing fix onward, were not real touches.**

### Fix and full re-validation

`touch_pct` now defaults to `0.0` — a bar must literally cross/reach the
ema_fast value, no tolerance zone (see `src/strategy/ema_pullback.py` and
`config_ema_pullback*.yaml`). Added a regression test
(`test_near_miss_does_not_fire_with_zero_touch_tolerance`) that fails
without the fix and passes with it. Re-ran everything against the corrected
logic:

**15-min, committed 20pt stop / 40pt target:**

| Metric | Before fix (invalid) | After fix (real) |
|---|---|---|
| Trades | 1,399 | 1,277 |
| Win rate | 57.5% | **28.9%** |
| Profit factor | 2.14 | **0.62** |
| Net P&L | +₹11.70L | **−₹5.94L** |
| Max drawdown | −9.6% | **−288.8%** (loses more than starting capital) |

**Full 43-combo stop/target sweep, corrected:** every single combination is
now **unprofitable** (PF < 1). Best case in the whole grid: 10pt stop / 100pt
target at PF 0.94 — still a net loss (−₹67,539). There is no stop/target
choice that rescues this entry at 15-min.

**Out-of-sample split, corrected:** loses in both halves, not just overall —
in-sample (2020-22) PF 0.64, out-of-sample (2023-26) PF 0.60. No regime
where the corrected entry shows an edge.

**75-min re-tune, corrected:** re-ran the full 184-combo sweep
(`scripts/ema_75m_retune.py`). Best combo found: `trend_slope_bars=2`,
`extension_lookback_bars=1`, 20pt stop / 250pt target — PF 1.08, win 22.5%,
net only **+₹0.47L** on ₹2L capital, with a **−32.8% max drawdown**. That's
marginal at best and nowhere near the previously reported +₹11.46L/PF 2.70 —
not a robust edge, more like noise sitting just above breakeven at the cost
of a huge drawdown for very little return.

### Bottom line

**The mechanical rule "day trend (EMA8/EMA50) + first genuine touch of the
8 EMA" does not have a demonstrable edge, at either 15-min or 75-min,
independent of stop/target choice.** The earlier "backtest-solid" result
that survived a slippage stress test and two out-of-sample checks was real
in the sense that the code correctly backtested *what it was actually
doing* — but what it was actually doing was trading a much looser "price
got somewhat close to the 8 EMA" signal, not literally the 8 EMA touch you
described. That looser signal happened to have an edge; a literal touch of
the line, checked carefully, does not.

This doesn't necessarily mean the discretionary version of your idea is
wrong — it means this specific mechanical translation (literal EMA8 touch,
day-trend filter, these entry/exit rules) isn't it. Worth considering before
trying more variations:
- Was "touch" ever meant to include a close approach, not just a literal
  cross? If so, a much smaller but nonzero tolerance (a handful of points,
  not a percentage that scales with price) might be closer to intent than
  either extreme tested so far.
- The near-miss trades that drove the old "edge" were entering when price
  was still 15-40 points away from the EMA — i.e., earlier/further from the
  line than a literal touch. That's closer to "anticipating" the pullback
  than reacting to it — worth testing deliberately as its own idea (e.g. a
  fixed-point buffer ahead of the line) rather than as an accidental
  side effect of a mis-scaled percentage.
- Re-adding a candle-confirmation requirement (like the S/R strategy's pin
  bar) on top of a literal touch, rather than "no confirmation," hasn't
  been tested under the corrected touch logic.

### Deliberate small fixed-point tolerance — tested, and it's not a clean fix

Added `touch_buffer_points` (a flat point tolerance, doesn't scale with
price like `touch_pct` did) and swept it from 0 to 40 points at the
committed 20pt/40pt stop/target (`scripts/ema_touch_buffer_sweep.py`):

| Buffer (pts) | Win% | PF | Net (₹L) | Max DD% |
|---|---|---|---|---|
| 0 (literal touch) | 28.9 | 0.62 | −5.94 | −288.8 |
| 5 | 34.6 | 0.82 | −2.76 | −136.1 |
| 10 | 40.7 | **1.07** | +0.99 | −18.7 |
| 15 | 45.5 | 1.31 | +4.01 | −11.3 |
| 20 | 51.2 | 1.64 | +7.61 | −9.7 |
| 25 | 55.9 | 2.00 | +10.71 | −6.2 |
| 30 | 59.5 | 2.31 | +12.89 | −4.9 |
| 40 | 65.2 | 2.96 | +16.54 | −3.4 |

**This is a smooth, monotonic curve, not a threshold effect** — there's no
buffer size where it "switches on." It crosses breakeven around 10 points
and keeps climbing continuously toward the old (buggy) ~35-40pt tolerance's
performance level as the buffer approaches that same magnitude. Checked
out-of-sample at several buffer sizes (10/15/20/25/30) — every one holds up
or improves out-of-sample (e.g. buffer=10: PF 1.03 in-sample → 1.12
out-of-sample; buffer=30: PF 2.16 → 2.48), so this isn't a fluke of a
particular date range at any buffer size.

**Honest read: a genuinely small, deliberate tolerance (single digits to
~10-15 points) does not show a strong edge on its own** — it's marginal to
barely-profitable at best. **The edge only becomes clearly strong once the
buffer grows to ~25-30+ points — close enough to the original bug's ~35-40pt
magnitude that this cannot be confidently called "a different, legitimate
mechanism" versus "the same effect that inflated the original numbers, with
a smaller dial."** There's no clean line between "reasonable slack for
noise" and "recreating the bug" — it's a continuum, and the strong results
live at the same end of that continuum the bug did.

This doesn't mean nothing is there — the effect is real and holds up
out-of-sample at every size tested, meaning *something* about "a pullback
that gets somewhat near (not necessarily touching) a fast EMA in a trending
day" has predictive value on this data. But it's a materially different,
vaguer idea than "enters on a literal touch of the 8 EMA," and picking any
specific buffer value to commit to right now would just be re-choosing how
much of the original bug to keep, dressed up as a parameter. Before trusting
any buffer size:
- Worth checking whether the effect is really about EMA8 specifically, or
  about "any recent shallow pullback in a trending day" regardless of which
  reference line is used — if a plain %-off-recent-high/low filter (no EMA
  at all) shows a similar pattern, the EMA8 isn't doing the work.
- If EMA8 does matter specifically, a principled way to pick the tolerance
  would help (e.g. tied to typical bar range or ATR, not an arbitrary point
  count chosen because it backtested well).

### Control test — is the EMA8 doing any specific work? No.

`scripts/ema_control_no_ema.py` reruns the exact same buffer sweep with one
change: the touched "level" is no longer `ema_fast`, it's **the close price
from 8 bars ago** — a plain lag with zero smoothing and no claim to being a
technical level of any kind. Everything else (EMA8/EMA50 trend filter,
extension filter, 20pt/40pt exits) is identical:

| Buffer (pts) | Real EMA8 (win% / PF / net ₹L) | Meaningless 8-bar-ago close (win% / PF / net ₹L) |
|---|---|---|
| 0 | 28.9 / 0.62 / −5.94 | 23.7 / 0.47 / −7.73 |
| 10 | 40.7 / 1.07 / +0.99 | 33.4 / 0.77 / −3.15 |
| 20 | 51.2 / 1.64 / +7.61 | 42.2 / 1.13 / +1.66 |
| 30 | 59.5 / 2.31 / +12.89 | 52.1 / 1.71 / +7.78 |
| 40 | 65.2 / 2.96 / +16.54 | 59.7 / 2.34 / +12.64 |

**The meaningless control shows the exact same smooth, monotonic climb as
the real EMA8** — crossing into profitability around the same buffer size,
strongly profitable by the same point. The real EMA8 is consistently
somewhat better (roughly 25-30% higher profit factor at every buffer size),
but the shape and behavior of the whole pattern is the same with a number
that has no claim to being a technical level at all.

**Conclusion: the EMA8 is not doing the specific work the strategy
attributes to it.** A meaningless reference point produces almost the same
effect. What's actually driving the results is something generic — "a
shallow retracement near roughly-recent price, during an EMA8/EMA50-
confirmed trending day, with a 20pt stop/40pt target" has some predictive
value on this data — but that is not "the 8 EMA" as a technical level in
any meaningful sense. The EMA's modest edge over the plain lag is most
likely just because it's a smoother, less noisy version of "recent price,"
not anything specific to exponential moving averages.

**Overall verdict on this strategy: "day trend + 8 EMA pullback," as a
specific technical hypothesis, does not hold up.** What's left after all
this investigation (shallow-retracement-in-a-trend, loosely defined) is a
materially different and vaguer idea that would need its own dedicated
specification and validation from scratch — it is not a patch or tuning
issue on the original idea.

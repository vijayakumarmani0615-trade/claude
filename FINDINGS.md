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

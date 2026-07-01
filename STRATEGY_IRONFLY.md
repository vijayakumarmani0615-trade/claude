# Iron Fly strategy specification (Nifty weekly)

My precise, mechanical interpretation of your idea:

> *"Nifty weekly iron fly. Enter the day after weekly expiry. Structure is a
> 300-point spread (ATM straddle + 300-pt protective wings). Once price breaks
> the spread zone, close the tested short leg and re-sell it the same distance
> (300 pts) further out."*

Read this and correct anything that doesn't match how you actually trade it.
Every number below maps to a knob in `config_ironfly.yaml`. This is the contract
the backtester in `src/ironfly/` implements.

## 1. Instrument & cycle
- Underlying: **Nifty 50**, **weekly** options.
- Strikes are on a `strike_step` grid (default **50** points).
- One weekly cycle = the week leading into a Thursday expiry.
- **Entry:** `entry_offset_days` (default **1**) trading days *after* the previous
  weekly expiry — i.e. the day after expiry — at `entry_time` (default 09:20).
  So each Friday-ish we open a fresh iron fly for the *coming* Thursday expiry.
- **Exit:** all remaining legs are squared off on expiry day at `square_off`
  (default 15:15). Held roughly 5 trading days.

## 2. The structure at entry
At entry we read spot and pick the ATM strike:

```
K0 = round(spot / strike_step) * strike_step
```

Then place four legs for the coming expiry (1 leg = `lots × lot_size` qty):

| Leg        | Type | Strike      | We are |
|------------|------|-------------|--------|
| Short call | CE   | K0          | short  |
| Short put  | PE   | K0          | short  |
| Long call  | CE   | K0 + `wing_width` (300) | long |
| Long put   | PE   | K0 − `wing_width` (300) | long |

- The short straddle collects premium (the profit engine — theta).
- The two long wings cap the max loss (this is what makes it an iron *fly*, not
  a naked short straddle). **Max loss is bounded by the wing width minus the net
  credit**, per side.
- **Net credit** = premium(short CE) + premium(short PE) − premium(long CE)
  − premium(long PE).

The **spread zone** is `[K0 − wing_width, K0 + wing_width]`. As long as spot stays
inside it, the position is doing what it should.

## 3. Adjustment — rolling the tested side
This is the active-management rule (`adjust: true`). We watch spot bar by bar.

- **Up-break:** when a bar's spot high reaches `short_CE_strike + roll_trigger`
  (default trigger = `wing_width` = 300, i.e. price hits the upper wing / leaves
  the zone), the **call side is tested**. We:
  1. **Close the tested call vertical** — buy back the short CE and sell the long
     CE at their current option prices (realizes that side's P&L so far).
  2. **Re-establish the call side `roll_step` (default 300) points further out**
     in the breakout direction: new short CE at `old_short_CE + roll_step`, new
     long CE at `new_short_CE + wing_width`. This collects fresh premium above
     the market and keeps a constant-width, still-protected structure.
- **Down-break:** mirror image on the put side, triggered when spot low reaches
  `short_PE_strike − roll_trigger`.

Each side can be rolled up to `max_rolls_per_side` times (default 3); after that
we stop chasing and simply carry the last (still wing-protected) structure to
expiry. The put side and call side roll independently.

> **Why roll the whole vertical, not just the short?** If we bought back only the
> short and left the long wing in place, the next re-sold short would collide
> with the old wing. Rolling the short *and* its wing together keeps the
> protection intact at all times and keeps max loss bounded. If you actually
> intend to roll *only the short* (leaving the wing), tell me and I'll switch the
> `roll_scope` to `short_only`.

## 4. P&L accounting
Every leg is tracked individually from the option chain:
- Short leg P&L = (entry price − exit price) × qty.
- Long leg P&L  = (exit price − entry price) × qty.
- A cycle's P&L is the sum over all legs it ever held (original four plus any
  legs created by rolls, each closed either on a subsequent roll or at expiry).

Legs still open on expiry day are closed at `square_off` using the option's
price in the chain at that timestamp; if that strike is illiquid / missing, we
fall back to **intrinsic value** from spot at expiry.

## 5. Costs modelled (per leg)
- `slippage_pct` applied to each option fill, against us (paid up on buys, taken
  off on sells), on entry, roll, and exit.
- `brokerage_per_leg` flat charge every time a leg is opened or closed.

An iron fly is 4 legs; each roll opens 2 and closes 2. Costs compound with
rolling, so the report tracks legs traded and total cost — rolling too eagerly
can eat the credit.

## 6. Data
Judging this needs **real Nifty weekly option prices** (you chose this over a
model). Supply a long-format CSV — see `config_ironfly.yaml` and the README —
plus 15-min spot bars for ATM selection and zone-break detection. A Black-Scholes
**synthetic** generator is included *only* to wire up and test the pipeline
offline; it cannot tell you whether the edge is real.

## Open questions (defaults chosen for now)
1. `roll_scope`: roll the whole tested vertical (current) or **only the short**?
2. Roll trigger: at the wing (`roll_trigger = 300`, current) or earlier — e.g.
   when the short goes ITM (`roll_trigger = 0`) or at a % of the wing?
3. Should a big net loss on the day (e.g. total premium loss ≥ X% of credit)
   force a full exit, independent of the zone break?
4. Skip entry on weeks with a holiday-shortened cycle or major event day?

Tell me which of these matter and I'll wire them in.

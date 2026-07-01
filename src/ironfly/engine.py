"""Weekly-cycle iron fly backtester.

For each weekly expiry (using the *previous* expiry as the "day after expiry"
reference) we:
  1. enter an ATM iron fly on the entry bar (day after prior expiry, entry_time),
  2. walk the spot bars, rolling the tested side out when spot breaks the zone,
  3. square off every remaining leg on expiry day at square_off.

No lookahead: strikes are chosen from spot known at the entry/roll bar, and legs
are priced from the option chain at that same timestamp.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import pricing
from .strategy import Leg, atm_strike, initial_legs, roll_side


@dataclass
class Cycle:
    entry_time: pd.Timestamp
    expiry: pd.Timestamp
    k0: float
    entry_credit: float          # net premium collected by the original 4 legs
    rolls_ce: int
    rolls_pe: int
    legs: list = field(default_factory=list)
    brokerage: float = 0.0
    pnl: float = 0.0             # net of slippage (in fills) and brokerage

    @property
    def legs_count(self) -> int:
        return len(self.legs)


class IronFlyBacktester:
    def __init__(self, spot: pd.DataFrame, chain, cfg: dict):
        self.spot = spot
        self.chain = chain
        self.cfg = cfg

        s = cfg["strategy"]
        self.step = int(s["strike_step"])
        self.wing = float(s["wing_width"])
        self.entry_time = pd.to_datetime(s["entry_time"]).time()
        self.offset = int(s.get("entry_offset_days", 1))
        self.adjust = bool(s.get("adjust", True))
        self.roll_trigger = float(s.get("roll_trigger", self.wing))
        self.roll_step = float(s.get("roll_step", self.wing))
        self.roll_scope = s.get("roll_scope", "vertical")
        self.max_rolls = int(s.get("max_rolls_per_side", 3))
        self.max_cycle_days = int(s.get("max_cycle_days", 10))

        self.qty = int(cfg["lots"]["lot_size"]) * int(cfg["lots"]["lots"])

        c = cfg["costs"]
        self.slip = float(c["slippage_pct"])
        self.brokerage_per_leg = float(c["brokerage_per_leg"])

        self.square_off = pd.to_datetime(cfg["data"]["square_off"]).time()

        # Precompute bar coordinates for fast windowing.
        self.idx = spot.index
        self.bar_date = self.idx.normalize()
        self.tmin = (self.idx.hour * 60 + self.idx.minute).to_numpy()
        self.highs = spot["high"].to_numpy()
        self.lows = spot["low"].to_numpy()
        self.closes = spot["close"].to_numpy()
        self.spot_days = list(pd.DatetimeIndex(sorted(set(self.bar_date))))

        self.expiry = None  # active cycle expiry (used by fill helpers)
        self.skipped: list[tuple] = []

    # -- fills ---------------------------------------------------------------
    def _open(self, spec, t) -> Leg | None:
        strike = self.chain.nearest_strike(self.expiry, spec.strike)
        px = self.chain.price(self.expiry, strike, spec.opt_type, t)
        if px is None:
            return None
        fill = px * (1 - self.slip) if spec.side == "short" else px * (1 + self.slip)
        return Leg(spec.opt_type, strike, spec.side, self.qty, t, round(fill, 4))

    def _close(self, leg: Leg, t, reason: str, spot_close: float) -> None:
        px = self.chain.price(self.expiry, leg.strike, leg.opt_type, t)
        if px is None:                       # illiquid strike near expiry: settle at intrinsic
            px = pricing.intrinsic(spot_close, leg.strike, leg.opt_type)
        fill = px * (1 + self.slip) if leg.side == "short" else px * (1 - self.slip)
        leg.exit_price = round(fill, 4)
        leg.exit_time = t
        leg.exit_reason = reason

    # -- windowing -----------------------------------------------------------
    def _entry_pos(self, entry_date, expiry_date) -> int | None:
        """First bar on/after entry_date at/after entry_time, before expiry."""
        di = bisect_right(self.spot_days, entry_date) - 1
        emin = self.entry_time.hour * 60 + self.entry_time.minute
        for d in self.spot_days[max(di, 0):]:
            if d >= expiry_date:
                return None
            mask = np.asarray(self.bar_date == d) & (self.tmin >= emin)
            hits = mask.nonzero()[0]
            if len(hits):
                return int(hits[0])
        return None

    def _exit_pos(self, expiry_date) -> int | None:
        """Last bar on expiry day at/before square_off (else last bar that day)."""
        smin = self.square_off.hour * 60 + self.square_off.minute
        day = np.asarray(self.bar_date == expiry_date)
        atbefore = (day & (self.tmin <= smin)).nonzero()[0]
        if len(atbefore):
            return int(atbefore[-1])
        anyday = day.nonzero()[0]
        return int(anyday[-1]) if len(anyday) else None

    # -- main loop -----------------------------------------------------------
    def run(self) -> list[Cycle]:
        cycles: list[Cycle] = []
        expiries = [e for e in self.chain.expiries]

        for i in range(1, len(expiries)):
            prev, expiry = expiries[i - 1], expiries[i]
            # Only trade genuine weekly cycles: skip gaps to far-dated (monthly /
            # quarterly) expiries that appear alongside weeklies in a real chain.
            if (expiry - prev).days > self.max_cycle_days:
                continue
            # "day after expiry" = `offset` trading days after the previous expiry.
            di = bisect_right(self.spot_days, prev)
            target = di + (self.offset - 1)
            if target >= len(self.spot_days):
                continue
            entry_date = self.spot_days[target]
            if entry_date >= expiry:
                continue

            cyc = self._run_cycle(entry_date, expiry)
            if cyc is not None:
                cycles.append(cyc)
        return cycles

    def _run_cycle(self, entry_date, expiry) -> Cycle | None:
        self.expiry = expiry
        if not self.chain.has_expiry(expiry):
            self.skipped.append((entry_date, expiry, "no chain for expiry"))
            return None

        epos = self._entry_pos(entry_date, expiry)
        xpos = self._exit_pos(expiry)
        if epos is None or xpos is None or xpos <= epos:
            self.skipped.append((entry_date, expiry, "no usable entry/exit bar"))
            return None

        t0 = self.idx[epos]
        spot0 = self.closes[epos]
        k0 = atm_strike(spot0, self.step)

        legs: list[Leg] = []
        for spec in initial_legs(k0, self.wing):
            leg = self._open(spec, t0)
            if leg is None:
                self.skipped.append((entry_date, expiry, f"missing price {spec.opt_type}{spec.strike}"))
                return None
            legs.append(leg)

        # Per-side state (short + wing) for rolling.
        state = {
            "CE": {"short": legs[0], "wing": legs[2], "k": legs[0].strike, "rolls": 0},
            "PE": {"short": legs[1], "wing": legs[3], "k": legs[1].strike, "rolls": 0},
        }
        entry_credit = sum((l.entry_price if l.side == "short" else -l.entry_price)
                           for l in legs) * self.qty

        # Walk the week, rolling tested sides.
        if self.adjust:
            for j in range(epos + 1, xpos):
                self._maybe_roll("CE", state, legs, j)
                self._maybe_roll("PE", state, legs, j)

        # Square off everything open at expiry.
        tX = self.idx[xpos]
        spotX = self.closes[xpos]
        for leg in legs:
            if leg.is_open:
                self._close(leg, tX, "expiry", spotX)

        brokerage = 2 * len(legs) * self.brokerage_per_leg   # each leg opened + closed
        pnl = sum(l.pnl() for l in legs) * 1.0 - brokerage
        return Cycle(
            entry_time=t0, expiry=expiry, k0=k0,
            entry_credit=round(entry_credit, 2),
            rolls_ce=state["CE"]["rolls"], rolls_pe=state["PE"]["rolls"],
            legs=legs, brokerage=round(brokerage, 2), pnl=round(pnl, 2),
        )

    def _maybe_roll(self, opt_type, state, legs, j) -> None:
        st = state[opt_type]
        if st["rolls"] >= self.max_rolls:
            return
        if opt_type == "CE":
            breached = self.highs[j] >= st["k"] + self.roll_trigger
        else:
            breached = self.lows[j] <= st["k"] - self.roll_trigger
        if not breached:
            return

        t = self.idx[j]
        spot_c = self.closes[j]
        # Close the tested vertical (or just the short, per scope).
        self._close(st["short"], t, "roll", spot_c)
        if self.roll_scope != "short_only" and st["wing"] is not None and st["wing"].is_open:
            self._close(st["wing"], t, "roll", spot_c)

        long_strike = st["wing"].strike if st["wing"] is not None else st["k"]
        new_specs = roll_side(opt_type, st["k"], long_strike,
                              self.roll_step, self.wing, self.roll_scope)
        new_short = new_wing = None
        for spec in new_specs:
            leg = self._open(spec, t)
            if leg is None:            # can't re-establish: leave the side closed
                return
            legs.append(leg)
            if spec.side == "short":
                new_short = leg
            else:
                new_wing = leg
        st["short"] = new_short
        if new_wing is not None:
            st["wing"] = new_wing
        st["k"] = new_short.strike
        st["rolls"] += 1

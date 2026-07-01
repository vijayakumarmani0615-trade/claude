"""Support/Resistance rejection strategy — signal generation.

For each bar we look at the nearest active support and resistance zone and test
for a rejection. Two setups:

  reversal (bounce)
    LONG : bar dips into a support zone (low touches it) but closes back above
           it -> buyers defended the level.
    SHORT: bar pushes into a resistance zone (high touches it) but closes back
           below it -> sellers defended the level.

  false_break (trap)
    LONG : bar breaks BELOW support by `break_buffer_pct` (stop-run / poke) but
           closes back ABOVE the level -> failed breakdown.
    SHORT: bar breaks ABOVE resistance by `break_buffer_pct` but closes back
           BELOW the level -> failed breakout.

A signal is emitted on the *close* of the signal bar. The backtester decides
the actual fill (default: next bar's open).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..indicators.levels import LevelBook, Zone


@dataclass
class Signal:
    bar_index: int
    side: str            # "long" or "short"
    setup: str           # "reversal" or "false_break"
    level: float         # the S/R price the signal is built on
    signal_close: float
    signal_high: float
    signal_low: float


class SRReversalStrategy:
    def __init__(self, cfg: dict, levels: LevelBook):
        sc = cfg["strategy"]
        self.reversal_on = bool(sc["setups"]["reversal"])
        self.false_break_on = bool(sc["setups"]["false_break"])
        self.break_buffer = float(sc["break_buffer_pct"])
        self.touch_pct = float(cfg["levels"]["touch_pct"])
        self.require_close = bool(sc["require_close_confirm"])
        self.require_wick = bool(sc.get("require_rejection_wick", False))
        self.levels = levels

    def _nearest(self, zones: list[Zone], price: float, side: str) -> Zone | None:
        """Nearest resistance ABOVE price / support BELOW price (with tolerance)."""
        tol = price * self.touch_pct
        if side == "resistance":
            cands = [z for z in zones if z.price >= price - tol]
        else:
            cands = [z for z in zones if z.price <= price + tol]
        if not cands:
            return None
        return min(cands, key=lambda z: abs(z.price - price))

    def evaluate(self, i: int, bar) -> Signal | None:
        """Return a Signal for bar `i`, or None. `bar` is a row-like with OHLC."""
        supports, resistances = self.levels.active(i)
        o, h, l, c = bar.open, bar.high, bar.low, bar.close

        res = self._nearest(resistances, c, "resistance")
        sup = self._nearest(supports, c, "support")

        # ---- SHORT side: rejection at resistance --------------------------------
        if res is not None:
            lvl = res.price
            touch_tol = lvl * self.touch_pct
            break_line = lvl * (1 + self.break_buffer)
            closed_below = c < lvl
            wick_ok = (not self.require_wick) or (h - max(o, c) > 0)

            # false breakout: poked above the level, closed back under.
            if self.false_break_on and h > break_line and closed_below and wick_ok:
                return Signal(i, "short", "false_break", lvl, c, h, l)
            # reversal: high reached the zone (within tolerance), rejected, closed under.
            if (
                self.reversal_on
                and h >= lvl - touch_tol
                and h <= break_line
                and (closed_below or not self.require_close)
                and c < o
                and wick_ok
            ):
                return Signal(i, "short", "reversal", lvl, c, h, l)

        # ---- LONG side: rejection at support ------------------------------------
        if sup is not None:
            lvl = sup.price
            touch_tol = lvl * self.touch_pct
            break_line = lvl * (1 - self.break_buffer)
            closed_above = c > lvl
            wick_ok = (not self.require_wick) or (min(o, c) - l > 0)

            # false breakdown: poked below the level, closed back above.
            if self.false_break_on and l < break_line and closed_above and wick_ok:
                return Signal(i, "long", "false_break", lvl, c, h, l)
            # reversal: low reached the zone, bounced, closed above.
            if (
                self.reversal_on
                and l <= lvl + touch_tol
                and l >= break_line
                and (closed_above or not self.require_close)
                and c > o
                and wick_ok
            ):
                return Signal(i, "long", "reversal", lvl, c, h, l)

        return None

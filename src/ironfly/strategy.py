"""Iron fly structure and rolling logic (pure, no data access).

The engine handles fills and P&L; this module only answers *what* strikes make
up the structure and *how* it changes when a side is rolled. See
STRATEGY_IRONFLY.md for the mechanical spec.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Leg:
    opt_type: str          # "CE" | "PE"
    strike: float
    side: str              # "short" | "long"
    qty: int
    entry_time: object
    entry_price: float
    exit_time: object = None
    exit_price: float = None
    exit_reason: str = ""

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    def pnl(self) -> float:
        """Realized P&L (0 while still open). Short profits as price falls."""
        if self.exit_price is None:
            return 0.0
        sign = 1.0 if self.side == "short" else -1.0
        return sign * (self.entry_price - self.exit_price) * self.qty


@dataclass
class LegSpec:
    """A leg to be opened, before it has a fill price."""
    opt_type: str
    strike: float
    side: str


def atm_strike(spot: float, step: int) -> float:
    """Nearest strike on the grid to spot."""
    return round(spot / step) * step


def initial_legs(k0: float, wing_width: float) -> list[LegSpec]:
    """The four legs of an ATM iron fly around strike k0."""
    return [
        LegSpec("CE", k0, "short"),
        LegSpec("PE", k0, "short"),
        LegSpec("CE", k0 + wing_width, "long"),
        LegSpec("PE", k0 - wing_width, "long"),
    ]


def roll_side(opt_type: str, cur_short: float, cur_long: float,
              roll_step: float, wing_width: float, scope: str) -> list[LegSpec]:
    """New leg specs when rolling a tested side outward in the breakout direction.

    `opt_type` "CE" rolls up (+), "PE" rolls down (-).  Returns the legs to OPEN;
    the engine closes the current legs of this side before opening these.

    scope:
      - "vertical"   : roll short + its wing together (constant-width protection).
      - "short_only" : roll only the short; keep the existing wing in place.
    """
    direction = 1.0 if opt_type == "CE" else -1.0
    new_short = cur_short + direction * roll_step
    if scope == "short_only":
        return [LegSpec(opt_type, new_short, "short")]
    new_long = new_short + direction * wing_width
    return [
        LegSpec(opt_type, new_short, "short"),
        LegSpec(opt_type, new_long, "long"),
    ]

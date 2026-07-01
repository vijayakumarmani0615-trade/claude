"""Shared signal type, used by every strategy so the backtest engine can stay
strategy-agnostic (it only ever touches these fields)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Signal:
    bar_index: int
    side: str            # "long" or "short"
    setup: str            # strategy-specific label, e.g. "reversal", "ema_pullback"
    level: float          # the reference price the signal is built on
    signal_close: float
    signal_high: float
    signal_low: float

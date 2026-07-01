"""EMA(8) trend-pullback strategy — signal generation.

Mechanical read of: "day has to be trending, then take the first pullback to
the 8 EMA."

  1. Trend filter (`ema_fast` vs `ema_slow`, both computed continuously across
     the whole series so they carry over day to day like on a chart):
       UP   : close > ema_slow, ema_fast > ema_slow, and ema_slow has risen
              over the last `trend_slope_bars` bars.
       DOWN : mirror image.
       Anything else -> no trend, no trade.

  2. Extension filter (`require_extension`): before the pullback, price must
     have been at least `extension_pct` away from ema_fast at some point in
     the last `extension_lookback_bars` bars — this is what makes it a
     genuine pullback rather than chop hugging the average.

  3. Entry trigger — first qualifying touch of ema_fast in the trend
     direction:
       LONG : bar's low touches into ema_fast (within `touch_pct`) and the
              bar closes back above ema_fast, green (close > open).
       SHORT: mirror (high touches ema_fast, closes back below, red).

A signal is emitted on the *close* of the signal bar; the backtester decides
the actual fill (default: next bar's open). "First visit per day" is enforced
by the caller via `risk.max_trades_per_day: 1`, not inside this class.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators.ema import ema
from .signal import Signal


class EmaPullbackStrategy:
    def __init__(self, cfg: dict, df: pd.DataFrame):
        sc = cfg["strategy"]
        self.ema_fast_n = int(sc.get("ema_fast", 8))
        self.ema_slow_n = int(sc.get("ema_slow", 50))
        self.trend_slope_bars = int(sc.get("trend_slope_bars", 10))
        self.touch_pct = float(sc.get("touch_pct", 0.0015))
        self.require_extension = bool(sc.get("require_extension", True))
        self.extension_pct = float(sc.get("extension_pct", 0.0015))
        self.extension_lookback = int(sc.get("extension_lookback_bars", 6))

        self.ema_fast = ema(df["close"], self.ema_fast_n).to_numpy()
        self.ema_slow = ema(df["close"], self.ema_slow_n).to_numpy()
        self.closes = df["close"].to_numpy()

    def _trend(self, i: int) -> str | None:
        if i < self.trend_slope_bars:
            return None
        fast, slow = self.ema_fast[i], self.ema_slow[i]
        prior_slow = self.ema_slow[i - self.trend_slope_bars]
        if np.isnan(fast) or np.isnan(slow) or np.isnan(prior_slow):
            return None
        if slow > 0 and fast > slow and slow > prior_slow:
            return "up"
        if slow > 0 and fast < slow and slow < prior_slow:
            return "down"
        return None

    def _was_extended(self, i: int, direction: str) -> bool:
        """Was price meaningfully away from ema_fast at some point recently?

        Confirms a genuine pullback rather than chop hugging the average.
        """
        if not self.require_extension:
            return True
        start = max(0, i - self.extension_lookback)
        for j in range(start, i):
            f = self.ema_fast[j]
            if np.isnan(f) or f <= 0:
                continue
            dist = (self.closes[j] - f) / f
            if direction == "up" and dist >= self.extension_pct:
                return True
            if direction == "down" and -dist >= self.extension_pct:
                return True
        return False

    def evaluate(self, i: int, bar) -> Signal | None:
        """Return a Signal for bar `i`, or None. `bar` is a row-like with OHLC."""
        direction = self._trend(i)
        if direction is None:
            return None

        f = self.ema_fast[i]
        if np.isnan(f) or f <= 0:
            return None

        o, h, l, c = bar.open, bar.high, bar.low, bar.close
        tol = f * self.touch_pct

        if direction == "up":
            touched = l <= f + tol
            closed_back = c > f and c > o
            if touched and closed_back and self._was_extended(i, "up"):
                return Signal(i, "long", "ema_pullback", float(f), c, h, l)
        else:  # down
            touched = h >= f - tol
            closed_back = c < f and c < o
            if touched and closed_back and self._was_extended(i, "down"):
                return Signal(i, "short", "ema_pullback", float(f), c, h, l)

        return None

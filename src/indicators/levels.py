"""Support / resistance level detection.

Two complementary level sources, because a single method rarely matches how a
discretionary trader reads a chart:

  1. Swing pivots (fractals): a swing high is a bar whose high is the highest
     among `left` bars before and `right` bars after it; a swing low mirrors
     that. These capture intraday structure that price reacts to.

  2. Daily pivot points: the classic PP / R1..R2 / S1..S2 computed from the
     PREVIOUS day's high/low/close. Index intraday traders lean on these
     heavily, so they are worth having as fixed reference levels.

Levels are clustered into "zones" so that many prints at nearly the same price
count as one level, and only levels formed recently (within `lookback_bars`)
stay active.

The key API is `LevelBook`, which — given the bar index `i` — returns the
active support and resistance zones *as they would have been known at that
bar* (no lookahead: a swing needs `right` future bars to confirm, so it only
becomes active `right` bars later).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Zone:
    price: float          # representative price of the clustered zone
    kind: str             # "support" or "resistance"
    formed_at: int        # bar index at which this level became *known*
    source: str           # "swing" or "pivot"
    hits: int = 1         # how many raw levels merged into this zone


def _find_swings(high: np.ndarray, low: np.ndarray, left: int, right: int):
    """Return (swing_high_idx, swing_low_idx) arrays of confirmed pivot bars.

    A pivot at bar t is confirmed only after `right` more bars exist, so callers
    must treat it as known from bar t + right onward.
    """
    n = len(high)
    sh, sl = [], []
    for t in range(left, n - right):
        h_window = high[t - left : t + right + 1]
        l_window = low[t - left : t + right + 1]
        if high[t] == h_window.max() and (high[t] > high[t - left : t]).all():
            sh.append(t)
        if low[t] == l_window.min() and (low[t] < low[t - left : t]).all():
            sl.append(t)
    return sh, sl


class LevelBook:
    """Precomputes swing pivots + daily pivots and serves active zones by bar."""

    def __init__(self, df: pd.DataFrame, cfg: dict):
        self.df = df
        lc = cfg["levels"]
        self.method = lc.get("method", "both")
        self.left = int(lc["swing_left"])
        self.right = int(lc["swing_right"])
        self.lookback = int(lc["lookback_bars"])
        self.zone_pct = float(lc["zone_pct"])
        self.max_levels = int(lc["max_levels"])

        high = df["high"].to_numpy()
        low = df["low"].to_numpy()

        # (bar_index_known_from, price, kind, source)
        self._events: list[tuple[int, float, str, str]] = []

        if self.method in ("swing", "both"):
            sh, sl = _find_swings(high, low, self.left, self.right)
            for t in sh:
                self._events.append((t + self.right, high[t], "resistance", "swing"))
            for t in sl:
                self._events.append((t + self.right, low[t], "support", "swing"))

        if self.method in ("pivots", "both"):
            self._add_daily_pivots(df)

        # Sort events by the bar they become known at, for efficient scanning.
        self._events.sort(key=lambda e: e[0])

    def _add_daily_pivots(self, df: pd.DataFrame) -> None:
        """Compute standard floor-trader pivots from each prior day's OHLC.

        A day's pivots become known from that day's first bar onward (they are
        derived purely from the *previous* completed day, so there is no
        lookahead).
        """
        day_key = df.index.normalize()
        # Map each date -> (bar index of its first bar).
        first_bar_of_day: dict[pd.Timestamp, int] = {}
        for i, d in enumerate(day_key):
            if d not in first_bar_of_day:
                first_bar_of_day[d] = i

        daily = df.groupby(day_key).agg(
            high=("high", "max"), low=("low", "min"), close=("close", "last")
        )
        dates = list(daily.index)
        for k in range(1, len(dates)):
            prev = daily.iloc[k - 1]
            pp = (prev["high"] + prev["low"] + prev["close"]) / 3.0
            rng = prev["high"] - prev["low"]
            r1 = 2 * pp - prev["low"]
            s1 = 2 * pp - prev["high"]
            r2 = pp + rng
            s2 = pp - rng
            known_from = first_bar_of_day[dates[k]]
            for price, kind in (
                (pp, "resistance"), (r1, "resistance"), (r2, "resistance"),
                (s1, "support"), (s2, "support"),
            ):
                # PP is neither inherently support nor resistance; we register it
                # on both sides so a touch from either direction is detected.
                self._events.append((known_from, float(price), kind, "pivot"))
                if kind == "resistance":
                    self._events.append((known_from, float(price), "support", "pivot"))

    def _cluster(self, raw: list[tuple[float, int, str]], kind: str) -> list[Zone]:
        """Merge nearby levels (within zone_pct) into representative zones."""
        if not raw:
            return []
        raw = sorted(raw, key=lambda x: x[0])
        zones: list[Zone] = []
        cur_prices = [raw[0][0]]
        cur_formed = raw[0][1]
        cur_source = raw[0][2]
        for price, formed, source in raw[1:]:
            anchor = cur_prices[0]
            if abs(price - anchor) <= anchor * self.zone_pct:
                cur_prices.append(price)
                cur_formed = max(cur_formed, formed)
            else:
                zones.append(
                    Zone(float(np.mean(cur_prices)), kind, cur_formed, cur_source,
                         hits=len(cur_prices))
                )
                cur_prices, cur_formed, cur_source = [price], formed, source
        zones.append(
            Zone(float(np.mean(cur_prices)), kind, cur_formed, cur_source,
                 hits=len(cur_prices))
        )
        return zones

    def active(self, i: int) -> tuple[list[Zone], list[Zone]]:
        """Active (support_zones, resistance_zones) known at bar index `i`.

        Only levels known at or before bar `i` and formed within `lookback`
        bars are considered. Zones are returned nearest-to-price first and
        capped at `max_levels` per side.
        """
        price = self.df["close"].iloc[i]
        sup_raw, res_raw = [], []
        for known_from, lvl_price, kind, source in self._events:
            if known_from > i:
                break  # events are sorted; nothing later is known yet
            if i - known_from > self.lookback:
                continue
            if kind == "support":
                sup_raw.append((lvl_price, known_from, source))
            else:
                res_raw.append((lvl_price, known_from, source))

        supports = self._cluster(sup_raw, "support")
        resistances = self._cluster(res_raw, "resistance")

        # Keep the nearest levels to current price on each side.
        supports.sort(key=lambda z: abs(z.price - price))
        resistances.sort(key=lambda z: abs(z.price - price))
        return supports[: self.max_levels], resistances[: self.max_levels]

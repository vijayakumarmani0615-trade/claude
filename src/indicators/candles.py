"""Candlestick rejection patterns, shared across strategies."""
from __future__ import annotations


def bull_pin(o: float, h: float, l: float, c: float,
             wick_ratio: float, opp_ratio: float, min_frac: float) -> bool:
    """Hammer / bullish pin bar: long lower wick, small body up top."""
    rng = h - l
    if rng <= 0:
        return False
    body = abs(c - o)
    lower = min(o, c) - l
    upper = h - max(o, c)
    return (
        lower >= wick_ratio * body
        and lower >= opp_ratio * upper
        and lower >= min_frac * rng
    )


def bear_pin(o: float, h: float, l: float, c: float,
             wick_ratio: float, opp_ratio: float, min_frac: float) -> bool:
    """Inverted hammer / bearish pin bar: long upper wick, small body low."""
    rng = h - l
    if rng <= 0:
        return False
    body = abs(c - o)
    lower = min(o, c) - l
    upper = h - max(o, c)
    return (
        upper >= wick_ratio * body
        and upper >= opp_ratio * lower
        and upper >= min_frac * rng
    )

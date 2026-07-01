"""Futures margin + capital-adequacy math for fixed-lot sizing.

`margin_pct` is a ROUGH stand-in for actual exchange SPAN + exposure margin
(which moves with volatility and isn't a fixed percentage) -- typically
10-15% of contract value for Nifty futures in practice. Confirm the real
number with your broker before trusting any of this for live capital; this
module is for catching an order-of-magnitude problem (e.g. "1 lot doesn't
even fit"), not for precise margin planning.
"""
from __future__ import annotations


def contract_value(price: float, lot_size: int) -> float:
    return price * lot_size


def required_margin(price: float, lot_size: int, margin_pct: float) -> float:
    """Approximate SPAN + exposure margin for one lot at `price`."""
    return contract_value(price, lot_size) * margin_pct


def capital_at_risk(price: float, lot_size: int, margin_pct: float, stop_points: float) -> float:
    """Margin tied up PLUS the worst-case single-trade loss (stop hit).

    This is what actually needs to fit in your capital: the margin doesn't
    free up mid-trade, and a losing trade eats into it before you get out.
    """
    return required_margin(price, lot_size, margin_pct) + stop_points * lot_size


def is_safe(capital: float, price: float, lot_size: int, margin_pct: float,
            stop_points: float, buffer_pct: float) -> bool:
    """Is 1 lot safe, leaving `buffer_pct` of capital unused as headroom for
    adverse mark-to-market moves / margin calls beyond the modeled stop?
    """
    return capital_at_risk(price, lot_size, margin_pct, stop_points) <= capital * (1 - buffer_pct)


def max_safe_lots(capital: float, price: float, lot_size: int, margin_pct: float,
                   stop_points: float, buffer_pct: float) -> int:
    per_lot = capital_at_risk(price, lot_size, margin_pct, stop_points)
    if per_lot <= 0:
        return 0
    return int((capital * (1 - buffer_pct)) // per_lot)

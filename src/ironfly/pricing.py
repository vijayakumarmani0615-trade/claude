"""Black-Scholes option pricing.

Used for two things only:
  1. Generating the *synthetic* option chain that lets the pipeline run offline.
  2. An intrinsic-value fallback when a real chain is missing a price for a leg
     we need to close (deep ITM/OTM strikes can be illiquid near expiry).

Real backtests price legs from the supplied chain, not from this model.
"""
from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: float, t_years: float, iv: float,
             opt_type: str, r: float = 0.0) -> float:
    """Black-Scholes price of a European CE/PE. `t_years` is time to expiry."""
    opt_type = opt_type.upper()
    if t_years <= 0 or iv <= 0:
        return intrinsic(spot, strike, opt_type)
    vol_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / vol_t
    d2 = d1 - vol_t
    disc = math.exp(-r * t_years)
    if opt_type == "CE":
        return spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2)
    return strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def intrinsic(spot: float, strike: float, opt_type: str) -> float:
    """Exercise value at expiry."""
    if opt_type.upper() == "CE":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)

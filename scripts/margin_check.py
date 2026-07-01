"""Is 1 lot actually safe on ₹2,00,000 capital, across the whole backtest
history and today?

Sizing is fixed_lot (1 lot regardless of stop distance), but margin isn't
fixed -- it scales with the index price, which has roughly doubled from
~12,000 (2020) to ~23,800 (2026) over the backtested period. This checks
whether the capital assumption actually held up throughout, not just today.

margin_pct is a ROUGH stand-in for real SPAN + exposure margin (see
src/risk/margin.py) -- confirm the real number with your broker.
"""
from __future__ import annotations

import yaml

from src.data import loader
from src.risk import margin


def main():
    with open("config_ema_pullback.yaml") as f:
        cfg = yaml.safe_load(f)

    r = cfg["risk"]
    capital = float(r["capital"])
    lot_size = int(r["lot_size"])
    margin_pct = float(r.get("margin_pct", 0.12))
    buffer_pct = float(r.get("margin_buffer_pct", 0.30))
    stop_points = float(r["sl_fixed_points"])

    df = loader.load(cfg)
    closes = df["close"]

    req_margin = closes.apply(lambda p: margin.required_margin(p, lot_size, margin_pct))
    risk_amt = closes.apply(lambda p: margin.capital_at_risk(p, lot_size, margin_pct, stop_points))
    safe_threshold = capital * (1 - buffer_pct)

    print("=" * 70)
    print(f"Capital: Rs.{capital:,.0f}  |  Lot size: {lot_size}  |  "
          f"margin_pct: {margin_pct:.0%} (rough estimate)  |  "
          f"buffer: {buffer_pct:.0%} -> safe threshold Rs.{safe_threshold:,.0f}")
    print("=" * 70)

    print(f"\nRequired margin for 1 lot, over {df.index[0].date()} -> {df.index[-1].date()}:")
    print(f"  min : Rs.{req_margin.min():,.0f}  (index @ {closes[req_margin.idxmin()]:,.0f} "
          f"on {req_margin.idxmin().date()})")
    print(f"  max : Rs.{req_margin.max():,.0f}  (index @ {closes[req_margin.idxmax()]:,.0f} "
          f"on {req_margin.idxmax().date()})")
    print(f"  now : Rs.{req_margin.iloc[-1]:,.0f}  (index @ {closes.iloc[-1]:,.0f})")

    print(f"\nCapital-at-risk (margin + {stop_points:.0f}pt stop loss), same period:")
    print(f"  min : Rs.{risk_amt.min():,.0f}")
    print(f"  max : Rs.{risk_amt.max():,.0f}")
    print(f"  now : Rs.{risk_amt.iloc[-1]:,.0f}")

    over_capital = req_margin[req_margin > capital]
    over_safe = risk_amt[risk_amt > safe_threshold]
    print(f"\nBars where margin alone exceeds Rs.{capital:,.0f} capital: "
          f"{len(over_capital)} / {len(df)} ({len(over_capital)/len(df)*100:.1f}%)")
    if len(over_capital):
        print(f"  first breach: {over_capital.index[0]}  (index @ {closes[over_capital.index[0]]:,.0f})")

    print(f"\nBars where capital-at-risk exceeds the Rs.{safe_threshold:,.0f} safe "
          f"threshold ({buffer_pct:.0%} buffer): "
          f"{len(over_safe)} / {len(df)} ({len(over_safe)/len(df)*100:.1f}%)")
    if len(over_safe):
        print(f"  first breach: {over_safe.index[0]}  (index @ {closes[over_safe.index[0]]:,.0f})")

    # What capital would have been needed to stay safe for the WHOLE period?
    needed = risk_amt.max() / (1 - buffer_pct)
    print(f"\nCapital needed to keep 1 lot safe (with buffer) for the ENTIRE "
          f"backtested period: Rs.{needed:,.0f}")


if __name__ == "__main__":
    main()

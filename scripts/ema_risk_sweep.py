"""Stop x target sweep, re-viewed through a risk lens for a Rs.2,00,000
account rather than just net P&L / profit factor (see scripts/ema_sweep.py
for the original profitability-only version).

For each combo this adds:
  - worst losing streak (consecutive losses) and the cumulative loss over it
    -- the bad patch you'd actually need to sit through.
  - capital-at-risk (margin + this combo's stop, see src/risk/margin.py),
    evaluated at the WORST (highest) index price seen in the backtest, so it
    reflects the toughest point in history, not just today.
  - whether 1 lot stays within the safe capital buffer at that worst price.

Margin numbers are a ROUGH estimate (`risk.margin_pct` in the config) --
confirm the real figure with your broker.
"""
from __future__ import annotations

import copy
import itertools

import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
from src.risk import margin
from src.strategy.ema_pullback import EmaPullbackStrategy

STOPS = [10, 15, 20, 25, 30, 40, 50]
TARGETS = [15, 20, 30, 40, 50, 60, 80, 100, 120]


def base_cfg():
    with open("config_ema_pullback.yaml") as f:
        return yaml.safe_load(f)


def run_one(df, cfg):
    strat = EmaPullbackStrategy(cfg, df)
    bt = Backtester(df, cfg, strategy=strat)
    trades = bt.run()
    return metrics.compute(trades, bt.capital0)


def main():
    cfg = base_cfg()
    df = loader.load(cfg)  # load once, reuse

    r = cfg["risk"]
    capital = float(r["capital"])
    lot_size = int(r["lot_size"])
    margin_pct = float(r.get("margin_pct", 0.12))
    buffer_pct = float(r.get("margin_buffer_pct", 0.30))
    worst_price = float(df["close"].max())  # toughest point in history for margin

    print(f"Capital Rs.{capital:,.0f}  |  lot_size {lot_size}  |  "
          f"margin_pct {margin_pct:.0%} (rough)  |  buffer {buffer_pct:.0%}  |  "
          f"worst historical index price: {worst_price:,.0f}\n")

    print(f"{'stop':>5}{'target':>8}{'PF':>7}{'net(L)':>9}{'maxDD%':>8}"
          f"{'worstStreak':>13}{'streakLoss':>12}{'capAtRisk':>12}{'safe?':>7}")
    for stop, target in itertools.product(STOPS, TARGETS):
        if target <= stop:
            continue
        c = copy.deepcopy(cfg)
        c["risk"]["sl_fixed_points"] = stop
        c["risk"]["target_fixed_points"] = target
        m = run_one(df, c)
        if m.get("trades", 0) == 0:
            continue

        car = margin.capital_at_risk(worst_price, lot_size, margin_pct, stop)
        safe = margin.is_safe(capital, worst_price, lot_size, margin_pct, stop, buffer_pct)

        print(f"{stop:>5}{target:>8}{str(m['profit_factor']):>7}"
              f"{m['net_pnl']/1e5:>9.2f}{m['max_drawdown_pct']:>8}"
              f"{m['max_losing_streak']:>13}{m['worst_streak_loss']:>12,.0f}"
              f"{car:>12,.0f}{'yes' if safe else 'NO':>7}")

    print(f"\nNote: capital-at-risk and safe/NO use the WORST historical index "
          f"price ({worst_price:,.0f}), independent of stop/target choice -- it "
          f"only changes with the stop distance (bigger stop = more at risk).")
    print("Since margin scales with price, not with which stop/target you pick, "
          "no stop/target combo fixes an undersized-capital problem -- see "
          "scripts/margin_check.py for that.")


if __name__ == "__main__":
    main()

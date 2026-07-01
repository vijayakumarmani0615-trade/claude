"""Fair re-tune of the EMA pullback strategy for 75-min bars.

The previous 75-min run reused the 15-min config verbatim and came back
weak (PF 1.06), but that wasn't a fair test: every strategy parameter is
counted in bars, and 75-min bars have ~2.1x the high-low range of 15-min
bars (measured directly from the data), not the same. This sweeps:

  - trend_slope_bars / extension_lookback_bars at wall-clock-equivalent
    values for 75-min (a 75-min bar is 5x a 15-min bar), alongside the
    original bar-count values for comparison.
  - stop/target scaled ~2x the 15-min grid to match 75-min's larger typical
    range, still keeping target > stop.

Reports the best combos found, and how they compare to both the "same
config" 75-min baseline and the committed 15-min result.
"""
from __future__ import annotations

import copy
import itertools

import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
from src.strategy.ema_pullback import EmaPullbackStrategy

# (trend_slope_bars, extension_lookback_bars) candidates.
# 10/6 = the 15-min bar-counts reused verbatim (baseline, for comparison).
# 2/1 and 3/2 = wall-clock-equivalent to 15-min's 10/6 (10*15/75=2, 6*15/75=1.2).
BAR_PARAMS = [(10, 6), (2, 1), (3, 2), (4, 2)]
STOPS = [20, 30, 40, 50, 60, 80, 100]
TARGETS = [30, 40, 60, 80, 100, 120, 150, 200, 250]


def base_cfg():
    with open("config_ema_pullback_75m.yaml") as f:
        return yaml.safe_load(f)


def run_one(df, cfg):
    strat = EmaPullbackStrategy(cfg, df)
    bt = Backtester(df, cfg, strategy=strat)
    trades = bt.run()
    return metrics.compute(trades, bt.capital0)


def main():
    cfg = base_cfg()
    df = loader.load(cfg)  # load once, reuse

    results = []
    for slope_bars, ext_bars in BAR_PARAMS:
        for stop, target in itertools.product(STOPS, TARGETS):
            if target <= stop:
                continue
            c = copy.deepcopy(cfg)
            c["strategy"]["trend_slope_bars"] = slope_bars
            c["strategy"]["extension_lookback_bars"] = ext_bars
            c["risk"]["sl_fixed_points"] = stop
            c["risk"]["target_fixed_points"] = target
            m = run_one(df, c)
            if m.get("trades", 0) < 30:  # skip combos with too few trades to trust
                continue
            results.append((slope_bars, ext_bars, stop, target, m))

    results.sort(key=lambda r: r[4]["net_pnl"], reverse=True)

    print(f"{'slope':>6}{'ext':>5}{'stop':>6}{'target':>8}{'trades':>8}"
          f"{'win%':>7}{'PF':>7}{'net(L)':>9}{'maxDD%':>8}")
    for slope_bars, ext_bars, stop, target, m in results[:20]:
        print(f"{slope_bars:>6}{ext_bars:>5}{stop:>6}{target:>8}{m['trades']:>8}"
              f"{m['win_rate_pct']:>7}{str(m['profit_factor']):>7}"
              f"{m['net_pnl']/1e5:>9.2f}{m['max_drawdown_pct']:>8}")

    print(f"\nTotal combos tested: {len(results)}")
    print("NOTE: figures below are historical, from BEFORE the touch_pct fix "
          "(see FINDINGS.md) -- kept only so old runs of this script are not "
          "silently mysterious, not as a live baseline to compare against.")
    print("  same-15min-config on 75-min (slope=10,ext=6,20/40): PF 1.06, win 40.9%, "
          "net +0.68L, maxDD -42.4% (pre-fix)")
    print("  15-min committed (slope=10,ext=6,20/40 @ 15-min bars): PF 2.14, win 57.5%, "
          "net +11.67L, maxDD -9.6% (pre-fix)")


if __name__ == "__main__":
    main()

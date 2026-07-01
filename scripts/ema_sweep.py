"""Sweep fixed stop x target combinations for the EMA(8) pullback strategy
to check whether the 20pt/40pt result is a lucky point in the parameter
space or part of a broader profitable region. See FINDINGS.md for the
committed 20/40 result and caveats; this reproduces the sweep behind them.
"""
from __future__ import annotations

import copy
import itertools

import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
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
    m = metrics.compute(trades, bt.capital0)
    return m


def main():
    cfg = base_cfg()
    df = loader.load(cfg)  # load once, reuse

    print("=== STOP x TARGET grid (EMA pullback, enter-on-touch) ===")
    print(f"{'stop':>5}{'target':>8}{'trades':>8}{'win%':>7}{'PF':>7}"
          f"{'net(L)':>10}{'maxDD%':>9}{'exp/trade':>11}")
    best = None
    for stop, target in itertools.product(STOPS, TARGETS):
        if target <= stop:
            continue
        c = copy.deepcopy(cfg)
        c["risk"]["sl_fixed_points"] = stop
        c["risk"]["target_fixed_points"] = target
        m = run_one(df, c)
        if m.get("trades", 0) == 0:
            continue
        pf = m["profit_factor"]
        net_l = m["net_pnl"] / 1e5
        print(f"{stop:>5}{target:>8}{m['trades']:>8}{m['win_rate_pct']:>7}"
              f"{str(pf):>7}{net_l:>10.2f}{m['max_drawdown_pct']:>9}"
              f"{m['expectancy_per_trade']:>11.0f}")
        score = m["net_pnl"]
        if best is None or score > best[0]:
            best = (score, stop, target, m)

    if best:
        _, s, t, m = best
        print(f"\nBest by net P&L: stop={s} target={t} -> "
              f"PF={m['profit_factor']} win%={m['win_rate_pct']} "
              f"net={m['net_pnl']:.0f} maxDD%={m['max_drawdown_pct']}")

    # How many combos beat the committed 20/40 config, and by how much.
    base_m = run_one(df, cfg)
    print(f"\nCommitted config (20/40): net={base_m['net_pnl']:.0f} "
          f"PF={base_m['profit_factor']} win%={base_m['win_rate_pct']} "
          f"maxDD%={base_m['max_drawdown_pct']}")


if __name__ == "__main__":
    main()

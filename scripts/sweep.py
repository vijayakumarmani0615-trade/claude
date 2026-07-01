"""Sweep fixed stop x target combinations (and per-setup) to find any edge.

Signals don't depend on the exits, but re-running the whole backtest per combo
is fast enough (~5s each), so we keep it simple and just vary the config.
"""
from __future__ import annotations

import copy
import itertools

import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics

STOPS = [20, 30, 40, 50, 60]
TARGETS = [40, 60, 80, 100, 120]


def base_cfg():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["risk"]["sl_method"] = "fixed"
    cfg["risk"]["target_method"] = "fixed"
    return cfg


def run_one(df, cfg):
    bt = Backtester(df, cfg)
    trades = bt.run()
    m = metrics.compute(trades, bt.capital0)
    return m, trades


def main():
    cfg = base_cfg()
    df = loader.load(cfg)  # load once, reuse

    print("=== STOP x TARGET grid (all setups) ===")
    print(f"{'stop':>5}{'target':>8}{'trades':>8}{'win%':>7}{'PF':>7}{'net(L)':>10}{'exp/trade':>11}")
    best = None
    for stop, target in itertools.product(STOPS, TARGETS):
        if target <= stop:
            continue
        c = copy.deepcopy(cfg)
        c["risk"]["sl_fixed_points"] = stop
        c["risk"]["target_fixed_points"] = target
        m, _ = run_one(df, c)
        if m.get("trades", 0) == 0:
            continue
        pf = m["profit_factor"]
        net_l = m["net_pnl"] / 1e5
        print(f"{stop:>5}{target:>8}{m['trades']:>8}{m['win_rate_pct']:>7}"
              f"{str(pf):>7}{net_l:>10.2f}{m['expectancy_per_trade']:>11.0f}")
        score = m["net_pnl"]
        if best is None or score > best[0]:
            best = (score, stop, target, m)

    if best:
        _, s, t, m = best
        print(f"\nBest by net P&L: stop={s} target={t} -> "
              f"PF={m['profit_factor']} win%={m['win_rate_pct']} net={m['net_pnl']:.0f}")

    # Per-setup / per-side at the user's 30/70 to see where the edge lives.
    print("\n=== 30/70, isolating each setup+side ===")
    for setup in ("reversal", "false_break"):
        for rev, fb in [((setup == "reversal"), (setup == "false_break"))]:
            c = copy.deepcopy(cfg)
            c["risk"]["sl_fixed_points"] = 30
            c["risk"]["target_fixed_points"] = 70
            c["strategy"]["setups"]["reversal"] = rev
            c["strategy"]["setups"]["false_break"] = fb
            m, trades = run_one(df, c)
            longs = [x for x in trades if x.side == "long"]
            shorts = [x for x in trades if x.side == "short"]
            ln = sum(x.pnl for x in longs)
            sn = sum(x.pnl for x in shorts)
            print(f"  {setup:12s}  all: PF={m['profit_factor']} net={m['net_pnl']/1e5:.2f}L "
                  f"| long net={ln/1e5:.2f}L ({len(longs)}) short net={sn/1e5:.2f}L ({len(shorts)})")


if __name__ == "__main__":
    main()

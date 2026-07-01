"""Deliberately test a small FIXED-point touch tolerance (touch_buffer_points),
now that a literal touch (touch_pct=0) came back with no edge but the old
percentage-based tolerance (accidentally ~35-40pt) had one.

Rather than accept the old tolerance as a lucky accident, this sweeps a
range of small, fixed-point buffers (which don't scale with price the way a
percentage does) to see if a deliberately-chosen "close enough" zone
recovers a genuine, non-accidental edge -- and where it stops being genuine
and starts being "the old bug with smaller numbers."

Stage 1: buffer alone at the committed 20/40 stop/target.
Stage 2: full stop/target sweep at whichever buffer looks best in stage 1.
"""
from __future__ import annotations

import copy
import itertools

import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
from src.strategy.ema_pullback import EmaPullbackStrategy

BUFFERS = [0, 2, 3, 5, 7, 10, 15, 20, 25, 30, 35, 40]
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

    print("=== Stage 1: touch_buffer_points alone, stop=20 / target=40 ===")
    print(f"{'buffer_pts':>11}{'trades':>8}{'win%':>7}{'PF':>7}{'net(L)':>9}{'maxDD%':>8}")
    for buf in BUFFERS:
        c = copy.deepcopy(cfg)
        c["strategy"]["touch_buffer_points"] = buf
        m = run_one(df, c)
        print(f"{buf:>11}{m['trades']:>8}{m['win_rate_pct']:>7}{str(m['profit_factor']):>7}"
              f"{m['net_pnl']/1e5:>9.2f}{m['max_drawdown_pct']:>8}")

    print("\n=== Stage 2: full stop/target sweep at a few candidate buffers ===")
    for buf in (5, 10, 15, 20):
        print(f"\n--- touch_buffer_points = {buf} ---")
        print(f"{'stop':>5}{'target':>8}{'trades':>8}{'win%':>7}{'PF':>7}{'net(L)':>9}{'maxDD%':>8}")
        best = None
        for stop, target in itertools.product(STOPS, TARGETS):
            if target <= stop:
                continue
            c = copy.deepcopy(cfg)
            c["strategy"]["touch_buffer_points"] = buf
            c["risk"]["sl_fixed_points"] = stop
            c["risk"]["target_fixed_points"] = target
            m = run_one(df, c)
            if m.get("trades", 0) == 0:
                continue
            if best is None or m["net_pnl"] > best[2]["net_pnl"]:
                best = (stop, target, m)
        if best:
            stop, target, m = best
            print(f"{stop:>5}{target:>8}{m['trades']:>8}{m['win_rate_pct']:>7}"
                  f"{str(m['profit_factor']):>7}{m['net_pnl']/1e5:>9.2f}{m['max_drawdown_pct']:>8}"
                  f"   <- best net P&L at this buffer")


if __name__ == "__main__":
    main()

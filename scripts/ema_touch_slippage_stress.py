"""Stress-test the EMA pullback's touch-fill assumption: how much extra
adverse slippage on entry (beyond the modeled slippage_pct) can the 20pt
stop / 40pt target withstand before the edge disappears?

The backtest fills entries at the exact ema_fast level the instant a bar's
range reaches it -- a clean assumption that may not survive real order
queues/liquidity on Nifty futures. `entry_touch_extra_slippage_points` adds
flat adverse points on top of the existing pct-based slippage, entries only.
"""
from __future__ import annotations

import copy

import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
from src.strategy.ema_pullback import EmaPullbackStrategy

EXTRA_SLIPPAGE_POINTS = [0, 1, 2, 3, 4, 5, 7, 10, 15, 20]


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

    print("=== Extra adverse slippage on touch-fill entries (20pt/40pt) ===")
    print(f"{'extra_pts':>10}{'trades':>8}{'win%':>7}{'PF':>7}{'net(L)':>10}{'exp/trade':>11}")
    for extra in EXTRA_SLIPPAGE_POINTS:
        c = copy.deepcopy(cfg)
        c["costs"]["entry_touch_extra_slippage_points"] = extra
        m = run_one(df, c)
        pf = m["profit_factor"]
        net_l = m["net_pnl"] / 1e5
        flag = "  <- turns net-negative" if m["net_pnl"] < 0 else ""
        print(f"{extra:>10}{m['trades']:>8}{m['win_rate_pct']:>7}"
              f"{str(pf):>7}{net_l:>10.2f}{m['expectancy_per_trade']:>11.0f}{flag}")


if __name__ == "__main__":
    main()

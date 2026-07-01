"""Out-of-sample check for the EMA pullback strategy.

So far the entry-timing fix and the stop/target sweep were both evaluated
against the full 2020-2026 history at once -- which risks the good numbers
being an artifact of having seen the whole period. This script runs the
backtest ONCE (so EMA warm-up stays continuous and correct across the split
boundary) and then splits the resulting trades into an "in-sample" period
(2020-2022, what we could have judged the strategy on originally) and an
"out-of-sample" period (2023-2026, held out) to see whether the edge that
shows up in-sample actually persists in the unseen period.

Also repeats the check for the sweep's grid-optimal combo (10pt stop / 120pt
target) to see whether that more extreme combo is equally robust or more of
a full-period artifact.
"""
from __future__ import annotations

import copy

import pandas as pd
import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
from src.strategy.ema_pullback import EmaPullbackStrategy

SPLIT_DATE = pd.Timestamp("2023-01-01")


def base_cfg():
    with open("config_ema_pullback.yaml") as f:
        return yaml.safe_load(f)


def run_and_split(df, cfg, capital):
    strat = EmaPullbackStrategy(cfg, df)
    bt = Backtester(df, cfg, strategy=strat)
    trades = bt.run()
    in_sample = [t for t in trades if t.entry_time < SPLIT_DATE]
    out_sample = [t for t in trades if t.entry_time >= SPLIT_DATE]
    return metrics.compute(in_sample, capital), metrics.compute(out_sample, capital)


def report(label, m_in, m_out):
    print("=" * 70)
    print(label)
    print("=" * 70)
    print(f"{'metric':>22}  {'in-sample (2020-22)':>22}  {'out-of-sample (2023-26)':>24}")
    for k in ("trades", "net_pnl", "win_rate_pct", "profit_factor", "avg_r", "max_drawdown_pct"):
        print(f"{k:>22}  {str(m_in.get(k)):>22}  {str(m_out.get(k)):>24}")
    print()


def main():
    cfg = base_cfg()
    df = loader.load(cfg)  # full continuous series -> EMA warm-up stays correct
    capital = float(cfg["risk"]["capital"])

    m_in, m_out = run_and_split(df, cfg, capital)
    report("Committed config: 20pt stop / 40pt target", m_in, m_out)

    grid_best = copy.deepcopy(cfg)
    grid_best["risk"]["sl_fixed_points"] = 10
    grid_best["risk"]["target_fixed_points"] = 120
    m_in2, m_out2 = run_and_split(df, grid_best, capital)
    report("Grid-optimal from sweep: 10pt stop / 120pt target", m_in2, m_out2)


if __name__ == "__main__":
    main()

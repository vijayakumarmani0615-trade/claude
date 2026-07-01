"""Out-of-sample check for the re-tuned 75-min EMA pullback config.

Mirrors scripts/ema_oos_validation.py (the 15-min check): the 75-min
re-tune (scripts/ema_75m_retune.py) picked its stop/target/lookback combo
by sweeping the full 2020-2026 history, which risks the good numbers being
partly an artifact of having seen the whole period. This runs the backtest
once (so the EMA warm-up stays continuous across the split boundary) and
splits the resulting trades into in-sample (2020-2022) and held-out
out-of-sample (2023-2026), for both the committed 75-min combo and the
next-best alternative from the sweep.
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
    with open("config_ema_pullback_75m.yaml") as f:
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
    cfg = base_cfg()  # already the committed retuned combo: slope=2, ext=1, 20/120
    df = loader.load(cfg)  # full continuous series -> EMA warm-up stays correct
    capital = float(cfg["risk"]["capital"])

    m_in, m_out = run_and_split(df, cfg, capital)
    report("Committed 75-min config: slope=2, ext=1, 20pt/120pt", m_in, m_out)

    alt = copy.deepcopy(cfg)
    alt["strategy"]["trend_slope_bars"] = 3
    alt["strategy"]["extension_lookback_bars"] = 2
    alt["risk"]["sl_fixed_points"] = 20
    alt["risk"]["target_fixed_points"] = 150
    m_in2, m_out2 = run_and_split(df, alt, capital)
    report("Alternative (best net/PF in sweep): slope=3, ext=2, 20pt/150pt", m_in2, m_out2)


if __name__ == "__main__":
    main()

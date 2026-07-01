"""Compare the EMA pullback baseline against two variants meant to rule out
an exit/filter artifact: dropping the extension-before-pullback filter, and
swapping the fixed 20pt stop for a structure-based one (beyond the signal
bar's low/high) with a 2R target. See FINDINGS.md for the results table.
"""
from __future__ import annotations

import copy

import pandas as pd
import yaml

from src.data import loader
from src.backtest.engine import Backtester, trades_to_frame
from src.backtest import metrics
from src.strategy.ema_pullback import EmaPullbackStrategy


def base_cfg():
    with open("config_ema_pullback.yaml") as f:
        return yaml.safe_load(f)


def run_one(df, cfg):
    strat = EmaPullbackStrategy(cfg, df)
    bt = Backtester(df, cfg, strategy=strat)
    trades = bt.run()
    m = metrics.compute(trades, bt.capital0)
    tdf = trades_to_frame(trades)
    yearly = None
    if not tdf.empty:
        tdf["year"] = pd.to_datetime(tdf["entry_time"]).dt.year
        yearly = tdf.groupby("year")["pnl"].agg(
            trades="count", net_pnl="sum", win_rate=lambda s: round((s > 0).mean() * 100, 1)
        )
    return m, yearly


def main():
    cfg = base_cfg()
    df = loader.load(cfg)  # load once, reuse

    variants = {
        "baseline (extension on, fixed 20/40)": lambda c: c,
        "A: extension off (fixed 20/40)": lambda c: {
            **c, "strategy": {**c["strategy"], "require_extension": False}
        },
        "B: structure stop, 2R target (extension on)": lambda c: {
            **c, "risk": {**c["risk"], "sl_method": "structure",
                          "target_method": "rr", "rr_multiple": 2.0}
        },
        "C: extension off + structure stop, 2R target": lambda c: {
            **c,
            "strategy": {**c["strategy"], "require_extension": False},
            "risk": {**c["risk"], "sl_method": "structure",
                     "target_method": "rr", "rr_multiple": 2.0},
        },
    }

    for label, mutate in variants.items():
        variant_cfg = mutate(copy.deepcopy(cfg))
        m, yearly = run_one(df, variant_cfg)
        print("=" * 70)
        print(label)
        print("=" * 70)
        for k, v in m.items():
            print(f"  {k:22s}: {v}")
        if yearly is not None:
            print(yearly)
        print()


if __name__ == "__main__":
    main()

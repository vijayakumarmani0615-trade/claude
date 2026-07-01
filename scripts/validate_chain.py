"""Coverage check for a real option chain before trusting a backtest.

Answers: does the supplied chain actually cover the strikes and expiries the iron
fly needs? How many weekly cycles are tradable, and why are the rest skipped?

Usage:
    python scripts/validate_chain.py --config config_ironfly.yaml \
        --spot data/nifty_daily.csv --options data/nifty_options.csv
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ironfly import data
from src.ironfly.engine import IronFlyBacktester


def main() -> None:
    p = argparse.ArgumentParser(description="Validate an option chain for the iron fly")
    p.add_argument("--config", default="config_ironfly.yaml")
    p.add_argument("--spot")
    p.add_argument("--options")
    args = p.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    cfg["data"]["source"] = "csv"
    if args.spot:
        cfg["data"]["spot_csv"] = args.spot
    if args.options:
        cfg["data"]["options_csv"] = args.options

    spot, chain = data.load(cfg)
    bt = IronFlyBacktester(spot, chain, cfg)
    cycles = bt.run()

    span = [(chain.strikes[e].min(), chain.strikes[e].max(), len(chain.strikes[e]))
            for e in chain.expiries]
    widths = [hi - lo for lo, hi, _ in span]
    need = cfg["strategy"]["wing_width"] + \
        cfg["strategy"]["roll_step"] * cfg["strategy"]["max_rolls_per_side"]

    line = "=" * 60
    print(line)
    print("  OPTION CHAIN COVERAGE")
    print(line)
    print(f"  Spot bars     : {len(spot)}  ({spot.index[0].date()} -> {spot.index[-1].date()})")
    print(f"  Chain expiries: {len(chain.expiries)}  "
          f"({chain.expiries[0].date()} -> {chain.expiries[-1].date()})")
    print(f"  Strikes/expiry: median {int(np.median([n for *_, n in span]))}, "
          f"min {min(n for *_, n in span)}")
    print(f"  Strike span   : median {int(np.median(widths))} pts "
          f"(need >= {need} around ATM for wings + rolls)")
    print(line)
    print(f"  Tradable cycles: {len(cycles)}")
    print(f"  Skipped cycles : {len(bt.skipped)}")
    if bt.skipped:
        reasons = pd.Series([r[2].split(" ")[0] for r in bt.skipped]).value_counts()
        for reason, n in reasons.items():
            print(f"    - {reason:12s}: {n}")
        print("  first few skips:")
        for row in bt.skipped[:6]:
            print(f"    {row[0].date()} exp {row[1].date()}: {row[2]}")
    print(line)
    if cycles:
        intrinsic_exits = sum(
            1 for c in cycles for l in c.legs
            if l.exit_reason == "expiry" and
            chain.price(c.expiry, l.strike, l.opt_type, l.exit_time) is None
        )
        print(f"  Legs settled at intrinsic (missing expiry-day price): {intrinsic_exits}")
        print(f"  Avg rolls/cycle: {np.mean([c.rolls_ce + c.rolls_pe for c in cycles]):.2f}")
    print(line)
    if len(cycles) == 0:
        print("  No tradable cycles. Check that spot dates overlap the chain and")
        print("  that strikes exist around ATM for each weekly expiry.")


if __name__ == "__main__":
    main()

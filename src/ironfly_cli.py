"""Iron fly backtester entry point.

Usage:
    python -m src.ironfly_cli --config config_ironfly.yaml
    python -m src.ironfly_cli --source csv \
        --spot data/nifty_15m.csv --options data/nifty_options.csv

Writes to results_ironfly/:
    summary.json  - headline metrics
    cycles.csv    - one row per weekly iron fly
    legs.csv      - every leg (entry/exit/pnl), incl. rolls
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .ironfly import data, metrics
from .ironfly.engine import IronFlyBacktester


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _apply_overrides(cfg: dict, args) -> dict:
    if args.source:
        cfg["data"]["source"] = args.source
    if args.spot:
        cfg["data"]["source"] = "csv"
        cfg["data"]["spot_csv"] = args.spot
    if args.options:
        cfg["data"]["source"] = "csv"
        cfg["data"]["options_csv"] = args.options
    return cfg


def run(cfg: dict, outdir: Path) -> dict:
    spot, chain = data.load(cfg)
    bt = IronFlyBacktester(spot, chain, cfg)
    cycles = bt.run()

    capital = float(cfg["lots"].get("capital", 1_000_000))
    summary = metrics.compute(cycles, capital)

    outdir.mkdir(parents=True, exist_ok=True)
    cdf = metrics.cycles_to_frame(cycles)
    ldf = metrics.legs_to_frame(cycles)
    if not cdf.empty:
        cdf.to_csv(outdir / "cycles.csv", index=False)
    if not ldf.empty:
        ldf.to_csv(outdir / "legs.csv", index=False)
    with open(outdir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    _print_report(spot, chain, cfg, summary, bt.skipped)
    return summary


def _print_report(spot, chain, cfg, summary, skipped) -> None:
    line = "=" * 60
    print(line)
    print("  IRON FLY BACKTEST REPORT  (Nifty weekly)")
    print(line)
    print(f"  Source     : {cfg['data']['source']}")
    print(f"  Spot bars  : {len(spot)}  ({spot.index[0]} -> {spot.index[-1]})")
    print(f"  Expiries   : {len(chain.expiries)}")
    print(f"  Wing width : {cfg['strategy']['wing_width']}   "
          f"roll(trigger/step): {cfg['strategy']['roll_trigger']}/"
          f"{cfg['strategy']['roll_step']}   adjust: {cfg['strategy']['adjust']}")
    print(line)
    for k, v in summary.items():
        print(f"  {k:22s}: {v}")
    print(line)
    if skipped:
        print(f"  Skipped {len(skipped)} cycle(s); first few:")
        for row in skipped[:5]:
            print(f"    {row[0].date()} exp {row[1].date()}: {row[2]}")
        print(line)


def main() -> None:
    p = argparse.ArgumentParser(description="Iron fly backtester (Nifty weekly)")
    p.add_argument("--config", default="config_ironfly.yaml")
    p.add_argument("--source", choices=["synthetic", "csv"])
    p.add_argument("--spot", help="spot OHLCV CSV (implies --source csv)")
    p.add_argument("--options", help="option chain CSV (implies --source csv)")
    p.add_argument("--outdir", default="results_ironfly")
    args = p.parse_args()

    cfg = _apply_overrides(load_config(args.config), args)
    run(cfg, Path(args.outdir))


if __name__ == "__main__":
    main()

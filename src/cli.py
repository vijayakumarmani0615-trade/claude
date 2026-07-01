"""Command-line entry point: load config, run backtest, print + save results.

Usage:
    python -m src.cli --config config.yaml
    python -m src.cli --config config.yaml --source csv --csv data/nifty_15m.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .data import loader
from .backtest.engine import Backtester, trades_to_frame
from .backtest import metrics
from .strategy.ema_pullback import EmaPullbackStrategy


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _apply_overrides(cfg: dict, args) -> dict:
    if args.source:
        cfg["data"]["source"] = args.source
    if args.csv:
        cfg["data"]["source"] = "csv"
        cfg["data"]["csv_path"] = args.csv
    if args.symbol:
        cfg["data"]["symbol"] = args.symbol
    return cfg


def _build_strategy(name: str, cfg: dict, df):
    if name == "sr_reversal":
        return None  # Backtester builds its default (LevelBook + SRReversalStrategy)
    if name == "ema_pullback":
        return EmaPullbackStrategy(cfg, df)
    raise ValueError(f"Unknown strategy: {name!r}")


def run(cfg: dict, outdir: Path, strategy_name: str = "sr_reversal") -> dict:
    df = loader.load(cfg)
    strategy = _build_strategy(strategy_name, cfg, df)
    bt = Backtester(df, cfg, strategy=strategy)
    trades = bt.run()

    summary = metrics.compute(trades, bt.capital0)
    breakdown = metrics.by_setup(trades)
    tdf = trades_to_frame(trades)

    outdir.mkdir(parents=True, exist_ok=True)
    if not tdf.empty:
        tdf.to_csv(outdir / "trades.csv", index=False)
    with open(outdir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    _print_report(df, cfg, summary, breakdown, strategy_name)
    return summary


def _print_report(df, cfg, summary, breakdown, strategy_name: str) -> None:
    line = "=" * 60
    print(line)
    print(f"  {strategy_name.upper()} BACKTEST REPORT")
    print(line)
    print(f"  Source     : {cfg['data']['source']}  ({cfg['data'].get('symbol','')})")
    print(f"  Bars       : {len(df)}  ({df.index[0]}  ->  {df.index[-1]})")
    if strategy_name == "sr_reversal":
        print(f"  Setups     : reversal={cfg['strategy']['setups']['reversal']}  "
              f"false_break={cfg['strategy']['setups']['false_break']}")
    print(line)
    for k, v in summary.items():
        print(f"  {k:22s}: {v}")
    print(line)
    if not breakdown.empty:
        print("  BREAKDOWN BY SETUP")
        print(breakdown.to_string(index=False))
        print(line)


def main() -> None:
    p = argparse.ArgumentParser(description="Strategy backtester (Indian indices)")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--strategy", choices=["sr_reversal", "ema_pullback"], default="sr_reversal")
    p.add_argument("--source", choices=["synthetic", "csv", "yfinance"])
    p.add_argument("--csv")
    p.add_argument("--symbol")
    p.add_argument("--outdir", default="results")
    args = p.parse_args()

    cfg = _apply_overrides(load_config(args.config), args)
    run(cfg, Path(args.outdir), strategy_name=args.strategy)


if __name__ == "__main__":
    main()

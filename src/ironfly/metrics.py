"""Performance metrics for a list of iron fly cycles."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Cycle


def compute(cycles: list[Cycle], starting_capital: float) -> dict:
    if not cycles:
        return {"cycles": 0, "note": "No cycles were traded."}

    pnl = np.array([c.pnl for c in cycles], dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    equity = starting_capital + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min())

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    pf = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

    net = float(pnl.sum())
    rolls = np.array([c.rolls_ce + c.rolls_pe for c in cycles])
    brokerage = float(sum(c.brokerage for c in cycles))

    return {
        "cycles": len(cycles),
        "net_pnl": round(net, 2),
        "return_pct": round(net / starting_capital * 100, 2),
        "win_rate_pct": round(len(wins) / len(cycles) * 100, 2),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 2),
        "avg_loss": round(float(losses.mean()) if len(losses) else 0.0, 2),
        "best": round(float(pnl.max()), 2),
        "worst": round(float(pnl.min()), 2),
        "profit_factor": round(pf, 2) if np.isfinite(pf) else "inf",
        "expectancy_per_cycle": round(net / len(cycles), 2),
        "avg_rolls_per_cycle": round(float(rolls.mean()), 2),
        "total_brokerage": round(brokerage, 2),
        "max_drawdown": round(max_dd, 2),
        "final_equity": round(float(equity[-1]), 2),
    }


def cycles_to_frame(cycles: list[Cycle]) -> pd.DataFrame:
    if not cycles:
        return pd.DataFrame()
    return pd.DataFrame([{
        "entry_time": c.entry_time, "expiry": c.expiry.date(), "atm": c.k0,
        "entry_credit": c.entry_credit, "rolls_ce": c.rolls_ce,
        "rolls_pe": c.rolls_pe, "legs": c.legs_count,
        "brokerage": c.brokerage, "pnl": c.pnl,
    } for c in cycles])


def legs_to_frame(cycles: list[Cycle]) -> pd.DataFrame:
    rows = []
    for c in cycles:
        for l in c.legs:
            rows.append({
                "expiry": c.expiry.date(), "opt_type": l.opt_type,
                "strike": l.strike, "side": l.side, "qty": l.qty,
                "entry_time": l.entry_time, "entry_price": l.entry_price,
                "exit_time": l.exit_time, "exit_price": l.exit_price,
                "reason": l.exit_reason, "pnl": round(l.pnl(), 2),
            })
    return pd.DataFrame(rows)

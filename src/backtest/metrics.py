"""Performance metrics from a list of trades."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Trade


def compute(trades: list[Trade], starting_capital: float) -> dict:
    if not trades:
        return {"trades": 0, "note": "No trades were generated."}

    pnl = np.array([t.pnl for t in trades], dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    equity = starting_capital + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    max_dd = float(drawdown.min())
    max_dd_pct = float((drawdown / peak).min() * 100)

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

    r = np.array([t.r_multiple for t in trades], dtype=float)

    # Per-trade Sharpe-like ratio (not annualized; a comparability aid).
    sharpe = float(pnl.mean() / pnl.std()) if pnl.std() > 0 else 0.0

    net = float(pnl.sum())
    max_streak, worst_streak_loss = _worst_losing_streak(pnl)
    return {
        "trades": len(trades),
        "net_pnl": round(net, 2),
        "return_pct": round(net / starting_capital * 100, 2),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 2),
        "avg_loss": round(float(losses.mean()) if len(losses) else 0.0, 2),
        "worst_trade": round(float(pnl.min()), 2),
        "profit_factor": round(profit_factor, 2) if np.isfinite(profit_factor) else "inf",
        "expectancy_per_trade": round(net / len(trades), 2),
        "avg_r": round(float(r.mean()), 3),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_losing_streak": max_streak,
        "worst_streak_loss": round(worst_streak_loss, 2),
        "sharpe_per_trade": round(sharpe, 3),
        "final_equity": round(float(equity[-1]), 2),
    }


def _worst_losing_streak(pnl: np.ndarray) -> tuple[int, float]:
    """Longest run of consecutive losing trades, and the cumulative loss
    over that specific run (the "worst bad patch" you'd need to sit through).
    """
    best_len, best_loss = 0, 0.0
    cur_len, cur_loss = 0, 0.0
    for p in pnl:
        if p < 0:
            cur_len += 1
            cur_loss += p
        else:
            if cur_len > best_len:
                best_len, best_loss = cur_len, cur_loss
            cur_len, cur_loss = 0, 0.0
    if cur_len > best_len:
        best_len, best_loss = cur_len, cur_loss
    return best_len, best_loss


def by_setup(trades: list[Trade]) -> pd.DataFrame:
    """Break performance down by setup and side."""
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([{"setup": t.setup, "side": t.side, "pnl": t.pnl} for t in trades])
    g = df.groupby(["setup", "side"])["pnl"].agg(
        trades="count", net_pnl="sum",
        win_rate=lambda s: round((s > 0).mean() * 100, 1),
    )
    return g.reset_index()

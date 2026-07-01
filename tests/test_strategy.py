"""Unit tests for level detection, signal logic, and the backtest engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data import synthetic
from src.indicators.levels import LevelBook, _find_swings
from src.indicators.atr import atr
from src.strategy.sr_reversal import SRReversalStrategy, Signal
from src.backtest.engine import Backtester


def base_cfg() -> dict:
    return {
        "data": {"source": "synthetic", "square_off": "15:15", "intraday": True,
                 "symbol": "^NSEI", "timeframe": "15m"},
        "levels": {"method": "swing", "swing_left": 2, "swing_right": 2,
                   "lookback_bars": 100, "zone_pct": 0.0015, "touch_pct": 0.0015,
                   "max_levels": 8},
        "strategy": {"setups": {"reversal": True, "false_break": True},
                     "break_buffer_pct": 0.0010, "require_close_confirm": True,
                     "require_rejection_wick": False},
        "risk": {"capital": 1_000_000, "risk_per_trade_pct": 1.0,
                 "sl_method": "structure", "sl_buffer_pct": 0.001, "atr_period": 14,
                 "atr_mult": 1.5, "sl_fixed_points": 30, "target_method": "rr",
                 "rr_multiple": 1.5, "target_fixed_points": 45,
                 "max_trades_per_day": 3, "one_position_at_a_time": True},
        "costs": {"slippage_pct": 0.0002, "brokerage_per_trade": 40},
        "backtest": {"entry": "next_open", "sl_priority": True},
    }


def test_find_swings_detects_obvious_pivot():
    # A clear peak at index 3 and trough at index 7.
    high = np.array([10, 11, 12, 20, 12, 11, 10, 9, 10, 11, 12], dtype=float)
    low = np.array([9, 10, 11, 12, 11, 10, 9, 2, 9, 10, 11], dtype=float)
    sh, sl = _find_swings(high, low, left=2, right=2)
    assert 3 in sh
    assert 7 in sl


def test_levels_no_lookahead():
    df = synthetic.generate(days=5, seed=1)
    book = LevelBook(df, base_cfg())
    # Every active level at bar i must have become known at or before bar i.
    for i in range(len(df)):
        sup, res = book.active(i)
        for z in sup + res:
            assert z.formed_at <= i


def test_atr_positive_and_finite():
    df = synthetic.generate(days=10, seed=2)
    a = atr(df, 14).dropna()
    assert (a > 0).all()
    assert np.isfinite(a).all()


def _make_reversal_short_df():
    """Craft bars where a resistance forms, then price rejects it -> short."""
    idx = pd.date_range("2024-01-02 09:15", periods=12, freq="15min")
    # Build a swing high at bar 3 (peak 105), then a later bar rejecting ~105.
    o = [100, 101, 103, 104, 102, 100, 99, 100, 102, 104, 104.6, 104]
    h = [101, 102, 104, 105, 103, 101, 100, 101, 103, 105, 105.0, 104.5]
    l = [99, 100, 102, 103, 101, 99, 98, 99, 101, 103, 103.5, 103]
    c = [101, 102, 104, 104, 102, 100, 99, 100, 103, 104, 103.6, 103.2]
    v = [1000] * 12
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)


def test_reversal_short_signal_fires_at_resistance():
    cfg = base_cfg()
    cfg["levels"].update(swing_left=1, swing_right=1, method="swing")
    df = _make_reversal_short_df()
    book = LevelBook(df, cfg)
    strat = SRReversalStrategy(cfg, book)

    fired = []
    for i in range(len(df)):
        row = df.iloc[i]
        sig = strat.evaluate(i, _row(row))
        if sig:
            fired.append(sig)
    # At least one short rejection at the ~105 resistance should appear.
    assert any(s.side == "short" for s in fired)


def test_backtester_runs_and_respects_daily_cap():
    cfg = base_cfg()
    cfg["risk"]["max_trades_per_day"] = 1
    df = synthetic.generate(days=20, seed=7)
    bt = Backtester(df, cfg)
    trades = bt.run()
    # Group by calendar day; never exceed the cap.
    by_day: dict = {}
    for t in trades:
        d = t.entry_time.normalize()
        by_day[d] = by_day.get(d, 0) + 1
    assert all(count <= 1 for count in by_day.values())


def test_backtester_stops_are_on_correct_side():
    cfg = base_cfg()
    df = synthetic.generate(days=30, seed=3)
    trades = Backtester(df, cfg).run()
    for t in trades:
        if t.side == "long":
            assert t.stop < t.entry
        else:
            assert t.stop > t.entry


def test_intraday_square_off_closes_positions():
    cfg = base_cfg()
    df = synthetic.generate(days=15, seed=9)
    trades = Backtester(df, cfg).run()
    # No trade should be held past the square-off time on a different day.
    for t in trades:
        assert t.exit_time.normalize() == t.entry_time.normalize(), (
            "intraday trade leaked across days"
        )


class _row:
    def __init__(self, s):
        self.open = s["open"]; self.high = s["high"]
        self.low = s["low"]; self.close = s["close"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

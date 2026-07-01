"""Unit tests for the EMA(8) trend-pullback strategy and its backtest wiring."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data import synthetic
from src.indicators.ema import ema
from src.strategy.ema_pullback import EmaPullbackStrategy
from src.backtest.engine import Backtester


def base_cfg() -> dict:
    return {
        "data": {"source": "synthetic", "square_off": "15:15", "intraday": True,
                 "symbol": "^NSEI", "timeframe": "15m"},
        "strategy": {
            "ema_fast": 8, "ema_slow": 50, "trend_slope_bars": 10,
            "touch_pct": 0.0015, "require_extension": True,
            "extension_pct": 0.0015, "extension_lookback_bars": 6,
        },
        "risk": {
            "capital": 200_000, "sizing_method": "fixed_lot", "lot_size": 75,
            "lots": 1, "sl_method": "structure", "sl_buffer_pct": 0.001,
            "atr_period": 14, "atr_mult": 1.5, "sl_fixed_points": 40,
            "target_method": "rr", "rr_multiple": 1.5, "target_fixed_points": 100,
            "max_trades_per_day": 1, "one_position_at_a_time": True,
        },
        "costs": {"slippage_pct": 0.0002, "brokerage_per_trade": 40},
        "backtest": {"entry": "next_open", "sl_priority": True},
    }


class _row:
    def __init__(self, o, h, l, c):
        self.open, self.high, self.low, self.close = o, h, l, c


def _make_uptrend_pullback_df():
    """Steady rise (so EMA8 > EMA50 and rising), price runs away from EMA8,
    then a bar dips into EMA8 and closes back above it, green."""
    n = 70
    base = np.linspace(100, 140, n)
    close = base.copy()
    idx = pd.date_range("2024-01-02 09:15", periods=n, freq="15min")
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.3
    low = np.minimum(open_, close) - 0.3

    # Craft the final bar as an explicit pullback-and-reject. ema_fast at the
    # signal bar itself blends in that bar's own close (alpha = 2/(8+1)), so
    # derive it forward from ema_prev rather than assuming it equals ema_prev.
    ema_prev = ema(pd.Series(close[: n - 1]), 8).iloc[-1]
    alpha = 2 / (8 + 1)
    c_last = ema_prev + 3.0                       # still rising, well above ema_prev
    ema_last = alpha * c_last + (1 - alpha) * ema_prev
    o_last = ema_last - 0.3                       # open below ema_last -> body closes green
    l_last = ema_last - 0.1                       # low dips into ema_last (the "touch")
    h_last = c_last + 0.1

    open_[-1] = o_last
    close[-1] = c_last
    low[-1] = l_last
    high[-1] = h_last

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": [1000] * n},
        index=idx,
    )


def test_trend_detects_uptrend_on_rising_series():
    cfg = base_cfg()
    df = _make_uptrend_pullback_df()
    strat = EmaPullbackStrategy(cfg, df)
    assert strat._trend(len(df) - 1) == "up"


def test_ema_pullback_long_signal_fires_on_touch_and_reject():
    cfg = base_cfg()
    df = _make_uptrend_pullback_df()
    strat = EmaPullbackStrategy(cfg, df)
    i = len(df) - 1
    row = df.iloc[i]
    sig = strat.evaluate(i, _row(row.open, row.high, row.low, row.close))
    assert sig is not None
    assert sig.side == "long"
    assert sig.setup == "ema_pullback"


def test_no_signal_without_trend():
    cfg = base_cfg()
    df = synthetic.generate(days=1, seed=5)  # too short for ema_slow(50) to warm up
    strat = EmaPullbackStrategy(cfg, df)
    for i in range(len(df)):
        row = df.iloc[i]
        sig = strat.evaluate(i, _row(row.open, row.high, row.low, row.close))
        assert sig is None  # EMAs still NaN / not enough history


def test_fixed_lot_sizing_ignores_stop_distance():
    cfg = base_cfg()
    df = synthetic.generate(days=30, seed=11)
    strat = EmaPullbackStrategy(cfg, df)
    bt = Backtester(df, cfg, strategy=strat)
    assert bt._position_size(100.0, 90.0) == 75
    assert bt._position_size(100.0, 50.0) == 75  # unchanged despite wider stop


def test_backtester_runs_with_injected_ema_strategy_and_respects_daily_cap():
    cfg = base_cfg()
    df = synthetic.generate(days=40, seed=13)
    strat = EmaPullbackStrategy(cfg, df)
    trades = Backtester(df, cfg, strategy=strat).run()

    by_day: dict = {}
    for t in trades:
        d = t.entry_time.normalize()
        by_day[d] = by_day.get(d, 0) + 1
    assert all(count <= 1 for count in by_day.values())
    for t in trades:
        assert t.qty == 75
        if t.side == "long":
            assert t.stop < t.entry
        else:
            assert t.stop > t.entry


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

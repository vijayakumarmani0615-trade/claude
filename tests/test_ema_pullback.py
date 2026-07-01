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
            "touch_pct": 0.0, "require_extension": True,
            "extension_pct": 0.0015, "extension_lookback_bars": 6,
        },
        "risk": {
            "capital": 200_000, "sizing_method": "fixed_lot", "lot_size": 75,
            "lots": 1, "sl_method": "fixed", "sl_buffer_pct": 0.001,
            "atr_period": 14, "atr_mult": 1.5, "sl_fixed_points": 20,
            "target_method": "fixed", "rr_multiple": 1.5, "target_fixed_points": 40,
            "max_trades_per_day": 1, "one_position_at_a_time": True,
        },
        "costs": {"slippage_pct": 0.0002, "brokerage_per_trade": 40},
        "backtest": {"entry": "signal_level", "sl_priority": True},
    }


class _row:
    def __init__(self, o, h, l, c):
        self.open, self.high, self.low, self.close = o, h, l, c


def _make_uptrend_pullback_df(last_bar_close_below_ema: bool = False):
    """Steady rise (so EMA8 > EMA50 and rising), price runs away from EMA8,
    then the final bar dips into the *previous* bar's EMA8. The entry no
    longer waits for a close/candle confirmation, so the final bar's own
    close can even end up on the wrong side of the level (parametrized via
    `last_bar_close_below_ema`) and the touch should still fire.
    """
    n = 70
    base = np.linspace(100, 140, n)
    close = base.copy()
    idx = pd.date_range("2024-01-02 09:15", periods=n, freq="15min")
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.3
    low = np.minimum(open_, close) - 0.3

    # The watched level for the final bar is ema_fast as of the PRIOR bar
    # (n-2), since that's what evaluate() uses to avoid lookahead.
    ema_prev = ema(pd.Series(close[: n - 1]), 8).iloc[-1]
    if last_bar_close_below_ema:
        o_last, c_last = ema_prev + 1.0, ema_prev - 2.0  # red candle, closes under ema_prev
    else:
        o_last, c_last = ema_prev - 0.3, ema_prev + 3.0  # green candle, closes over ema_prev
    l_last = ema_prev - 0.1                              # low dips into ema_prev (the "touch")
    h_last = max(o_last, c_last) + 0.1

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
    assert strat._trend(len(df) - 2) == "up"  # trend is read as of bar i-1


def test_ema_pullback_long_signal_fires_on_touch_alone():
    cfg = base_cfg()
    df = _make_uptrend_pullback_df()
    strat = EmaPullbackStrategy(cfg, df)
    i = len(df) - 1
    row = df.iloc[i]
    sig = strat.evaluate(i, _row(row.open, row.high, row.low, row.close))
    assert sig is not None
    assert sig.side == "long"
    assert sig.setup == "ema_pullback"


def test_ema_pullback_fires_even_if_bar_closes_against_the_trend():
    """No confirmation wait: a touch fires even if the bar closes red."""
    cfg = base_cfg()
    df = _make_uptrend_pullback_df(last_bar_close_below_ema=True)
    strat = EmaPullbackStrategy(cfg, df)
    i = len(df) - 1
    row = df.iloc[i]
    sig = strat.evaluate(i, _row(row.open, row.high, row.low, row.close))
    assert sig is not None


def test_near_miss_does_not_fire_with_zero_touch_tolerance():
    """Regression for a real bug: at a Nifty-like price level (~26,000), a
    0.15% touch_pct is a ~35-40pt band -- comparable to a whole bar's range
    -- so a bar whose low stayed well above the EMA8 line still counted as
    a "touch". With touch_pct=0 (the corrected default), only a literal
    cross of the line should fire.
    """
    n = 70
    price_level = 26000.0
    base = np.linspace(price_level, price_level + 200, n)  # gentle uptrend at realistic scale
    close = base.copy()
    idx = pd.date_range("2024-01-02 09:15", periods=n, freq="15min")
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 5
    low = np.minimum(open_, close) - 5

    ema_prev = ema(pd.Series(close[: n - 1]), 8).iloc[-1]
    # Old 0.15% tolerance at this price level is ~39 points -- craft a bar
    # whose low sits 25 points ABOVE the ema line (a real near-miss like the
    # Dec-1 example): well inside the old tolerance, but not a real touch.
    o_last, c_last = ema_prev + 30.0, ema_prev + 35.0
    l_last = ema_prev + 25.0   # 25pt above the line -- never actually touches it
    h_last = c_last + 5.0

    open_[-1], close[-1], low[-1], high[-1] = o_last, c_last, l_last, h_last
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": [1000] * n},
        index=idx,
    )

    cfg = base_cfg()
    cfg["strategy"]["require_extension"] = False  # isolate the touch check itself
    strat_fixed = EmaPullbackStrategy(cfg, df)
    i = len(df) - 1
    row = df.iloc[i]
    sig = strat_fixed.evaluate(i, _row(row.open, row.high, row.low, row.close))
    assert sig is None, "a bar that never reached the EMA8 line should not signal"

    # Confirm this WOULD have fired under the old loose 0.15% tolerance,
    # proving this test actually exercises the bug that was fixed.
    cfg_loose = base_cfg()
    cfg_loose["strategy"]["require_extension"] = False
    cfg_loose["strategy"]["touch_pct"] = 0.0015
    strat_loose = EmaPullbackStrategy(cfg_loose, df)
    sig_loose = strat_loose.evaluate(i, _row(row.open, row.high, row.low, row.close))
    assert sig_loose is not None, "sanity check: old tolerance should have fired here"


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

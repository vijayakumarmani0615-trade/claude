"""Control experiment: is the EMA8 doing any specific work, or does ANY
"shallow pullback near a recent price anchor in a trending day" show the
same pattern the touch_buffer sweep found?

Keeps everything about EmaPullbackStrategy identical -- the EMA8/EMA50
trend filter, the extension-before-pullback filter, the buffer-tolerance
entry mechanism, the 20pt/40pt exits -- except ONE thing: the reference
"level" a bar's low/high is checked against is no longer ema_fast. It's the
close price from `ema_fast` bars ago (8 bars) -- a plain lag with zero
smoothing, carrying no claim to being a meaningful technical level at all.
If this control shows the same "profitability climbs smoothly with buffer
size" pattern the real EMA8 did, that's strong evidence the EMA8 isn't
what's driving the touch_buffer result -- almost any nearby-ish recent
price would do.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import yaml

from src.data import loader
from src.backtest.engine import Backtester
from src.backtest import metrics
from src.strategy.ema_pullback import EmaPullbackStrategy
from src.strategy.signal import Signal

BUFFERS = [0, 2, 3, 5, 7, 10, 15, 20, 25, 30, 35, 40]


class LagCloseControlStrategy(EmaPullbackStrategy):
    """Same as EmaPullbackStrategy, except the touch level is the close
    price from `ema_fast_n` bars ago (a meaningless plain lag), not ema_fast.
    Trend filter and extension filter still use the real EMA8/EMA50 -- only
    the touched reference level changes.
    """

    def __init__(self, cfg, df):
        super().__init__(cfg, df)
        # Plain lag reference: close price `ema_fast_n` bars before each bar.
        self.lag_level = self.closes.copy()
        self.lag_level[self.ema_fast_n:] = self.closes[:-self.ema_fast_n]
        self.lag_level[:self.ema_fast_n] = np.nan

    def evaluate(self, i, bar):
        if i < 1:
            return None
        direction = self._trend(i - 1)
        if direction is None:
            return None

        level = self.lag_level[i - 1]
        if np.isnan(level) or level <= 0:
            return None

        o, h, l, c = bar.open, bar.high, bar.low, bar.close
        tol = level * self.touch_pct + self.touch_buffer_points

        if direction == "up":
            touched = l <= level + tol
            if touched and self._was_extended(i - 1, "up"):
                return Signal(i, "long", "lag_control", float(level), c, h, l)
        else:
            touched = h >= level - tol
            if touched and self._was_extended(i - 1, "down"):
                return Signal(i, "short", "lag_control", float(level), c, h, l)
        return None


def base_cfg():
    with open("config_ema_pullback.yaml") as f:
        return yaml.safe_load(f)


def run_one(df, cfg, strategy_cls):
    strat = strategy_cls(cfg, df)
    bt = Backtester(df, cfg, strategy=strat)
    trades = bt.run()
    return metrics.compute(trades, bt.capital0)


def main():
    cfg = base_cfg()
    df = loader.load(cfg)

    print(f"{'buffer_pts':>11}{'':>4}{'EMA8: trades':>14}{'win%':>7}{'PF':>7}{'net(L)':>9}"
          f"{'  |  ':>5}{'lag-control: trades':>20}{'win%':>7}{'PF':>7}{'net(L)':>9}")
    for buf in BUFFERS:
        c_ema = copy.deepcopy(cfg)
        c_ema["strategy"]["touch_buffer_points"] = buf
        m_ema = run_one(df, c_ema, EmaPullbackStrategy)

        c_lag = copy.deepcopy(cfg)
        c_lag["strategy"]["touch_buffer_points"] = buf
        m_lag = run_one(df, c_lag, LagCloseControlStrategy)

        print(f"{buf:>11}{'':>4}{m_ema['trades']:>14}{m_ema['win_rate_pct']:>7}"
              f"{str(m_ema['profit_factor']):>7}{m_ema['net_pnl']/1e5:>9.2f}"
              f"{'  |  ':>5}{m_lag['trades']:>20}{m_lag['win_rate_pct']:>7}"
              f"{str(m_lag['profit_factor']):>7}{m_lag['net_pnl']/1e5:>9.2f}")


if __name__ == "__main__":
    main()

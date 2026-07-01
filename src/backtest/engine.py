"""Event-driven backtester for the S/R rejection strategy.

Design goals: transparency and no lookahead. We walk bar by bar. On a signal
(when flat and within daily limits) we compute entry, stop and target, then
enter at the next bar's open (default) to avoid filling on information from the
signal bar's close. Open trades are then managed intrabar against subsequent
bars' highs/lows, plus a hard intraday square-off.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from ..indicators.atr import atr
from ..indicators.levels import LevelBook
from ..strategy.sr_reversal import SRReversalStrategy
from ..strategy.signal import Signal


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: str
    setup: str
    level: float
    entry: float
    stop: float
    target: float
    exit: float
    qty: int
    reason: str          # target | stop | square_off | eod
    pnl: float           # net of costs
    r_multiple: float    # realized reward-in-risk-units


class Backtester:
    def __init__(self, df: pd.DataFrame, cfg: dict, strategy=None):
        """`strategy` lets a caller plug in any strategy exposing
        `evaluate(i, bar) -> Signal | None`. Defaults to the S/R reversal
        strategy (built from `cfg["levels"]`/`cfg["strategy"]`) for backward
        compatibility with existing callers/tests.
        """
        self.df = df
        self.cfg = cfg
        if strategy is None:
            self.levels = LevelBook(df, cfg)
            strategy = SRReversalStrategy(cfg, self.levels)
        self.strategy = strategy
        self.atr = atr(df, int(cfg["risk"]["atr_period"]))

        r = cfg["risk"]
        self.capital0 = float(r["capital"])
        self.sizing_method = r.get("sizing_method", "risk_pct")
        self.risk_pct = float(r.get("risk_per_trade_pct", 0) or 0) / 100.0
        self.lot_size = int(r.get("lot_size", 1))
        self.lots = int(r.get("lots", 1))
        self.sl_method = r["sl_method"]
        self.sl_buffer = float(r["sl_buffer_pct"])
        self.atr_mult = float(r["atr_mult"])
        self.sl_fixed = float(r["sl_fixed_points"])
        self.target_method = r["target_method"]
        self.rr = float(r["rr_multiple"])
        self.target_fixed = float(r["target_fixed_points"])
        self.max_trades = int(r["max_trades_per_day"])
        self.one_at_a_time = bool(r["one_position_at_a_time"])

        c = cfg["costs"]
        self.slippage = float(c["slippage_pct"])
        self.brokerage = float(c["brokerage_per_trade"])
        # Extra flat points of adverse slippage applied only to `signal_level`
        # (touch-fill) entries, on top of `slippage_pct` -- for stress-testing
        # how much a real limit order at the level might slip vs. the clean
        # fill the backtest otherwise assumes.
        self.entry_touch_extra_slippage = float(c.get("entry_touch_extra_slippage_points", 0))

        b = cfg["backtest"]
        self.entry_mode = b["entry"]
        self.sl_priority = bool(b["sl_priority"])

        d = cfg["data"]
        self.intraday = bool(d["intraday"])
        self.square_off = pd.to_datetime(d["square_off"]).time()
        self.square_off_mask = self._compute_square_off_mask(df)

        self.trades: list[Trade] = []

    def _compute_square_off_mask(self, df: pd.DataFrame):
        """True where a position must be forced flat: at/after the configured
        cutoff time, OR on the last bar of the trading day -- whichever comes
        first. The time check alone only works when some bar's start time
        lands exactly on the cutoff (true for 15-min bars with a 15:15
        cutoff); coarser bars (e.g. 75-min: 09:15/10:30/11:45/13:00/14:15)
        never hit it, so without the last-bar fallback positions would never
        get squared off and could carry across days.
        """
        times = df.index
        by_time = times.time >= self.square_off
        day = times.normalize()
        is_last_of_day = np.append(day[:-1].to_numpy() != day[1:].to_numpy(), True)
        return by_time | is_last_of_day

    # -- risk math -----------------------------------------------------------
    def _stop_distance(self, sig: Signal, i: int) -> float:
        if self.sl_method == "atr":
            a = self.atr.iloc[i]
            dist = self.atr_mult * (a if pd.notna(a) else 0.0)
        elif self.sl_method == "fixed":
            dist = self.sl_fixed
        else:  # structure: beyond the signal bar's extreme + buffer
            if sig.side == "long":
                dist = sig.signal_close - sig.signal_low
            else:
                dist = sig.signal_high - sig.signal_close
            dist += sig.signal_close * self.sl_buffer
        return max(dist, 1e-6)

    def _levels_for(self, sig: Signal, entry: float, i: int) -> tuple[float, float, float]:
        dist = self._stop_distance(sig, i)
        if sig.side == "long":
            stop = entry - dist
            if self.target_method == "fixed":
                target = entry + self.target_fixed
            else:  # rr (level-based target falls back to rr for simplicity)
                target = entry + self.rr * dist
        else:
            stop = entry + dist
            if self.target_method == "fixed":
                target = entry - self.target_fixed
            else:
                target = entry - self.rr * dist
        return stop, target, dist

    def _position_size(self, entry: float, stop: float) -> int:
        if self.sizing_method == "fixed_lot":
            return self.lot_size * self.lots
        risk_amount = self.capital0 * self.risk_pct
        per_unit = abs(entry - stop)
        if per_unit <= 0:
            return 0
        return max(int(risk_amount // per_unit), 0)

    # -- main loop -----------------------------------------------------------
    def run(self) -> list[Trade]:
        df = self.df
        n = len(df)
        times = df.index
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()

        pending: Signal | None = None
        in_pos = False
        pos = {}
        trades_today = 0
        cur_day = None

        for i in range(n):
            t = times[i]
            day = t.normalize()
            if day != cur_day:
                cur_day = day
                trades_today = 0

            # 1) Manage an open position against THIS bar.
            if in_pos:
                exit_price, reason = self._check_exit(pos, i, highs, lows, closes, t)
                if exit_price is not None:
                    self._close(pos, exit_price, t, reason)
                    in_pos = False
                    pos = {}

            # 2) Fill a pending entry at this bar's open.
            if not in_pos and pending is not None:
                entry_raw = opens[i]
                slip = entry_raw * self.slippage
                entry = entry_raw + slip if pending.side == "long" else entry_raw - slip
                stop, target, dist = self._levels_for(pending, entry, i)
                qty = self._position_size(entry, stop)
                if qty > 0 and self._valid(pending, entry, stop):
                    pos = {
                        "sig": pending, "entry": entry, "stop": stop,
                        "target": target, "qty": qty, "dist": dist,
                        "entry_time": t,
                    }
                    in_pos = True
                    trades_today += 1
                pending = None

            # 3) Look for a new signal on this bar (if flat & under the cap).
            can_trade = (not in_pos or not self.one_at_a_time) and trades_today < self.max_trades
            if can_trade and pending is None and not (self.intraday and self.square_off_mask[i]):
                bar = _Bar(opens[i], highs[i], lows[i], closes[i])
                sig = self.strategy.evaluate(i, bar)
                if sig is not None:
                    if self.entry_mode == "signal_close":
                        # Fill immediately at this close (less realistic).
                        entry = closes[i]
                        stop, target, dist = self._levels_for(sig, entry, i)
                        qty = self._position_size(entry, stop)
                        if qty > 0 and self._valid(sig, entry, stop) and not in_pos:
                            pos = {
                                "sig": sig, "entry": entry, "stop": stop,
                                "target": target, "qty": qty, "dist": dist,
                                "entry_time": t,
                            }
                            in_pos = True
                            trades_today += 1
                    elif self.entry_mode == "signal_level":
                        # Fill the moment the bar's range touches the level
                        # (e.g. a resting limit order) -- no confirmation wait.
                        entry_raw = sig.level
                        slip = entry_raw * self.slippage + self.entry_touch_extra_slippage
                        entry = entry_raw + slip if sig.side == "long" else entry_raw - slip
                        stop, target, dist = self._levels_for(sig, entry, i)
                        qty = self._position_size(entry, stop)
                        if qty > 0 and self._valid(sig, entry, stop) and not in_pos:
                            pos = {
                                "sig": sig, "entry": entry, "stop": stop,
                                "target": target, "qty": qty, "dist": dist,
                                "entry_time": t,
                            }
                            in_pos = True
                            trades_today += 1
                    else:
                        pending = sig  # fill next bar's open

            # 4) Hard intraday square-off at/after the cutoff time.
            if in_pos and self.intraday and self.square_off_mask[i]:
                self._close(pos, closes[i], t, "square_off")
                in_pos = False
                pos = {}
                pending = None

        # Close anything still open at the very end.
        if in_pos:
            self._close(pos, closes[-1], times[-1], "eod")

        return self.trades

    # -- helpers -------------------------------------------------------------
    def _valid(self, sig: Signal, entry: float, stop: float) -> bool:
        # Guard against degenerate geometry (stop on the wrong side of entry).
        if sig.side == "long":
            return stop < entry
        return stop > entry


    def _check_exit(self, pos, i, highs, lows, closes, t):
        side = pos["sig"].side
        stop, target = pos["stop"], pos["target"]
        hi, lo = highs[i], lows[i]

        hit_stop = lo <= stop if side == "long" else hi >= stop
        hit_tgt = hi >= target if side == "long" else lo <= target

        if hit_stop and hit_tgt:
            # Ambiguous bar: honor configured priority (default: stop first).
            return (stop, "stop") if self.sl_priority else (target, "target")
        if hit_stop:
            return stop, "stop"
        if hit_tgt:
            return target, "target"
        return None, ""

    def _close(self, pos, exit_price, t, reason):
        sig = pos["sig"]
        entry, qty, dist = pos["entry"], pos["qty"], pos["dist"]
        # Apply exit slippage against us.
        slip = exit_price * self.slippage
        if sig.side == "long":
            fill = exit_price - slip
            gross = (fill - entry) * qty
        else:
            fill = exit_price + slip
            gross = (entry - fill) * qty
        pnl = gross - self.brokerage
        r_mult = (pnl / (dist * qty)) if dist * qty else 0.0

        self.trades.append(
            Trade(
                entry_time=pos["entry_time"], exit_time=t, side=sig.side,
                setup=sig.setup, level=round(sig.level, 2), entry=round(entry, 2),
                stop=round(pos["stop"], 2), target=round(pos["target"], 2),
                exit=round(fill, 2), qty=qty, reason=reason, pnl=round(pnl, 2),
                r_multiple=round(r_mult, 3),
            )
        )


class _Bar:
    __slots__ = ("open", "high", "low", "close")

    def __init__(self, o, h, l, c):
        self.open, self.high, self.low, self.close = o, h, l, c


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([asdict(tr) for tr in trades])

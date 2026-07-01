"""Tests for the real-data ingestion path: bhavcopy converter + cycle guard."""
from __future__ import annotations

import importlib.util
import os

import pandas as pd
import pytest

from src.ironfly import data
from src.ironfly.engine import IronFlyBacktester

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_converter():
    path = os.path.join(_HERE, "scripts", "build_options_chain.py")
    spec = importlib.util.spec_from_file_location("build_options_chain", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CONV = _load_converter()


# --- bhavcopy converter ---------------------------------------------------- #
def test_classic_bhavcopy_normalize_and_filter():
    df = pd.DataFrame([
        ["OPTIDX", "NIFTY", "20-Jun-2024", 23500, "CE", 142.5, 142.5, "20-Jun-2024"],
        ["OPTIDX", "NIFTY", "20-Jun-2024", 23500, "PE", 131.0, 131.0, "20-Jun-2024"],
        ["FUTIDX", "NIFTY", "20-Jun-2024", 0, "XX", 23500, 23500, "20-Jun-2024"],
        ["OPTSTK", "RELIANCE", "20-Jun-2024", 3000, "CE", 55.0, 55.0, "20-Jun-2024"],
    ], columns=["INSTRUMENT", "SYMBOL", "EXPIRY_DT", "STRIKE_PR", "OPTION_TYP",
                "CLOSE", "SETTLE_PR", "TIMESTAMP"])
    out = CONV._normalize(df, "NIFTY")
    assert len(out) == 2                                  # futures + stock filtered out
    assert set(out["option_type"]) == {"CE", "PE"}
    assert out["datetime"].iloc[0].startswith("2024-06-20")
    assert out["expiry"].iloc[0] == pd.Timestamp("2024-06-20")


def test_udiff_iso_dates_not_daymonth_swapped():
    # The bug this guards: ISO YYYY-MM-DD must NOT be read day-first.
    df = pd.DataFrame([
        ["2024-02-07", "IDO", "NIFTY", "2024-02-15", 22000, "CE", 145.5, 145.5],
        ["2024-02-07", "STO", "RELIANCE", "2024-02-15", 3000, "PE", 10.0, 10.0],
    ], columns=["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric",
                "OptnTp", "ClsPric", "SttlmPric"])
    out = CONV._normalize(df, "NIFTY")
    assert len(out) == 1                                  # STO filtered out
    assert out["datetime"].iloc[0].startswith("2024-02-07")   # Feb 7, not Jul 2
    assert out["expiry"].iloc[0] == pd.Timestamp("2024-02-15")


def test_normalize_prefers_close_but_falls_back_to_settle():
    df = pd.DataFrame([
        ["OPTIDX", "NIFTY", "20-Jun-2024", 23500, "CE", 0.0, 99.0, "20-Jun-2024"],
    ], columns=["INSTRUMENT", "SYMBOL", "EXPIRY_DT", "STRIKE_PR", "OPTION_TYP",
                "CLOSE", "SETTLE_PR", "TIMESTAMP"])
    out = CONV._normalize(df, "NIFTY")
    assert out["close"].iloc[0] == 99.0                  # close==0 -> use settle


def test_normalize_rejects_non_bhavcopy():
    df = pd.DataFrame({"foo": [1], "bar": [2]})
    assert CONV._normalize(df, "NIFTY") is None


# --- engine weekly-cycle guard --------------------------------------------- #
def _flat_chain(expiries, strikes, timestamps, price=100.0):
    rows = []
    for e in expiries:
        for k in strikes:
            for ot in ("CE", "PE"):
                for t in timestamps:
                    rows.append((t, pd.Timestamp(e), float(k), ot, price))
    return data._build_chain(
        pd.DataFrame(rows, columns=["datetime", "expiry", "strike",
                                    "option_type", "close"]))


def test_max_cycle_days_skips_far_expiries():
    cfg = {
        "data": {"square_off": "15:15"},
        "strategy": {"strike_step": 50, "wing_width": 300, "entry_time": "09:20",
                     "entry_offset_days": 1, "adjust": False, "roll_trigger": 300,
                     "roll_step": 300, "roll_scope": "vertical",
                     "max_rolls_per_side": 3, "max_cycle_days": 10},
        "lots": {"lot_size": 75, "lots": 1}, "costs": {"slippage_pct": 0.0,
                 "brokerage_per_leg": 0},
    }
    days = pd.bdate_range("2024-01-01", periods=60)
    ts = [d + pd.Timedelta(hours=15, minutes=15) for d in days]
    spot = pd.DataFrame({"open": 22000.0, "high": 22000.0, "low": 22000.0,
                         "close": 22000.0}, index=pd.DatetimeIndex(ts, name="datetime"))
    strikes = range(21000, 23001, 50)
    # Two weeklies then a far monthly expiry.
    expiries = ["2024-01-11", "2024-01-18", "2024-03-14"]
    chain = _flat_chain(expiries, strikes, ts)

    cycles = IronFlyBacktester(spot, chain, cfg).run()
    traded = {str(c.expiry.date()) for c in cycles}
    assert "2024-01-18" in traded          # a real weekly (prev = 01-11)
    assert "2024-03-14" not in traded      # 55-day gap > max_cycle_days -> skipped

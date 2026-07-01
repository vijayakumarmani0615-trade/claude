"""Tests for the iron fly backtester."""
from __future__ import annotations

import copy

import pandas as pd
import pytest

from src.ironfly import data, metrics, pricing
from src.ironfly.engine import IronFlyBacktester
from src.ironfly.strategy import Leg, atm_strike, initial_legs, roll_side


BASE_CFG = {
    "data": {"source": "synthetic", "square_off": "15:15"},
    "strategy": {
        "strike_step": 50, "wing_width": 300, "entry_time": "09:20",
        "entry_offset_days": 1, "adjust": True, "roll_trigger": 300,
        "roll_step": 300, "roll_scope": "vertical", "max_rolls_per_side": 3,
    },
    "lots": {"lot_size": 75, "lots": 1, "capital": 1_000_000},
    "costs": {"slippage_pct": 0.01, "brokerage_per_leg": 20},
    "synthetic": {"weeks": 8, "start": "2024-01-05", "spot0": 22000,
                  "annual_vol": 0.14, "iv": 0.12, "seed": 3},
}


def cfg(**over):
    c = copy.deepcopy(BASE_CFG)
    for k, v in over.items():
        c["strategy"][k] = v
    return c


# --- pricing --------------------------------------------------------------- #
def test_bs_atm_positive_and_parity():
    call = pricing.bs_price(100, 100, 0.05, 0.2, "CE")
    put = pricing.bs_price(100, 100, 0.05, 0.2, "PE")
    assert call > 0 and put > 0
    # Put-call parity at r=0: C - P == S - K.
    assert abs((call - put) - (100 - 100)) < 1e-6


def test_bs_expiry_is_intrinsic():
    assert pricing.bs_price(110, 100, 0, 0.2, "CE") == 10
    assert pricing.intrinsic(90, 100, "PE") == 10


# --- structure math -------------------------------------------------------- #
def test_atm_rounds_to_grid():
    assert atm_strike(22013, 50) == 22000
    assert atm_strike(22030, 50) == 22050


def test_initial_legs_shape():
    legs = initial_legs(22000, 300)
    kinds = {(l.opt_type, l.side): l.strike for l in legs}
    assert kinds[("CE", "short")] == 22000
    assert kinds[("PE", "short")] == 22000
    assert kinds[("CE", "long")] == 22300
    assert kinds[("PE", "long")] == 21700


def test_roll_vertical_moves_short_and_wing():
    specs = roll_side("CE", 22000, 22300, 300, 300, "vertical")
    strikes = {s.side: s.strike for s in specs}
    assert strikes["short"] == 22300 and strikes["long"] == 22600


def test_roll_short_only_keeps_wing():
    specs = roll_side("PE", 22000, 21700, 300, 300, "short_only")
    assert len(specs) == 1 and specs[0].side == "short"
    assert specs[0].strike == 21700   # rolled down by roll_step


def test_leg_pnl_signs():
    short = Leg("CE", 100, "short", 75, None, 120, exit_price=100)
    long = Leg("CE", 100, "long", 75, None, 40, exit_price=60)
    assert short.pnl() == (120 - 100) * 75      # short profits as price falls
    assert long.pnl() == (60 - 40) * 75         # long profits as price rises
    assert Leg("CE", 100, "short", 75, None, 120).pnl() == 0.0  # open leg


# --- end to end ------------------------------------------------------------ #
def test_backtest_runs_and_reconciles():
    spot, chain = data.generate_synthetic(BASE_CFG)
    cycles = IronFlyBacktester(spot, chain, BASE_CFG).run()
    assert len(cycles) >= 5
    for c in cycles:
        assert all(not l.is_open for l in c.legs)           # everything settled
        recon = sum(l.pnl() for l in c.legs) - c.brokerage
        assert abs(recon - c.pnl) < 0.011                   # pnl reconciles (2dp round)


def test_summary_shape():
    spot, chain = data.generate_synthetic(BASE_CFG)
    cycles = IronFlyBacktester(spot, chain, BASE_CFG).run()
    s = metrics.compute(cycles, 1_000_000)
    assert s["cycles"] == len(cycles)
    assert s["wins"] + s["losses"] <= s["cycles"]


def test_adjust_off_never_rolls():
    c = cfg(adjust=False)
    spot, chain = data.generate_synthetic(c)
    cycles = IronFlyBacktester(spot, chain, c).run()
    assert cycles
    assert all(cy.rolls_ce == 0 and cy.rolls_pe == 0 for cy in cycles)
    # Static iron fly: every cycle is exactly the original 4 legs.
    assert all(cy.legs_count == 4 for cy in cycles)


def test_static_wings_cap_the_loss():
    """A static (no-roll) iron fly's loss is bounded by the wing width."""
    c = cfg(adjust=False)
    spot, chain = data.generate_synthetic(c)
    cycles = IronFlyBacktester(spot, chain, c).run()
    qty = 75
    # Worst case per side ~ wing_width*qty; allow slippage/brokerage slack.
    bound = -(300 * qty + 300 * qty + 2000)
    assert min(cy.pnl for cy in cycles) >= bound


def test_higher_trigger_rolls_less():
    few = IronFlyBacktester(*data.generate_synthetic(cfg(roll_trigger=600)),
                            cfg(roll_trigger=600)).run()
    many = IronFlyBacktester(*data.generate_synthetic(cfg(roll_trigger=150)),
                             cfg(roll_trigger=150)).run()
    rolls_few = sum(c.rolls_ce + c.rolls_pe for c in few)
    rolls_many = sum(c.rolls_ce + c.rolls_pe for c in many)
    assert rolls_many >= rolls_few


# --- chain lookup ---------------------------------------------------------- #
def test_chain_nearest_and_asof():
    spot, chain = data.generate_synthetic(BASE_CFG)
    exp = chain.expiries[1]
    near = chain.nearest_strike(exp, 22013)
    assert near % 50 == 0
    t = chain.series[(exp, near, "CE")].index[0]
    assert chain.price(exp, near, "CE", t) is not None
    assert chain.price(exp, 999999, "CE", t) is None     # unknown strike

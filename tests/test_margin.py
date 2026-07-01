"""Unit tests for the futures margin / capital-adequacy helpers."""
from __future__ import annotations

import pytest

from src.risk import margin


def test_required_margin_scales_with_price():
    low = margin.required_margin(12000, 75, 0.12)
    high = margin.required_margin(24000, 75, 0.12)
    assert high == pytest.approx(2 * low)


def test_capital_at_risk_adds_stop_loss_on_top_of_margin():
    m = margin.required_margin(20000, 75, 0.12)
    car = margin.capital_at_risk(20000, 75, 0.12, stop_points=20)
    assert car == pytest.approx(m + 20 * 75)


def test_is_safe_respects_buffer():
    # Margin+risk exactly at 70% of capital should be safe with a 30% buffer,
    # and unsafe with no buffer margin to spare above it.
    price, lot_size, margin_pct, stop = 20000, 75, 0.12, 20
    car = margin.capital_at_risk(price, lot_size, margin_pct, stop)
    capital_exact = car / 0.70
    assert margin.is_safe(capital_exact, price, lot_size, margin_pct, stop, buffer_pct=0.30)
    assert not margin.is_safe(capital_exact - 1, price, lot_size, margin_pct, stop, buffer_pct=0.30)


def test_max_safe_lots_is_zero_when_capital_too_small():
    assert margin.max_safe_lots(50_000, 24000, 75, 0.12, 20, 0.30) == 0


def test_max_safe_lots_scales_down_as_price_rises():
    lots_low = margin.max_safe_lots(10_000_000, 12000, 75, 0.12, 20, 0.30)
    lots_high = margin.max_safe_lots(10_000_000, 24000, 75, 0.12, 20, 0.30)
    assert lots_high < lots_low


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

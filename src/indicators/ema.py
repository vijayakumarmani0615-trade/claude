"""Exponential Moving Average, computed continuously across the whole series.

Intraday indices trade session to session with no reset in the underlying
trend, so the EMA is carried across day boundaries rather than restarted each
morning (matches how it looks on a chart in TradingView/broker terminals).
"""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()

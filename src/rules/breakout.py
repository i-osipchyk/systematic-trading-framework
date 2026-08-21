"""
Donchian channel breakout rules.

Formula: channel_high = prices.shift(1).rolling(N).max()
         channel_low  = prices.shift(1).rolling(N).min()
         midpoint     = (channel_high + channel_low) / 2
         half_width   = ((channel_high - channel_low) / 2).clip(lower=prices.abs() * 1e-8)
         raw          = (prices - midpoint) / half_width
         forecast     = clip(raw × scalar, -20, +20)

Signal is normalised by channel width, not volatility.
raw = +1 when price equals the previous N-bar high.
raw =  0 at the channel midpoint (neutral).
raw = -1 when price equals the previous N-bar low.
"""
from __future__ import annotations

import pandas as pd

FORECAST_CAP = 20.0

SCALARS: dict[int, float] = {20: 1.0, 50: 1.0, 100: 1.0, 200: 1.0}

LOOKBACKS = list(SCALARS.keys())


def breakout(
    prices: pd.Series,
    lookback: int,
    scalar: float | None = None,
) -> pd.Series:
    """Single Donchian breakout forecast, scaled and capped.

    Args:
        prices:   Adjusted close price series.
        lookback: Channel lookback period in bars.
        scalar:   Override scalar. If None, looks up SCALARS dict. Pass 1.0
                  to get the raw (unscaled) signal for calibration purposes.

    Returns:
        Forecast series in [-20, +20].
    """
    if scalar is None:
        if lookback not in SCALARS:
            raise ValueError(f"No scalar for BREAKOUT({lookback}). Add it to SCALARS.")
        scalar = SCALARS[lookback]

    channel_high = prices.shift(1).rolling(lookback).max()
    channel_low = prices.shift(1).rolling(lookback).min()
    midpoint = (channel_high + channel_low) / 2
    half_width = ((channel_high - channel_low) / 2).clip(lower=prices.abs() * 1e-8)

    raw = (prices - midpoint) / half_width
    scaled = raw * scalar
    return scaled.clip(-FORECAST_CAP, FORECAST_CAP).rename(f"BREAKOUT_{lookback}")


def all_breakout_forecasts(
    prices: pd.Series,
    scalars: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Compute all Donchian breakout forecasts and return as a DataFrame.

    Args:
        prices:  Adjusted close price series.
        scalars: Override scalars dict {lookback: scalar}. If None, uses LOOKBACKS
                 with SCALARS defaults. When provided, iterates its keys.

    Returns:
        DataFrame with one column per rule.
    """
    if scalars is None:
        return pd.concat(
            [breakout(prices, n) for n in LOOKBACKS],
            axis=1,
        )
    elif not scalars:
        return pd.DataFrame(index=prices.index)
    else:
        return pd.concat(
            [breakout(prices, n, scalar=v) for n, v in scalars.items()],
            axis=1,
        )

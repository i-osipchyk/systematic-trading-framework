"""
Time-series momentum rules.

Formula: raw      = prices / prices.shift(L) - 1
         forecast = clip(raw × scalar, -20, +20)

Signal is the total return over the past L bars, not vol-normalised.
"""
from __future__ import annotations

import pandas as pd

FORECAST_CAP = 20.0

SCALARS: dict[int, float] = {63: 1.0, 126: 1.0, 252: 1.0}

LOOKBACKS = list(SCALARS.keys())


def tsmom(
    prices: pd.Series,
    lookback: int,
    scalar: float | None = None,
) -> pd.Series:
    """Single TSMOM rule forecast, scaled and capped.

    Args:
        prices:   Adjusted close price series.
        lookback: Return lookback period in bars.
        scalar:   Override scalar. If None, looks up SCALARS dict. Pass 1.0
                  to get the raw (unscaled) signal for calibration purposes.

    Returns:
        Forecast series in [-20, +20].
    """
    if scalar is None:
        if lookback not in SCALARS:
            raise ValueError(f"No scalar for TSMOM({lookback}). Add it to SCALARS.")
        scalar = SCALARS[lookback]

    raw = prices / prices.shift(lookback) - 1
    scaled = raw * scalar
    return scaled.clip(-FORECAST_CAP, FORECAST_CAP).rename(f"TSMOM_{lookback}")


def all_tsmom_forecasts(
    prices: pd.Series,
    scalars: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Compute all TSMOM forecasts and return as a DataFrame.

    Args:
        prices:  Adjusted close price series.
        scalars: Override scalars dict {lookback: scalar}. If None, uses LOOKBACKS
                 with SCALARS defaults. When provided, iterates its keys.

    Returns:
        DataFrame with one column per rule.
    """
    if scalars is None:
        return pd.concat(
            [tsmom(prices, n) for n in LOOKBACKS],
            axis=1,
        )
    elif not scalars:
        return pd.DataFrame(index=prices.index)
    else:
        return pd.concat(
            [tsmom(prices, n, scalar=v) for n, v in scalars.items()],
            axis=1,
        )

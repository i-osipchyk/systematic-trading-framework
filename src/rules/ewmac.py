"""
EWMAC (Exponentially Weighted Moving Average Crossover) trend-following rules.

Formula: raw = (fast_EMA - slow_EMA) / (price × daily_vol)
         forecast = clip(raw × scalar, -20, +20)

Scalars calibrated on IS data (2018–2024) pooled across all 8 instruments
so that each rule's mean absolute forecast = 10.
Carver's universal scalars (10.6, 7.5, …) target the same goal but on a
futures universe; our CFD universe produces smaller raw signals, requiring
larger scalars.
"""
from __future__ import annotations

import pandas as pd

FORECAST_CAP = 20.0

# IS-calibrated scalars: 10 / mean_abs_raw, pooled across all instruments
SCALARS: dict[tuple[int, int], float] = {
    (2,   8):  13.35,
    (4,  16):   9.38,
    (8,  32):   6.50,
    (16,  64):  4.50,
    (32, 128):  3.13,
    (64, 256):  2.35,
}

# All six crossover pairs in the trend family
PAIRS = list(SCALARS.keys())


def ewmac(
    prices: pd.Series,
    fast: int,
    slow: int,
    vol: pd.Series,
    scalar: float | None = None,
) -> pd.Series:
    """Single EWMAC rule forecast, scaled and capped.

    Args:
        prices: Adjusted close price series.
        fast:   Fast EMA span.
        slow:   Slow EMA span.
        vol:    Daily % vol series (from src.rules.vol.daily_vol).
        scalar: Override scalar. If None, looks up SCALARS dict. Pass 1.0
                to get the raw (unscaled) signal for calibration purposes.

    Returns:
        Forecast series in [-20, +20].
    """
    if scalar is None:
        if (fast, slow) not in SCALARS:
            raise ValueError(f"No scalar for EWMAC({fast},{slow}). Add it to SCALARS.")
        scalar = SCALARS[(fast, slow)]

    fast_ema = prices.ewm(span=fast, min_periods=fast).mean()
    slow_ema = prices.ewm(span=slow, min_periods=slow).mean()

    raw = (fast_ema - slow_ema) / (prices * vol)
    scaled = raw * scalar
    return scaled.clip(-FORECAST_CAP, FORECAST_CAP).rename(f"EWMAC_{fast}_{slow}")


def all_ewmac_forecasts(
    prices: pd.Series,
    vol: pd.Series,
    scalars: dict[tuple[int, int], float] | None = None,
) -> pd.DataFrame:
    """Compute all EWMAC forecasts and return as a DataFrame.

    Args:
        prices:  Adjusted close price series.
        vol:     Daily % vol series.
        scalars: Override scalars dict {(fast, slow): scalar}. If None, uses
                 PAIRS with SCALARS defaults. When provided, iterates its keys
                 (so the set of rules is determined by the scalars dict).

    Returns:
        DataFrame with one column per rule.
    """
    if scalars is None:
        pairs = PAIRS
        return pd.concat(
            [ewmac(prices, f, s, vol) for f, s in pairs],
            axis=1,
        )
    elif not scalars:
        return pd.DataFrame(index=prices.index)
    else:
        return pd.concat(
            [ewmac(prices, f, s, vol, scalar=v) for (f, s), v in scalars.items()],
            axis=1,
        )

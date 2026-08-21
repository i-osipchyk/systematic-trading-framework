"""
Mean reversion rules: vol-normalised deviation from EMA.

Formula: raw = -(price - EMA) / (price × daily_vol)
         forecast = clip(raw × scalar, -20, +20)

Negative sign: price above EMA → negative forecast (expect reversion down).

Scalar ≈ 10 is an analytical prior for a vol-normalised half-normal signal.
Verify against IS backtest data; adjust only if empirical mean absolute
forecast deviates more than 30% from 10.
"""
from __future__ import annotations

import pandas as pd

FORECAST_CAP = 20.0

# Per-span scalars calibrated on IS data (2018–2024) pooled across all 8
# instruments. Longer EMAs have larger raw deviations so need smaller scalars.
# Re-run scripts/verify_rules.py calibration block if instruments or IS period change.
SCALARS: dict[int, float] = {
    16:  6.96,
    200: 1.74,
}

SPANS = list(SCALARS.keys())


def mean_reversion(
    prices: pd.Series,
    span: int,
    vol: pd.Series,
    scalar: float | None = None,
) -> pd.Series:
    """Single MR rule forecast, scaled and capped.

    Args:
        prices: Adjusted close price series.
        span:   EMA span for the reference level.
        vol:    Daily % vol series (from src.rules.vol.daily_vol).
        scalar: Override scalar. If None, looks up SCALARS dict. Pass 1.0
                to get the raw (unscaled) signal for calibration purposes.

    Returns:
        Forecast series in [-20, +20].
    """
    if scalar is None:
        if span not in SCALARS:
            raise ValueError(f"No scalar for MR({span}). Add it to SCALARS.")
        scalar = SCALARS[span]

    ema = prices.ewm(span=span, min_periods=span).mean()
    raw = -(prices - ema) / (prices * vol)
    scaled = raw * scalar
    return scaled.clip(-FORECAST_CAP, FORECAST_CAP).rename(f"MR_{span}")


def all_mr_forecasts(
    prices: pd.Series,
    vol: pd.Series,
    scalars: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Compute all MR forecasts and return as a DataFrame.

    Args:
        prices:  Adjusted close price series.
        vol:     Daily % vol series.
        scalars: Override scalars dict {span: scalar}. If None, uses SPANS with
                 SCALARS defaults. When provided, iterates its keys.

    Returns:
        DataFrame with one column per rule.
    """
    if scalars is None:
        return pd.concat(
            [mean_reversion(prices, span, vol) for span in SPANS],
            axis=1,
        )
    elif not scalars:
        return pd.DataFrame(index=prices.index)
    else:
        return pd.concat(
            [mean_reversion(prices, span, vol, scalar=v) for span, v in scalars.items()],
            axis=1,
        )

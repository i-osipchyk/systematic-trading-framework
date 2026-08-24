"""
Seasonality rule: calendar-based monthly forecast fitted on IS data.

Signal = scaled historical mean return for the current calendar month.
Applicable to instruments with strong seasonal patterns (ags, energy).
Non-applicable instruments return zero.

Fitting:
    fit_seasonality(prices) -> dict[int, float]
    Computes mean daily return per calendar month over IS data, then scales
    so the cross-month mean absolute value ≈ 10.

Usage:
    month_means = fit_seasonality(is_prices)
    fc = seasonality_forecast(prices, month_means)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FORECAST_CAP = 20.0

# Instruments where seasonality is meaningfully applicable
SEASONAL_INSTRUMENTS: set[str] = {
    "Coffee", "Cocoa", "Sugar", "Corn", "Cotton",  # agricultural softs
    "NatGas", "SpotCrude",                          # energy
}


def fit_seasonality(prices: pd.Series) -> dict[int, float]:
    """Fit monthly seasonal model on IS price series.

    Returns scaled monthly means {1..12: float} where the scaling ensures
    mean(abs(values)) ≈ 10. Returns all-zero dict if data is insufficient.
    """
    returns = prices.pct_change().dropna()
    month_means: dict[int, float] = {}
    for m in range(1, 13):
        mask = returns.index.month == m
        month_means[m] = float(returns[mask].mean()) if mask.sum() > 5 else 0.0

    mean_abs = float(np.mean(np.abs(list(month_means.values()))))
    if mean_abs < 1e-8:
        return {m: 0.0 for m in range(1, 13)}

    scale = 10.0 / mean_abs
    return {m: round(v * scale, 6) for m, v in month_means.items()}


def seasonality_forecast(
    prices: pd.Series,
    month_means: dict[int, float],
) -> pd.Series:
    """Generate a seasonal forecast series from fitted monthly means."""
    if not month_means or all(v == 0.0 for v in month_means.values()):
        return pd.Series(0.0, index=prices.index, name="SEASONALITY")
    fc = prices.index.month.map(month_means).astype(float)
    return pd.Series(fc.values, index=prices.index, name="SEASONALITY").clip(
        -FORECAST_CAP, FORECAST_CAP
    )


def all_seasonality_forecasts(
    prices: pd.Series,
    vol: pd.Series | None,
    month_means: dict[int, float],
) -> pd.DataFrame:
    """Return a one-column DataFrame suitable for combined_forecast."""
    return seasonality_forecast(prices, month_means).to_frame()

"""
Shared volatility estimation used by both trading rules and position sizing.

Carver's robust vol: EWMA of daily % returns, with a floor to prevent
near-zero vol from producing extreme forecasts on low-activity days.

Returns daily (not annualised) vol as a fraction (e.g. 0.012 = 1.2% / day).
"""

import pandas as pd

VOL_SPAN = 35        # EWMA span for vol estimation (Carver default)
VOL_MIN_PERIODS = 10
VOL_FLOOR_QUANTILE = 0.05   # floor at 5th percentile of rolling vol
VOL_FLOOR_LOOKBACK = 500    # bars used to compute the floor


def daily_vol(prices: pd.Series, span: int = VOL_SPAN) -> pd.Series:
    """EWMA estimate of daily % return volatility with a vol floor.

    The floor prevents the signal from blowing up during unusually quiet
    periods. Set to the 5th percentile of the trailing 500-bar vol series.
    """
    returns = prices.pct_change()
    raw_vol = returns.ewm(span=span, min_periods=VOL_MIN_PERIODS).std()

    # Floor: rolling 5th percentile of the vol series itself
    floor = (
        raw_vol
        .rolling(VOL_FLOOR_LOOKBACK, min_periods=VOL_MIN_PERIODS)
        .quantile(VOL_FLOOR_QUANTILE)
    )
    floored = raw_vol.where(raw_vol >= floor, floor)

    # Absolute minimum: prevents position blow-up during flat-price data periods
    # (e.g. monthly FRED data forward-filled to daily). 0.001 = 0.1% daily ≈ 1.6%
    # annualized — well below any real asset vol. Only fires in pathological cases.
    floored = floored.clip(lower=0.001)
    return floored

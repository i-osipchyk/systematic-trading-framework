"""
Forecast combination: weighted average across rule families + FDM.

Structure:
  - Trend family  (75%): 6 EWMAC rules, equal weight within family
  - MR family     (25%): 4 MR rules,   equal weight within family
  - FDM applied to the combined forecast to correct for inter-rule correlation

FDM (Forecast Diversification Multiplier) is estimated from the IS correlation
matrix of individual rule forecasts. Until FDM is calibrated it defaults to 1.0.
Call calibrate_fdm() on the IS period to compute the proper value.

All forecasts are capped at ±20 before and after combination.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.rules.ewmac import all_ewmac_forecasts
from src.rules.mr import all_mr_forecasts
from src.rules.vol import daily_vol

TREND_WEIGHT = 0.75
MR_WEIGHT = 0.25
FORECAST_CAP = 20.0


def combined_forecast(
    prices: pd.Series,
    vol: pd.Series | None = None,
    fdm: float = 1.0,
    ewmac_scalars: dict[tuple[int, int], float] | None = None,
    mr_scalars: dict[int, float] | None = None,
    rule_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Compute the combined forecast for a single instrument.

    Args:
        prices:        Adjusted close price series.
        vol:           Pre-computed daily vol series. Computed from prices if None.
        fdm:           Forecast diversification multiplier. Use 1.0 until calibrated.
        ewmac_scalars: Override scalars for EWMAC rules {(fast, slow): scalar}.
                       Passed through to all_ewmac_forecasts(). None = use defaults.
        mr_scalars:    Override scalars for MR rules {span: scalar}.
                       Passed through to all_mr_forecasts(). None = use defaults.
        rule_weights:  Per-rule combination weights e.g. {'EWMAC_2_8': 0.125, ...}.
                       When provided, combine using these explicit weights instead of
                       the TREND_WEIGHT/MR_WEIGHT family-level logic.
                       trend_combined and mr_combined are still computed for display.

    Returns:
        DataFrame with columns for every individual rule forecast plus
        'trend_combined', 'mr_combined', and 'combined'.
    """
    if vol is None:
        vol = daily_vol(prices)

    trend_df = all_ewmac_forecasts(prices, vol, scalars=ewmac_scalars)
    mr_df = all_mr_forecasts(prices, vol, scalars=mr_scalars)

    trend_combined = trend_df.mean(axis=1).clip(-FORECAST_CAP, FORECAST_CAP)
    mr_combined = (
        mr_df.mean(axis=1).clip(-FORECAST_CAP, FORECAST_CAP)
        if not mr_df.empty
        else pd.Series(0.0, index=prices.index)
    )

    # Build the raw combined using either rule_weights or family-level weights
    all_forecasts = pd.concat([trend_df, mr_df], axis=1)

    if rule_weights is not None:
        raw_combined = sum(
            rule_weights.get(col, 0.0) * all_forecasts[col]
            for col in all_forecasts.columns
            if col in rule_weights
        )
        # Ensure it's a Series (sum() on empty iterable returns 0)
        if not isinstance(raw_combined, pd.Series):
            raw_combined = pd.Series(0.0, index=prices.index)
    else:
        raw_combined = TREND_WEIGHT * trend_combined + MR_WEIGHT * mr_combined

    final = (raw_combined * fdm).clip(-FORECAST_CAP, FORECAST_CAP)

    return pd.concat(
        [trend_df, mr_df,
         trend_combined.rename("trend_combined"),
         mr_combined.rename("mr_combined"),
         final.rename("combined")],
        axis=1,
    )


def calibrate_fdm(
    forecasts_df: pd.DataFrame,
    rule_weights: dict[str, float] | None = None,
) -> float:
    """Estimate FDM from the correlation matrix of IS rule forecasts.

    FDM = 1 / sqrt(w' C w)
    where w is the weight vector and C is the forecast correlation matrix.

    Args:
        forecasts_df: DataFrame of individual rule forecasts (IS period only).
                      Exclude the combined/family columns — only raw rule cols.
        rule_weights: Per-rule weights dict[str, float]. When provided, use these
                      weights directly instead of equal-within-family weights.

    Returns:
        FDM scalar, clipped to [1.0, 2.5].
    """
    rule_cols = [c for c in forecasts_df.columns
                 if c not in ("trend_combined", "mr_combined", "combined")]

    if rule_weights is not None:
        weights = np.array([rule_weights.get(c, 0.0) for c in rule_cols])
    else:
        n_trend = sum(1 for c in rule_cols if c.startswith("EWMAC"))
        n_mr = sum(1 for c in rule_cols if c.startswith("MR"))

        weights = np.array(
            [TREND_WEIGHT / n_trend] * n_trend +
            [MR_WEIGHT / n_mr] * n_mr
        )

    corr = forecasts_df[rule_cols].dropna().corr().values
    portfolio_variance = weights @ corr @ weights
    fdm = 1.0 / np.sqrt(portfolio_variance)

    # Cap FDM at a sensible upper bound (Carver recommends ≤ 2.5)
    return float(np.clip(fdm, 1.0, 2.5))

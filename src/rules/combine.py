"""
Forecast combination: weighted average across rule families + FDM.

FDM (Forecast Diversification Multiplier) is estimated from the IS correlation
matrix of individual rule forecasts. Until FDM is calibrated it defaults to 1.0.
Call calibrate_fdm() on the IS period to compute the proper value.

All forecasts are capped at ±20 before and after combination.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.rules.vol import daily_vol

FORECAST_CAP = 20.0


def combined_forecast(
    prices: pd.Series,
    vol: pd.Series | None = None,
    fdm: float = 1.0,
    family_scalars: dict[str, dict] | None = None,
    rule_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Compute the combined forecast for a single instrument.

    Args:
        prices:        Adjusted close price series.
        vol:           Pre-computed daily vol series. Computed from prices if None.
        fdm:           Forecast diversification multiplier. Use 1.0 until calibrated.
        family_scalars: Maps config block name to native scalars dict
                        (e.g. {"ewmac": {(4,16): 9.38, ...}, "breakout": {20: 3.1}}).
                        When None, loads the active config and uses each family's
                        built-in module-level defaults.
                        When a family's value is None, the handler uses its
                        module-level SCALARS.
        rule_weights:  Per-rule combination weights e.g. {'EWMAC_2_8': 0.125, ...}.
                       When provided, combine using these explicit weights instead of
                       equal weighting across all rule columns.

    Returns:
        DataFrame with columns for every individual rule forecast plus 'combined'.
    """
    from src.backtest.config import load_rules_config
    from src.rules.registry import REGISTRY

    if vol is None:
        vol = daily_vol(prices)

    if family_scalars is None:
        rules_cfg = load_rules_config()
        family_scalars = {block: None for block in rules_cfg}

    dfs = []
    for block_name, scalars in family_scalars.items():
        handler = REGISTRY.get(block_name)
        if handler is None:
            continue
        df = handler.compute_all(prices, vol, scalars)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        return pd.DataFrame({"combined": pd.Series(0.0, index=prices.index)})

    all_forecasts = pd.concat(dfs, axis=1)
    rule_cols = list(all_forecasts.columns)

    if rule_weights is not None:
        raw_combined = sum(
            rule_weights.get(col, 0.0) * all_forecasts[col]
            for col in rule_cols
            if col in rule_weights
        )
        if not isinstance(raw_combined, pd.Series):
            raw_combined = pd.Series(0.0, index=prices.index)
    else:
        raw_combined = all_forecasts[rule_cols].mean(axis=1)

    final = (raw_combined * fdm).clip(-FORECAST_CAP, FORECAST_CAP)

    return pd.concat(
        [all_forecasts, final.rename("combined")],
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
        rule_weights: Per-rule weights dict[str, float]. When provided, use these
                      weights directly instead of equal weights.

    Returns:
        FDM scalar, clipped to [1.0, 2.5].
    """
    rule_cols = [c for c in forecasts_df.columns if c != "combined"]

    if not rule_cols:
        return 1.0

    if rule_weights is not None:
        weights = np.array([rule_weights.get(c, 0.0) for c in rule_cols])
    else:
        n = len(rule_cols)
        weights = np.full(n, 1.0 / n)

    corr = forecasts_df[rule_cols].dropna().corr().values
    portfolio_variance = weights @ corr @ weights
    fdm = 1.0 / np.sqrt(portfolio_variance)

    return float(np.clip(fdm, 1.0, 2.5))

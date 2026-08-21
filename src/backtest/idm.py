import numpy as np
import pandas as pd

IDM_CAP = 2.5


def compute_idm(
    instrument_returns: pd.DataFrame,
    weights: np.ndarray | None = None,
) -> float:
    """Compute Instrument Diversification Multiplier from IS return correlations.

    Formula: IDM = 1 / sqrt(w' C w), clipped to [1.0, IDM_CAP].

    Args:
        instrument_returns: DataFrame of daily returns (net_pnl / capital),
                            one column per instrument. IS period only.
        weights:            Portfolio weights. Equal-weighted if None.
    """
    cols = instrument_returns.columns.tolist()
    n = len(cols)

    if weights is None:
        weights = np.ones(n) / n

    weights = np.array(weights) / np.sum(weights)  # normalise

    # Drop rows where all instruments are NaN (e.g. before any data starts)
    returns = instrument_returns.dropna(how="all")

    # Per-column NaN is handled by pairwise correlation (min_periods enforced)
    corr = returns.corr(min_periods=20).values

    # Replace any remaining NaN correlation with 0 (treat as uncorrelated)
    corr = np.where(np.isnan(corr), 0.0, corr)
    np.fill_diagonal(corr, 1.0)

    portfolio_variance = weights @ corr @ weights
    idm = 1.0 / np.sqrt(portfolio_variance)
    return float(np.clip(idm, 1.0, IDM_CAP))

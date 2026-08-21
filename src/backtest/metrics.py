import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 256


def sharpe_ratio(
    daily_pnl: pd.Series,
    capital: float,
    ann_factor: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualised Sharpe ratio (risk-free rate = 0)."""
    r = daily_pnl / capital
    if r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(ann_factor))


def annualised_return(
    daily_pnl: pd.Series,
    capital: float,
    ann_factor: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualised arithmetic return as a fraction (e.g. 0.15 = 15%)."""
    n = len(daily_pnl.dropna())
    if n == 0:
        return 0.0
    return float(daily_pnl.sum() / capital * ann_factor / n)


def equity_curve(daily_pnl: pd.Series, capital: float) -> pd.Series:
    """Compounded equity curve.

    Equivalent to resizing positions daily to current equity: each day's
    unit return (pnl/capital) is the same regardless of compounding, so
    equity_t = capital × prod(1 + r_i) for i ≤ t.
    """
    r = daily_pnl / capital
    return capital * (1 + r).cumprod()


def max_drawdown(
    daily_pnl: pd.Series,
    capital: float,
) -> float:
    """Maximum peak-to-trough drawdown as a negative fraction of peak equity.

    Uses compounded equity (mark-to-market sizing), so drawdown is bounded
    at -100% and reflects what a real account would experience.
    """
    eq = equity_curve(daily_pnl, capital)
    return float((eq / eq.cummax() - 1).min())


def annual_turnover(
    positions: pd.Series,
    ann_factor: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Average number of roundtrips traded per year.

    Roundtrips = sum(|Δposition|) / 2 / years
    Normalised by mean absolute position so it's comparable across instruments.
    """
    daily_trades = positions.diff().abs()
    mean_pos = positions.abs().mean()
    if mean_pos == 0:
        return 0.0
    n_years = len(positions.dropna()) / ann_factor
    if n_years == 0:
        return 0.0
    return float(daily_trades.sum() / 2 / mean_pos / n_years)


def performance_report(
    daily_pnl: pd.Series,
    capital: float,
    positions: pd.Series | None = None,
    label: str = "",
) -> dict:
    return {
        "label": label,
        "sharpe": sharpe_ratio(daily_pnl, capital),
        "ann_return": annualised_return(daily_pnl, capital),
        "max_drawdown": max_drawdown(daily_pnl, capital),
        "turnover": annual_turnover(positions) if positions is not None else float("nan"),
    }

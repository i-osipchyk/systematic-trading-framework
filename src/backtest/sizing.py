import numpy as np
import pandas as pd

from src.backtest.config import load_bars_per_year


def round_to_lot(positions: pd.Series, lot_step: float) -> pd.Series:
    """Round positions to the nearest lot_step increment."""
    if lot_step <= 0:
        return positions
    return (np.round(positions / lot_step) * lot_step).rename(positions.name)


def apply_inertia(target: pd.Series, buffer_fraction: float = 0.10) -> pd.Series:
    """Hold current position unless new target differs by more than buffer_fraction of target.

    Avoids churning on small forecast changes that don't justify transaction costs.
    """
    values = target.to_numpy(dtype=float)
    held = np.empty(len(values))
    current = 0.0
    for i, tgt in enumerate(values):
        if abs(tgt - current) > buffer_fraction * abs(tgt):
            current = tgt
        held[i] = current
    return pd.Series(held, index=target.index, name=target.name)


def compute_positions(
    prices: pd.Series,
    vol: pd.Series,
    forecast: pd.Series,
    pointsize: float,
    capital: float = 10_000.0,
    vol_target: float = 0.20,
    idm: float = 1.0,
    fx_rate_to_usd: pd.Series | float = 1.0,
    instrument_weight: float = 1.0,
) -> pd.Series:
    """Convert combined forecast to fractional contract positions.

    Formula:
        annual_vol          = vol * sqrt(load_bars_per_year())
        block_value_usd     = price * pointsize * fx_rate_to_usd
        position            = capital * vol_target * idm * (forecast / 10)
                              / (block_value_usd * annual_vol)

    fx_rate_to_usd converts the instrument's native P&L currency to USD:
        USD instruments  → 1.0
        EUR instruments  → EURUSD price series
        GBP instruments  → EURUSD / EURGBP (synthetic GBPUSD)
        JPY instruments  → 1 / USDJPY

    instrument_weight scales the position by the handcrafted portfolio weight,
    so that the portfolio vol target is distributed across instruments according
    to their intended allocation rather than equal-weighting.

    Without this correction, positions for non-USD instruments are sized
    in mixed currency units and will be systematically wrong.

    Returns Series named 'position'.
    """
    annual_vol = vol * np.sqrt(load_bars_per_year())
    block_value_usd = prices * pointsize * fx_rate_to_usd
    notional = capital * vol_target * idm * instrument_weight * (forecast / 10)
    positions = notional / (block_value_usd * annual_vol)
    return positions.rename("position")

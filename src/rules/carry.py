"""
Carry rule: annualised interest rate differential normalised by instrument vol.

Only meaningful for FX pairs where both leg currencies have known policy rates.
Non-FX instruments (equities, commodities, dollar index) return a zero series
so their carry weight is neutral rather than missing.

Raw signal = (base_rate% - quote_rate%) / (daily_vol * sqrt(bars_per_year))
Scaled so E[|carry|] = 10 after multiplying by scalar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BARS_PER_YEAR = 256

# instrument_code → (base_currency, quote_currency)
# base = currency you go long, quote = currency you go short when buying 1 unit
FX_CARRY_PAIRS: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "USDJPY": ("USD", "JPY"),
    "EURGBP": ("EUR", "GBP"),
}

SCALARS: dict[str, float] = {"carry": 1.0}


def carry(
    prices: pd.Series,
    instrument_code: str,
    vol: pd.Series | None = None,
    scalar: float | None = None,
) -> pd.Series:
    """Carry forecast for one instrument.

    Returns a zero series for non-FX instruments (neutral, not NaN).
    """
    from src.data.rates import load_policy_rates
    from src.rules.vol import daily_vol

    if instrument_code not in FX_CARRY_PAIRS:
        return pd.Series(0.0, index=prices.index, name="CARRY")

    if vol is None:
        vol = daily_vol(prices)
    if scalar is None:
        scalar = SCALARS["carry"]

    base_ccy, quote_ccy = FX_CARRY_PAIRS[instrument_code]
    rates = load_policy_rates(index=prices.index)

    missing = [c for c in (base_ccy, quote_ccy) if c not in rates.columns]
    if missing:
        return pd.Series(0.0, index=prices.index, name="CARRY")

    base_rate  = rates[base_ccy]   # annualised %
    quote_rate = rates[quote_ccy]
    rate_diff  = (base_rate - quote_rate) / 100.0  # convert to fraction

    ann_vol = (vol * np.sqrt(BARS_PER_YEAR)).clip(lower=1e-8)
    raw = rate_diff / ann_vol

    return (raw * scalar).rename("CARRY")


def all_carry_forecasts(
    prices: pd.Series,
    instrument_code: str,
    vol: pd.Series | None = None,
    scalars: dict | None = None,
) -> pd.DataFrame:
    sc = (scalars or SCALARS).get("carry", SCALARS["carry"])
    fc = carry(prices, instrument_code, vol, scalar=sc)
    return fc.to_frame("CARRY")

"""
Carry rule: net income from holding the position, normalised by instrument vol.

Three instrument types are supported:

  FX pairs      — annualised interest rate differential (base_rate − quote_rate)
  Bond futures  — bond yield minus short-term funding rate (yield curve carry)
  Equity indices — dividend yield minus funding rate (US500 / NAS100 only)

Non-covered instruments return a zero series so their carry weight is neutral.

Raw signal = net_carry_fraction / ann_vol
Scaled so E[|carry|] ≈ 10 after multiplying by scalar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BARS_PER_YEAR = 256

# ── Instrument classification ─────────────────────────────────────────────────

FX_CARRY_PAIRS: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "USDJPY": ("USD", "JPY"),
    "USDCAD": ("USD", "CAD"),
}

BOND_CARRY_INSTRUMENTS: dict[str, str] = {
    # instrument_code: funding_currency
    "US2YR":  "USD",
    "US5YR":  "USD",
    "US10YR": "USD",
    "US30YR": "USD",
    "BUND":   "EUR",
}

EQUITY_CARRY_INSTRUMENTS: dict[str, str] = {
    # Dividend yield - funding rate is persistently negative in high-rate regimes,
    # creating a systematic short bias throughout 1984-2001.  Equity carry via
    # CFD requires futures roll data (not available here), so this is disabled.
}

SCALARS: dict[str, float] = {"carry": 1.0}


def carry(
    prices: pd.Series,
    instrument_code: str,
    vol: pd.Series | None = None,
    scalar: float | None = None,
) -> pd.Series:
    """Carry forecast for one instrument.

    Returns a zero series for instruments with no carry model.
    """
    from src.data.rates import (
        load_bond_yields,
        load_equity_dividend_yields,
        load_policy_rates,
    )
    from src.rules.vol import daily_vol

    if scalar is None:
        scalar = SCALARS["carry"]
    if vol is None:
        vol = daily_vol(prices)

    ann_vol = (vol * np.sqrt(BARS_PER_YEAR)).clip(lower=1e-8)

    # ── FX carry ──────────────────────────────────────────────────────────────
    if instrument_code in FX_CARRY_PAIRS:
        base_ccy, quote_ccy = FX_CARRY_PAIRS[instrument_code]
        rates = load_policy_rates(index=prices.index)

        missing = [c for c in (base_ccy, quote_ccy) if c not in rates.columns]
        if missing:
            return pd.Series(0.0, index=prices.index, name="CARRY")

        rate_diff = (rates[base_ccy] - rates[quote_ccy]) / 100.0
        raw = rate_diff / ann_vol

    # ── Bond carry ────────────────────────────────────────────────────────────
    elif instrument_code in BOND_CARRY_INSTRUMENTS:
        funding_ccy = BOND_CARRY_INSTRUMENTS[instrument_code]
        rates = load_policy_rates(index=prices.index)
        bond_yields = load_bond_yields(index=prices.index)

        if funding_ccy not in rates.columns or instrument_code not in bond_yields.columns:
            return pd.Series(0.0, index=prices.index, name="CARRY")

        funding_rate = rates[funding_ccy] / 100.0
        bond_yield = bond_yields[instrument_code] / 100.0
        raw = (bond_yield - funding_rate) / ann_vol

    # ── Equity carry ──────────────────────────────────────────────────────────
    elif instrument_code in EQUITY_CARRY_INSTRUMENTS:
        funding_ccy = EQUITY_CARRY_INSTRUMENTS[instrument_code]
        rates = load_policy_rates(index=prices.index)
        div_yields = load_equity_dividend_yields(index=prices.index)

        if funding_ccy not in rates.columns or instrument_code not in div_yields.columns:
            return pd.Series(0.0, index=prices.index, name="CARRY")

        funding_rate = rates[funding_ccy] / 100.0
        div_yield = div_yields[instrument_code] / 100.0
        raw = (div_yield - funding_rate) / ann_vol

    # ── Not covered ───────────────────────────────────────────────────────────
    else:
        return pd.Series(0.0, index=prices.index, name="CARRY")

    return (raw * scalar).clip(-20.0, 20.0).rename("CARRY")


def all_carry_forecasts(
    prices: pd.Series,
    instrument_code: str,
    vol: pd.Series | None = None,
    scalars: dict | None = None,
) -> pd.DataFrame:
    sc = (scalars or SCALARS).get("carry", SCALARS["carry"])
    fc = carry(prices, instrument_code, vol, scalar=sc)
    return fc.to_frame("CARRY")

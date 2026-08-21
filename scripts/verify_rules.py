#!/usr/bin/env python3
"""
Verify trading rules on IS data.

For each instrument prints:
  - Mean absolute forecast per rule (target: ~10)
  - Rule correlation matrix
  - FDM estimate
  - Recent combined forecast

Usage:
    uv run python scripts/verify_rules.py
    uv run python scripts/verify_rules.py --instrument BTC
"""

import argparse

import pandas as pd

from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import calibrate_fdm, combined_forecast
from src.rules.vol import daily_vol

INSTRUMENTS = ["BTC", "ETH", "US500", "US30", "GER40", "XAU", "EURUSD", "EURGBP"]


def verify_instrument(code: str, split_date) -> float:
    prices = load_adjusted_prices(code)
    is_prices, _ = split_series(prices, split_date)

    vol = daily_vol(is_prices)
    fc = combined_forecast(is_prices, vol)

    rule_cols = [c for c in fc.columns
                 if c not in ("trend_combined", "mr_combined", "combined")]

    print(f"\n{'='*60}")
    print(f"  {code}  —  IS period: {is_prices.index[0].date()} → {is_prices.index[-1].date()}")
    print(f"{'='*60}")

    # Mean absolute forecast per rule (target ≈ 10)
    print("\nMean absolute forecast (target ≈ 10):")
    mafs = fc[rule_cols].abs().mean()
    for rule, maf in mafs.items():
        flag = "  ✓" if 5 <= maf <= 15 else "  ⚠ (check scalar)"
        print(f"  {rule:<18} {maf:>6.2f}{flag}")

    # FDM
    fdm = calibrate_fdm(fc)
    print(f"\nFDM (IS estimate): {fdm:.3f}")

    # Correlation matrix of rule forecasts
    corr = fc[rule_cols].dropna().corr()
    print("\nForecast correlation matrix:")
    print(corr.round(2).to_string())

    # Last 5 combined forecasts
    print(f"\nRecent combined forecasts:")
    recent = fc[["trend_combined", "mr_combined", "combined"]].tail(5)
    print(recent.round(2).to_string())

    return fdm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", default=None,
                        help="Single instrument to verify (default: all)")
    args = parser.parse_args()

    instruments = [args.instrument] if args.instrument else INSTRUMENTS
    split_date = compute_split_date()
    print(f"IS/OOS split date: {split_date.date()}")

    fdms = {}
    for code in instruments:
        try:
            fdms[code] = verify_instrument(code, split_date)
        except FileNotFoundError:
            print(f"\nWARNING: No data for {code} — run fetch_history.py first.")

    if len(fdms) > 1:
        print(f"\n{'='*60}")
        print("FDM summary:")
        for code, fdm in fdms.items():
            print(f"  {code:<10} {fdm:.3f}")


if __name__ == "__main__":
    main()

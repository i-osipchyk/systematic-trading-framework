"""
Step 03: Compute per-instrument FDM from IS forecast correlations.

Uses the calibrated scalars (step 01) and forecast weights (step 02) to
compute each instrument's Forecast Diversification Multiplier on IS data.

Usage:
    uv run python calibrate/03_fdm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, traded_instruments
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import calibrate_fdm, combined_forecast
from src.rules.vol import daily_vol


def main(state_dir=None, split_date=None) -> None:
    # Load state
    scalars_data = st.load("01_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("02_forecast_weights.yaml", state_dir=state_dir)

    ewmac_scalars = st.parse_ewmac_scalars(scalars_data.get("ewmac", {}))
    mr_scalars = st.parse_mr_scalars(scalars_data.get("mr", {}))
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    if split_date is None:
        split_date = compute_split_date(instruments)

    print(f"  Split date: {split_date.date()}\n")

    fdms: dict[str, float] = {}

    for code in instruments:
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            print(f"  WARNING: no data for {code}, skipping.")
            continue

        is_prices, _ = split_series(prices, split_date)
        vol_is = daily_vol(is_prices)

        fc_is = combined_forecast(
            is_prices, vol_is, fdm=1.0,
            ewmac_scalars=ewmac_scalars,
            mr_scalars=mr_scalars,
            rule_weights=rule_weights,
        )
        rule_cols = [c for c in fc_is.columns
                     if c not in ("trend_combined", "mr_combined", "combined")]

        fdm = calibrate_fdm(fc_is[rule_cols], rule_weights=rule_weights)
        fdms[code] = fdm

    # Save state
    st.save("03_fdm.yaml", {code: round(fdm, 4) for code, fdm in fdms.items()}, state_dir=state_dir)

    # Print table
    print(f"  {'Instrument':<14} {'FDM':>6}")
    print(f"  {'─' * 22}")
    for code, fdm in fdms.items():
        print(f"  {code:<14} {fdm:>6.3f}")

    print()
    print(
        "  Note: all instruments hitting cap (2.500) is normal when EWMAC and MR\n"
        "        rules are used together — their structural anti-correlation requires\n"
        "        FDM ~3.5 which exceeds the cap."
    )
    print(f"\n  Saved → {st.path('03_fdm.yaml', state_dir=state_dir)}")


if __name__ == "__main__":
    main()

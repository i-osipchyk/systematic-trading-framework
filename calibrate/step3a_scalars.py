"""
Step 3a: Compute IS-calibrated scalars for all rules.

For each rule, finds the scalar such that mean absolute forecast = 10
when computed on the IS data, pooled across all instruments.

Usage:
    uv run python calibrate/step3a_scalars.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, load_rules_config, traded_instruments
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol


def main(state_dir=None, split_date=None) -> None:
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules = load_rules_config()

    if split_date is None:
        print("  Computing IS split date...")
        split_date = compute_split_date(instruments)
    print(f"  Split date: {split_date.date()}\n")

    scalars_out: dict[str, dict] = {}
    rows: list[tuple[str, float, float]] = []

    print("  Loading IS data and computing raw mean absolute forecasts...")

    for block_name, block_cfg in rules.items():
        handler = REGISTRY.get(block_name)
        if handler is None:
            print(f"  WARNING: unknown rule block '{block_name}', skipping.")
            continue

        variants = handler.variants_from_cfg(block_cfg)
        if not variants:
            continue

        maf_by_variant: dict = {v: [] for v in variants}

        for code in instruments:
            try:
                prices = load_adjusted_prices(code)
            except FileNotFoundError:
                print(f"  WARNING: no data for {code}, skipping.")
                continue

            is_prices, _ = split_series(prices, split_date)
            if len(is_prices) < 20:
                continue
            vol = daily_vol(is_prices)

            for variant in variants:
                raw = handler.compute_one_raw(is_prices, variant, vol, instrument_code=code)
                maf = float(np.nanmean(np.abs(raw)))
                maf_by_variant[variant].append(maf)

        block_scalars_native: dict = {}
        for variant in variants:
            mafs = [m for m in maf_by_variant[variant] if m > 0.0 and not np.isnan(m)]
            if not mafs:
                continue
            pooled = float(np.nanmean(mafs))
            scalar = round(10.0 / pooled, 4)
            block_scalars_native[variant] = scalar
            rows.append((handler.rule_name(variant), pooled, scalar))

        scalars_out[block_name] = handler.dump_scalars(block_scalars_native)

    # Seasonality: per-instrument calibration (not pooled across instruments).
    # Uses the instruments list from the config's seasonality block if present;
    # falls back to the module-level SEASONAL_INSTRUMENTS set otherwise.
    if "seasonality" in rules:
        from src.rules.seasonality import SEASONAL_INSTRUMENTS, fit_seasonality
        seasonal_instrument_list = rules["seasonality"].get("instruments", list(SEASONAL_INSTRUMENTS))
        seasonal_models: dict[str, dict] = {}
        for code in instruments:
            if code not in seasonal_instrument_list:
                continue
            try:
                prices = load_adjusted_prices(code)
            except FileNotFoundError:
                continue
            is_prices, _ = split_series(prices, split_date)
            if len(is_prices) < 512:
                continue
            month_means = fit_seasonality(is_prices)
            seasonal_models[code] = {str(k): v for k, v in month_means.items()}
            max_abs = max(abs(v) for v in month_means.values()) or 1.0
            rows.append((f"SEASONALITY_{code}", round(10.0 / max_abs, 3), 1.0))
        if seasonal_models:
            scalars_out["seasonality"] = seasonal_models
            print(f"\n  Seasonality: fitted for {list(seasonal_models.keys())}")

    st.save("step3a_scalars.yaml", scalars_out, state_dir=state_dir)

    print()
    if rows:
        col_w = max(len(r[0]) for r in rows) + 2
        print(f"  {'Rule':<{col_w}} {'Raw MAF':>9}  {'Scalar':>8}")
        print(f"  {'─' * (col_w + 22)}")
        for rule, maf, scalar in rows:
            print(f"  {rule:<{col_w}} {maf:>9.3f}  {scalar:>8.2f}")

    print(f"\n  Saved → {st.path('step3a_scalars.yaml', state_dir=state_dir)}")


if __name__ == "__main__":
    main()

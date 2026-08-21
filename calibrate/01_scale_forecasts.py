"""
Step 01: Compute IS-calibrated scalars for all rules.

For each rule, finds the scalar such that mean absolute forecast = 10
when computed on the IS data, pooled across all instruments.

Usage:
    uv run python calibrate/01_scale_forecasts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Ensure project root is on the path when running standalone
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, load_rules_config, traded_instruments
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.ewmac import ewmac
from src.rules.mr import mean_reversion
from src.rules.vol import daily_vol


def main(state_dir=None, split_date=None) -> None:
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules = load_rules_config()
    ewmac_pairs: list[tuple[int, int]] = [tuple(p) for p in rules.get("ewmac", {}).get("pairs", [])]
    mr_spans: list[int] = rules.get("mr", {}).get("spans", [])

    if split_date is None:
        print("  Computing IS split date...")
        split_date = compute_split_date(instruments)
    print(f"  Split date: {split_date.date()}\n")

    # ── Pool raw MAF across instruments for each rule ─────────────────────────
    ewmac_maf: dict[tuple[int, int], list[float]] = {p: [] for p in ewmac_pairs}
    mr_maf: dict[int, list[float]] = {s: [] for s in mr_spans}

    print("  Loading IS data and computing raw mean absolute forecasts...")
    for code in instruments:
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            print(f"  WARNING: no data for {code}, skipping.")
            continue

        is_prices, _ = split_series(prices, split_date)
        vol = daily_vol(is_prices)

        for fast, slow in ewmac_pairs:
            raw = ewmac(is_prices, fast, slow, vol, scalar=1.0)
            maf = float(np.nanmean(np.abs(raw)))
            ewmac_maf[(fast, slow)].append(maf)

        for span in mr_spans:
            raw = mean_reversion(is_prices, span, vol, scalar=1.0)
            maf = float(np.nanmean(np.abs(raw)))
            mr_maf[span].append(maf)

    # ── Compute scalars ───────────────────────────────────────────────────────
    ewmac_scalars: dict[str, float] = {}
    mr_scalars: dict[str, float] = {}

    rows: list[tuple[str, float, float]] = []

    for fast, slow in ewmac_pairs:
        pooled = float(np.nanmean(ewmac_maf[(fast, slow)]))
        scalar = round(10.0 / pooled, 4)
        key = f"{fast}_{slow}"
        ewmac_scalars[key] = scalar
        rows.append((f"EWMAC_{fast}_{slow}", pooled, scalar))

    for span in mr_spans:
        pooled = float(np.nanmean(mr_maf[span]))
        scalar = round(10.0 / pooled, 4)
        key = str(span)
        mr_scalars[key] = scalar
        rows.append((f"MR_{span}", pooled, scalar))

    # ── Save state ────────────────────────────────────────────────────────────
    st.save("01_scalars.yaml", {"ewmac": ewmac_scalars, "mr": mr_scalars}, state_dir=state_dir)

    # ── Print results ─────────────────────────────────────────────────────────
    print()
    col_w = max(len(r[0]) for r in rows) + 2
    print(f"  {'Rule':<{col_w}} {'Raw MAF':>9}  {'Scalar':>8}")
    print(f"  {'─' * (col_w + 22)}")
    for rule, maf, scalar in rows:
        print(f"  {rule:<{col_w}} {maf:>9.3f}  {scalar:>8.2f}")

    print(f"\n  Saved → {st.path('01_scalars.yaml', state_dir=state_dir)}")


if __name__ == "__main__":
    main()

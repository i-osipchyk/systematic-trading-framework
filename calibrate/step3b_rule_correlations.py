"""
Step 3b: IS rule forecast correlation matrix and handcrafted weights.

Loads calibrated scalars (step 3a), computes each rule's IS forecast for every
instrument, then outputs:
  - Pairwise rule correlation matrix (pooled across instruments)
  - Suggested handcrafted forecast weights from Carver's hierarchy

Instruments where a rule returns a flat (zero) signal are excluded from that
rule's correlation computation so constant series don't inflate diversification
estimates.

Usage:
    uv run python calibrate/step3b_rule_correlations.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, traded_instruments
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

# ── Candidate rule set — set after Step 3b correlation analysis ───────────────
#
# v3 rule families: Trend (EWMAC + Breakout + TSMOM candidates) + Seasonality.
# No Carry in v3 — carry was removed at Step 2 (bonds-only host, no FX).
# Seasonality applied universally to all instruments.
#
# FAMILY_WEIGHTS and FAMILY_STRUCTURE below are PROVISIONAL — they are used to
# produce a suggested weight breakdown for reference after the correlation matrix
# is printed. Adjust them once you have reviewed the actual correlations.
#
# Provisional structure: Trend sub-families grouped by timescale.
# Rules at the same timescale are expected to be highly correlated (0.85+);
# Step 3b will confirm. If so, the most redundant can be pruned.

FAMILY_WEIGHTS: dict[str, float] = {
    "Trend":       0.50,
    "Seasonality": 0.50,
}

FAMILY_STRUCTURE: dict[str, list[list[str]]] = {
    "Trend": [
        # Grouped by timescale. Each group is one sub-family (equal budget).
        ["EWMAC_2_8"],                                   # ~1-2 weeks
        ["EWMAC_4_16", "BREAKOUT_20"],                   # ~1 month
        ["EWMAC_8_32", "BREAKOUT_50", "TSMOM_63"],       # ~2-3 months
        ["EWMAC_16_64", "BREAKOUT_100", "TSMOM_126"],    # ~3-5 months
        ["EWMAC_32_128"],                                 # ~5 months
        ["EWMAC_64_256", "BREAKOUT_200", "TSMOM_252"],   # ~10-12 months
    ],
    "Seasonality": [["SEASONALITY"]],
}

SUBFAM_WEIGHTS: dict[str, list[float]] = {
    "Trend":       [1/6, 1/6, 1/6, 1/6, 1/6, 1/6],
    "Seasonality": [1.0],
}


def _handcraft_weights() -> dict[str, float]:
    """Derive forecast weights from the family hierarchy (no correlation data needed).

    Returns a dict mapping rule_name → weight (sums to 1.0).
    """
    weights: dict[str, float] = {}
    for fam_name, fam_w in FAMILY_WEIGHTS.items():
        sub_families = FAMILY_STRUCTURE[fam_name]
        sub_fam_ws = SUBFAM_WEIGHTS[fam_name]
        for sub_fam, sub_w in zip(sub_families, sub_fam_ws):
            rule_w = fam_w * sub_w / len(sub_fam)
            for rule in sub_fam:
                weights[rule] = rule_w
    return weights


def _pooled_correlation(
    forecasts_by_instrument: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Average pairwise correlations across instruments.

    For each instrument, we compute the rule-rule correlation matrix using only
    the rows and columns that have non-zero variance (active rules).  We then
    average across instruments, counting only instruments where both rules of a
    pair are active.
    """
    # Collect all rule names
    all_rules: list[str] = []
    for fc in forecasts_by_instrument.values():
        for col in fc.columns:
            if col != "combined" and col not in all_rules:
                all_rules.append(col)

    n = len(all_rules)
    sum_corr = np.zeros((n, n))
    count = np.zeros((n, n))
    idx = {r: i for i, r in enumerate(all_rules)}

    for fc in forecasts_by_instrument.values():
        rule_cols = [c for c in fc.columns if c != "combined"]
        clean = fc[rule_cols].dropna()
        active = [c for c in rule_cols if clean[c].std() > 1e-6]
        if len(active) < 2:
            continue
        corr = clean[active].corr()
        for r1 in active:
            for r2 in active:
                i, j = idx[r1], idx[r2]
                sum_corr[i, j] += corr.loc[r1, r2]
                count[i, j] += 1

    pooled = np.where(count > 0, sum_corr / count, np.nan)
    return pd.DataFrame(pooled, index=all_rules, columns=all_rules)


def _print_corr(corr: pd.DataFrame) -> None:
    rules = list(corr.index)
    col_w = max(len(r) for r in rules) + 2
    header = f"  {'':>{col_w}}" + "".join(f"  {r[:8]:>8}" for r in rules)
    print(header)
    for r1 in rules:
        row = f"  {r1:>{col_w}}"
        for r2 in rules:
            v = corr.loc[r1, r2]
            row += f"  {v:>8.3f}" if not np.isnan(v) else f"  {'n/a':>8}"
        print(row)


def _suggest_weight_adjustment(
    corr: pd.DataFrame, base_weights: dict[str, float]
) -> dict[str, float]:
    """Refine within-family weights using observed correlations.

    For each family, we compute the average correlation of each rule with the
    other members of its sub-family.  If a rule has noticeably higher average
    correlation than siblings (>0.10 gap), reduce its weight proportionally.

    This is a lightweight implementation of Carver's handcrafting heuristic,
    not a full matrix inversion.  The family-level split is not changed here.
    """
    rules = list(corr.index)
    adjusted = dict(base_weights)

    for fam_name, sub_families in FAMILY_STRUCTURE.items():
        sub_fam_ws = SUBFAM_WEIGHTS[fam_name]
        fam_w = FAMILY_WEIGHTS[fam_name]

        for sub_fam, sub_w in zip(sub_families, sub_fam_ws):
            present = [r for r in sub_fam if r in rules]
            if len(present) < 2:
                continue
            # Average correlation of each rule with the rest of the sub-family
            avg_corrs = {}
            for r in present:
                others = [o for o in present if o != r]
                vals = [corr.loc[r, o] for o in others if not np.isnan(corr.loc[r, o])]
                avg_corrs[r] = float(np.mean(vals)) if vals else 0.0

            # Weight inversely by (1 + avg_corr) to penalise correlated members
            raw = {r: 1.0 / (1.0 + avg_corrs[r]) for r in present}
            total = sum(raw.values())
            for r in present:
                adjusted[r] = fam_w * sub_w * raw[r] / total

    return adjusted


def main(state_dir=None) -> None:
    scalars_data = st.load("step3a_scalars.yaml", state_dir=state_dir)
    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    split_date = compute_split_date(instruments)

    print(f"  IS window end: {split_date.date()}")
    print(f"  Instruments: {len(instruments)}\n")

    forecasts_by_instrument: dict[str, pd.DataFrame] = {}

    for code in instruments:
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) < 20:
            continue
        vol_is = daily_vol(is_prices)

        fc = combined_forecast(
            is_prices, vol_is, fdm=1.0,
            family_scalars=family_scalars,
            rule_weights=None,          # equal weights — we only need individual rule cols
            instrument_code=code,
        )
        forecasts_by_instrument[code] = fc

    # ── Correlation matrix ────────────────────────────────────────────────────
    corr = _pooled_correlation(forecasts_by_instrument)

    print("  Pooled IS rule forecast correlation matrix")
    print("  (averaged across instruments where both rules are active)\n")
    _print_corr(corr)

    # ── Per-rule instrument coverage ──────────────────────────────────────────
    all_rules = [c for c in list(corr.index)]
    print("\n  Active instrument count per rule (non-zero variance on IS data):")
    for rule in all_rules:
        count = sum(
            1 for fc in forecasts_by_instrument.values()
            if rule in fc.columns and fc[rule].std() > 1e-6
        )
        print(f"    {rule:<20} {count:>3} / {len(forecasts_by_instrument)}")

    # ── Handcrafted weights ───────────────────────────────────────────────────
    base_weights = _handcraft_weights()
    adjusted_weights = _suggest_weight_adjustment(corr, base_weights)

    print("\n  Suggested forecast weights:")
    print(f"  {'Rule':<20} {'Hierarchy':>10}  {'Corr-adjusted':>14}")
    print(f"  {'─' * 48}")
    for rule in all_rules:
        bw = base_weights.get(rule, 0.0)
        aw = adjusted_weights.get(rule, 0.0)
        print(f"  {rule:<20} {bw:>10.4f}  {aw:>14.4f}")
    total_base = sum(base_weights.get(r, 0.0) for r in all_rules)
    total_adj = sum(adjusted_weights.get(r, 0.0) for r in all_rules)
    print(f"  {'─' * 48}")
    print(f"  {'Total':<20} {total_base:>10.4f}  {total_adj:>14.4f}")

    print("\n  To use these weights, edit calibrate/state/step3d_forecast_weights.yaml:")
    print("  forecast_weights:")
    for rule, w in sorted(adjusted_weights.items(), key=lambda x: -x[1]):
        print(f"    {rule}: {round(w, 4)}")

    print(
        "\n  Note: family-level weights (Trend/Seasonality) and within-trend\n"
        "  sub-family weights are set in this script's FAMILY_WEIGHTS / SUBFAM_WEIGHTS\n"
        "  constants. Adjust those if the correlation matrix suggests a different split."
    )


if __name__ == "__main__":
    main()

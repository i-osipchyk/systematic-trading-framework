"""
Step 4a: Generate / validate instrument weights — two-pass hierarchical.

Pass 1: User sets group-level weights (step4a_group_weights.yaml).
Pass 2: Individual instrument weights are auto-derived and presented for
        final confirmation (step4a_instrument_weights.yaml).

Usage:
    uv run python calibrate/step4a_instrument_weights.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, traded_instruments
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series

GROUP_FILENAME = "step4a_group_weights.yaml"
FILENAME = "step4a_instrument_weights.yaml"
SUM_TOL = 0.005


def _get_groups() -> dict[str, list[str]]:
    """Build {asset_type: [code, ...]} from instruments.yaml, traded instruments only."""
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    groups: dict[str, list[str]] = {}
    for code in instruments:
        atype = cfgs[code].asset_type
        groups.setdefault(atype, []).append(code)
    return groups


def _write_group_template(
    group_to_instruments: dict[str, list[str]], state_dir=None
) -> None:
    """Write the group-level weights template with equal weights."""
    n_groups = len(group_to_instruments)
    weight = round(1.0 / n_groups, 3)
    groups = list(group_to_instruments.keys())

    lines = [
        "# Group-level instrument weights — Step 1 of 2",
        "# ─────────────────────────────────────────────────────────────────",
        "# Set the weight for each asset group. Must sum to 1.0.",
        "# Individual instrument weights (step 2) will be split equally within each group.",
        "#",
        "# Groups and their instruments:",
    ]
    for group, instruments in group_to_instruments.items():
        lines.append(f"#   {group} ({len(instruments)}): {', '.join(instruments)}")
    lines.append("#")
    lines.append("group_weights:")
    for i, group in enumerate(groups):
        n = len(group_to_instruments[group])
        w = weight
        if i == n_groups - 1:
            # Adjust last entry to ensure exact sum of 1.0
            w = round(1.0 - weight * (n_groups - 1), 3)
        lines.append(
            f"  {group}: {w:.3f}     # {n} instrument{'s' if n != 1 else ''}"
        )

    content = "\n".join(lines) + "\n"
    actual_path = st.path(GROUP_FILENAME, state_dir=state_dir)
    actual_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path.write_text(content)


def _validate_group_weights(
    group_to_instruments: dict[str, list[str]], data: dict
) -> list[str]:
    """Validate group weights: all groups present, non-negative, sum to 1.0."""
    errors: list[str] = []
    weights: dict = data.get("group_weights", {})
    if not weights:
        errors.append("  'group_weights' key missing or empty.")
        return errors

    for group in group_to_instruments:
        if group not in weights:
            errors.append(f"  Missing group: {group}")
        else:
            w = weights[group]
            if not isinstance(w, (int, float)) or w < 0:
                errors.append(
                    f"  {group}: weight must be a non-negative number, got {w!r}"
                )

    total = sum(float(weights.get(g, 0.0)) for g in group_to_instruments)
    if abs(total - 1.0) > SUM_TOL:
        errors.append(f"  Weights sum to {total:.4f} — must be 1.0 ± {SUM_TOL}")

    return errors


def _write_individual_template(
    group_to_instruments: dict[str, list[str]],
    group_weights: dict[str, float],
    state_dir=None,
) -> None:
    """Write individual instrument weights template derived from group weights."""
    lines = [
        "# Individual instrument weights — Step 2 of 2",
        "# ─────────────────────────────────────────────────────────────────",
        "# Derived from group_weights. Edit individual weights if needed.",
        "# Must sum to 1.0 (tolerance ±0.005).",
        "#",
        "instrument_weights:",
    ]
    for group, instruments in group_to_instruments.items():
        gw = group_weights.get(group, 0.0)
        n = len(instruments)
        per_inst = gw / n if n > 0 else 0.0
        lines.append(
            f"  # Group: {group} (group weight: {gw:.2f} → {per_inst:.4f} per instrument)"
        )
        for i, code in enumerate(instruments):
            if i == 0:
                comment = f"  # {group}: {gw:.2f} / {n}"
                lines.append(f"  {code}: {round(per_inst, 6)}{comment}")
            else:
                lines.append(f"  {code}: {round(per_inst, 6)}")

    content = "\n".join(lines) + "\n"
    actual_path = st.path(FILENAME, state_dir=state_dir)
    actual_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path.write_text(content)


def _validate_individual_weights(instruments: list[str], data: dict) -> list[str]:
    """Validate individual instrument weights: all instruments present, non-negative, sum to 1.0."""
    errors: list[str] = []
    weights: dict = data.get("instrument_weights", {})
    if not weights:
        errors.append("  'instrument_weights' key missing or empty.")
        return errors

    for code in instruments:
        if code not in weights:
            errors.append(f"  Missing instrument: {code}")
        else:
            w = weights[code]
            if not isinstance(w, (int, float)) or w < 0:
                errors.append(
                    f"  {code}: weight must be non-negative, got {w!r}"
                )

    total = sum(float(weights.get(c, 0.0)) for c in instruments)
    if abs(total - 1.0) > SUM_TOL:
        errors.append(f"  Weights sum to {total:.4f} — must be 1.0 ± {SUM_TOL}")

    return errors


def _print_and_report_corr(instruments: list[str], split_date, state_dir) -> None:
    """Print and save IS price-return correlation matrix before the user sets weights."""
    returns: dict[str, pd.Series] = {}
    for code in instruments:
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) >= 20:
            returns[code] = is_prices.pct_change().dropna()

    if not returns:
        return

    ret_df = pd.DataFrame(returns).dropna(how="all")
    corr = ret_df.corr(min_periods=20)
    codes = list(corr.columns)
    vals = corr.values
    vals = np.where(np.isnan(vals), 0.0, vals)
    np.fill_diagonal(vals, 1.0)

    col_w = max(len(c) for c in codes)
    SEP = "─" * 70
    print(f"\n  {SEP}")
    print("  INSTRUMENT RETURN CORRELATIONS  (IS price returns)")
    print(f"  {SEP}")
    print(f"  {'':>{col_w}}" + "".join(f"  {c:>{col_w}}" for c in codes))
    for i, r1 in enumerate(codes):
        row = f"  {r1:>{col_w}}"
        for j in range(len(codes)):
            row += f"  {vals[i, j]:>{col_w}.2f}"
        print(row)
    print()

    # Markdown report
    lines = ["# Step 4 Instrument Weights Report", "",
             "## Instrument Return Correlations  (IS price returns)", ""]
    lines.append("| |" + "".join(f" {c} |" for c in codes))
    lines.append("|---|" + "".join("---|" for _ in codes))
    for i, r1 in enumerate(codes):
        lines.append(f"| **{r1}** |" + "".join(f" {vals[i,j]:.2f} |" for j in range(len(codes))))
    lines.append("")

    report_path = st.path("step4_report.md", state_dir=state_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))
    print(f"  Saved → {report_path}")


def main(state_dir=None) -> None:
    group_to_instruments = _get_groups()
    all_instruments = [code for codes in group_to_instruments.values() for code in codes]

    split_date = compute_split_date(all_instruments)
    _print_and_report_corr(all_instruments, split_date, state_dir)

    # ── Pass 1: group-level weights ────────────────────────────────────────────
    if not st.exists(GROUP_FILENAME, state_dir=state_dir):
        _write_group_template(group_to_instruments, state_dir=state_dir)
        print(
            f"  Wrote group weights template → {st.path(GROUP_FILENAME, state_dir=state_dir)}"
        )

    print()
    print("  ACTION REQUIRED — Step 1 of 2: Group weights")
    print("  " + "─" * 50)
    print(f"  Edit the group weights file:")
    print(f"  {st.path(GROUP_FILENAME, state_dir=state_dir)}")
    print()
    for group, instruments in group_to_instruments.items():
        print(f"  {group} ({len(instruments)}): {', '.join(instruments)}")
    print()
    print("  Constraint: group weights must sum to 1.0")
    print()
    print("  Press Enter when done (Ctrl+C to abort)...")

    group_weights: dict[str, float] = {}
    while True:
        try:
            input()
        except KeyboardInterrupt:
            print("\n  Aborted.")
            sys.exit(1)
        except EOFError:
            raise

        if not st.exists(GROUP_FILENAME, state_dir=state_dir):
            print("  ERROR: file not found, please create it.")
            continue

        data = yaml.safe_load(st.path(GROUP_FILENAME, state_dir=state_dir).read_text())
        errors = _validate_group_weights(group_to_instruments, data)

        if errors:
            print()
            print("  VALIDATION ERRORS:")
            for e in errors:
                print(e)
            print()
            print("  Fix the errors above and press Enter again...")
        else:
            group_weights = {
                g: float(data["group_weights"][g]) for g in group_to_instruments
            }
            break

    # ── Pass 2: individual instrument weights ──────────────────────────────────
    # Always regenerate from current group weights (in case they changed)
    _write_individual_template(group_to_instruments, group_weights, state_dir=state_dir)
    print(f"\n  Derived individual weights → {st.path(FILENAME, state_dir=state_dir)}")

    print()
    print("  ACTION REQUIRED — Step 2 of 2: Individual instrument weights")
    print("  " + "─" * 50)
    print(f"  Review (and optionally edit) the individual weights file:")
    print(f"  {st.path(FILENAME, state_dir=state_dir)}")
    print()
    print("  Constraint: weights must sum to 1.0 (tolerance ±0.005)")
    print()
    print("  Press Enter when done (Ctrl+C to abort)...")

    final_weights: dict[str, float] = {}
    while True:
        try:
            input()
        except KeyboardInterrupt:
            print("\n  Aborted.")
            sys.exit(1)
        except EOFError:
            raise

        if not st.exists(FILENAME, state_dir=state_dir):
            print("  ERROR: file not found, please create it.")
            continue

        data = yaml.safe_load(st.path(FILENAME, state_dir=state_dir).read_text())
        errors = _validate_individual_weights(all_instruments, data)

        if errors:
            print()
            print("  VALIDATION ERRORS:")
            for e in errors:
                print(e)
            print()
            print("  Fix the errors above and press Enter again...")
        else:
            final_weights = {
                c: float(data["instrument_weights"][c]) for c in all_instruments
            }
            break

    # ── Print confirmation ─────────────────────────────────────────────────────
    print()
    print("  Instrument weights confirmed:")
    for group, instruments in group_to_instruments.items():
        group_total = sum(final_weights[c] for c in instruments)
        print(f"  Group: {group} (total: {group_total * 100:.1f}%)")
        for code in instruments:
            print(f"    {code:<8} {final_weights[code] * 100:.1f}%")
    print()
    print(f"  Instrument weights saved → {st.path(FILENAME, state_dir=state_dir)}")

    return {
        "group_weights": {
            grp: round(sum(final_weights[c] for c in codes), 6)
            for grp, codes in group_to_instruments.items()
        },
        "instrument_weights": {c: round(w, 6) for c, w in final_weights.items()},
    }


if __name__ == "__main__":
    main()

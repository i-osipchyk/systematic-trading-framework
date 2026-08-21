"""
Step 02: Generate / validate forecast weights — two-pass hierarchical.

Pass 1: User sets family-level weights (02_family_weights.yaml).
Pass 2: Individual rule weights are auto-derived and presented for
        final confirmation (02_forecast_weights.yaml).

Usage:
    uv run python calibrate/02_forecast_weights.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_rules_config
from src.calibration import state as st

FAMILY_FILENAME = "02_family_weights.yaml"
FILENAME = "02_forecast_weights.yaml"
SUM_TOL = 0.005


def _build_family_to_rules(scalars_data: dict, rules_cfg: dict) -> dict[str, list[str]]:
    """Build {family_name: [rule_name, ...]} from scalars and rules config."""
    family_to_rules: dict[str, list[str]] = {}

    ewmac_keys = list(scalars_data.get("ewmac", {}).keys())
    ewmac_family = rules_cfg.get("ewmac", {}).get("family", "ema_crossover")
    rule_names_ewmac = [f"EWMAC_{k}" for k in ewmac_keys]
    if rule_names_ewmac:
        family_to_rules[ewmac_family] = rule_names_ewmac

    mr_keys = list(scalars_data.get("mr", {}).keys())
    mr_family = rules_cfg.get("mr", {}).get("family", "mean_reversion")
    rule_names_mr = [f"MR_{k}" for k in mr_keys]
    if rule_names_mr:
        family_to_rules[mr_family] = rule_names_mr

    return family_to_rules


def _write_family_template(family_to_rules: dict[str, list[str]], state_dir=None) -> None:
    """Write the family-level weights template."""
    n_families = len(family_to_rules)
    weight = round(1.0 / n_families, 3)
    families = list(family_to_rules.keys())

    lines = [
        "# Family-level forecast weights — Step 1 of 2",
        "# ─────────────────────────────────────────────────────────────────",
        "# Set the weight for each rule family. Must sum to 1.0.",
        "# Individual rule weights (step 2) will be derived proportionally.",
        "#",
        "# Families and their rules:",
    ]
    for family, rules in family_to_rules.items():
        lines.append(f"#   {family} ({len(rules)} rules): {', '.join(rules)}")
    lines.append("#")
    lines.append("family_weights:")
    for i, family in enumerate(families):
        w = weight
        if i == n_families - 1:
            # Adjust last entry to ensure exact sum of 1.0
            w = round(1.0 - weight * (n_families - 1), 3)
        lines.append(f"  {family}: {w:.3f}   # edit this")

    content = "\n".join(lines) + "\n"
    actual_path = st.path(FAMILY_FILENAME, state_dir=state_dir)
    actual_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path.write_text(content)


def _validate_family_weights(
    family_to_rules: dict[str, list[str]], data: dict
) -> list[str]:
    """Validate family weights: all families present, non-negative, sum to 1.0."""
    errors: list[str] = []
    weights: dict = data.get("family_weights", {})
    if not weights:
        errors.append("  'family_weights' key missing or empty.")
        return errors

    for family in family_to_rules:
        if family not in weights:
            errors.append(f"  Missing family: {family}")
        else:
            w = weights[family]
            if not isinstance(w, (int, float)) or w < 0:
                errors.append(
                    f"  {family}: weight must be a non-negative number, got {w!r}"
                )

    total = sum(float(weights.get(f, 0.0)) for f in family_to_rules)
    if abs(total - 1.0) > SUM_TOL:
        errors.append(f"  Weights sum to {total:.4f} — must be 1.0 ± {SUM_TOL}")

    return errors


def _write_individual_template(
    family_to_rules: dict[str, list[str]],
    family_weights: dict[str, float],
    state_dir=None,
) -> None:
    """Write individual rule weights template derived from family weights."""
    lines = [
        "# Individual forecast weights — Step 2 of 2",
        "# ─────────────────────────────────────────────────────────────────",
        "# Derived from family_weights. Edit individual weights if needed.",
        "# Must sum to 1.0 (tolerance ±0.005).",
        "#",
        "forecast_weights:",
    ]
    for family, rules in family_to_rules.items():
        fw = family_weights.get(family, 0.0)
        n = len(rules)
        per_rule = fw / n if n > 0 else 0.0
        lines.append(
            f"  # Family: {family} (family weight: {fw:.2f} → {per_rule:.4f} per rule)"
        )
        for i, rule in enumerate(rules):
            if i == 0:
                comment = f"  # {family}: {fw:.2f} / {n}"
                lines.append(f"  {rule}: {round(per_rule, 6)}{comment}")
            else:
                lines.append(f"  {rule}: {round(per_rule, 6)}")

    content = "\n".join(lines) + "\n"
    actual_path = st.path(FILENAME, state_dir=state_dir)
    actual_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path.write_text(content)


def _validate_individual_weights(rule_names: list[str], data: dict) -> list[str]:
    """Validate individual forecast weights: all rules present, non-negative, sum to 1.0."""
    errors: list[str] = []
    weights: dict = data.get("forecast_weights", {})
    if not weights:
        errors.append("  'forecast_weights' key missing or empty.")
        return errors

    for rule in rule_names:
        if rule not in weights:
            errors.append(f"  Missing rule: {rule}")
        else:
            w = weights[rule]
            if not isinstance(w, (int, float)) or w < 0:
                errors.append(
                    f"  {rule}: weight must be a non-negative number, got {w!r}"
                )

    total = sum(float(weights.get(r, 0.0)) for r in rule_names)
    if abs(total - 1.0) > SUM_TOL:
        errors.append(f"  Weights sum to {total:.4f} — must be 1.0 ± {SUM_TOL}")

    return errors


def main(state_dir=None) -> None:
    # ── Load state ─────────────────────────────────────────────────────────────
    scalars_data = st.load("01_scalars.yaml", state_dir=state_dir)
    rules_cfg = load_rules_config()
    family_to_rules = _build_family_to_rules(scalars_data, rules_cfg)
    all_rule_names = [r for rules in family_to_rules.values() for r in rules]

    # ── Pass 1: family-level weights ───────────────────────────────────────────
    if not st.exists(FAMILY_FILENAME, state_dir=state_dir):
        _write_family_template(family_to_rules, state_dir=state_dir)
        print(f"  Wrote family weights template → {st.path(FAMILY_FILENAME, state_dir=state_dir)}")

    print()
    print("  ACTION REQUIRED — Step 1 of 2: Family weights")
    print("  " + "─" * 50)
    print(f"  Edit the family weights file:")
    print(f"  {st.path(FAMILY_FILENAME, state_dir=state_dir)}")
    print()
    for family, rules in family_to_rules.items():
        print(f"  {family} ({len(rules)} rules): {', '.join(rules)}")
    print()
    print("  Constraint: family weights must sum to 1.0")
    print()
    print("  Press Enter when done (Ctrl+C to abort)...")

    family_weights: dict[str, float] = {}
    while True:
        try:
            input()
        except KeyboardInterrupt:
            print("\n  Aborted.")
            sys.exit(1)
        except EOFError:
            raise

        if not st.exists(FAMILY_FILENAME, state_dir=state_dir):
            print("  ERROR: file not found, please create it.")
            continue

        data = yaml.safe_load(st.path(FAMILY_FILENAME, state_dir=state_dir).read_text())
        errors = _validate_family_weights(family_to_rules, data)

        if errors:
            print()
            print("  VALIDATION ERRORS:")
            for e in errors:
                print(e)
            print()
            print("  Fix the errors above and press Enter again...")
        else:
            family_weights = {
                f: float(data["family_weights"][f]) for f in family_to_rules
            }
            break

    # ── Pass 2: individual rule weights ────────────────────────────────────────
    # Always regenerate from current family weights (in case they changed)
    _write_individual_template(family_to_rules, family_weights, state_dir=state_dir)
    print(f"\n  Derived individual weights → {st.path(FILENAME, state_dir=state_dir)}")

    print()
    print("  ACTION REQUIRED — Step 2 of 2: Individual rule weights")
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
        errors = _validate_individual_weights(all_rule_names, data)

        if errors:
            print()
            print("  VALIDATION ERRORS:")
            for e in errors:
                print(e)
            print()
            print("  Fix the errors above and press Enter again...")
        else:
            final_weights = {
                r: float(data["forecast_weights"][r]) for r in all_rule_names
            }
            break

    # ── Print confirmation ─────────────────────────────────────────────────────
    print()
    print("  Forecast weights confirmed:")
    for family, rules in family_to_rules.items():
        family_total = sum(final_weights[r] for r in rules)
        print(f"  Family: {family} (total: {family_total * 100:.1f}%)")
        for rule in rules:
            print(f"    {rule:<16} {final_weights[rule] * 100:.1f}%")
    print()
    print(f"  Forecast weights saved → {st.path(FILENAME, state_dir=state_dir)}")

    return {
        "family_weights": {
            fam: round(sum(final_weights[r] for r in rules), 6)
            for fam, rules in family_to_rules.items()
        },
        "forecast_weights": {r: round(w, 6) for r, w in final_weights.items()},
    }


if __name__ == "__main__":
    main()

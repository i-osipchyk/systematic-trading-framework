"""Formats a step's raw `values` dict (as stored in run_log.yaml) into a
single short line for the frontend, instead of the full console log.
"""
from __future__ import annotations

def format_step0(values: dict) -> str | None:
    if not values:
        return None
    up_to_date, needs_update, missing = values.get("up_to_date", 0), values.get("needs_update", 0), values.get("missing", 0)
    if needs_update == 0 and missing == 0:
        return f"All {up_to_date} instruments up to date."
    return f"{up_to_date} up to date, {needs_update} updated, {missing} fetched."


def format_step1(values: dict) -> list[str] | None:
    """One line per asset class, so the breakdown reads as a short list, not a run-on sentence."""
    if not values:
        return None
    instruments = values.get("instruments", [])
    n = values.get("n_traded", len(instruments))
    groups = values.get("asset_groups")
    if not groups:  # fallback for run_log entries written before asset_groups existed
        return [f"Confirmed {n} instruments: {', '.join(instruments)}"]
    lines = [f"Confirmed {n} instruments across {len(groups)} asset classes:"]
    lines += [f"{group.title()}: {', '.join(codes)}" for group, codes in groups.items()]
    return lines


def format_step2(values: dict) -> list[str] | None:
    """One line per rule family, so the breakdown reads as a short list, not a run-on sentence."""
    if not values:
        return None
    n_families, n_variants = values.get("n_families", 0), values.get("n_variants", 0)
    variants = values.get("family_variants")
    if not variants:  # fallback for run_log entries written before family_variants existed
        families = values.get("families")
        base = f"Confirmed {n_families} families / {n_variants} variants"
        return [f"{base}: {', '.join(families)}" if families else base]
    lines = [f"Confirmed {n_families} rule families, {n_variants} variants:"]
    lines += [
        f"{family.title()}: {', '.join(labels)}" if labels else family.title()
        for family, labels in variants.items()
    ]
    return lines


def format_step3(values: dict) -> str | None:
    fdm = values.get("fdm")
    weights = values.get("forecast_weights")
    if not fdm or not weights:
        return None
    weights_str = ", ".join(f"{k}={v:.2f}" for k, v in weights.items())
    fdm_values = list(fdm.values())
    fdm_range = f"{min(fdm_values):.2f}–{max(fdm_values):.2f} (avg {sum(fdm_values) / len(fdm_values):.2f})"
    return f"Forecast weights: {weights_str} | FDM {fdm_range}"


def format_step4(values: dict) -> str | None:
    group_weights = values.get("group_weights")
    if not group_weights:
        return None
    groups_str = ", ".join(f"{g} {w:.0%}" for g, w in group_weights.items())
    idm = values.get("idm")
    if idm is None:
        return f"Groups: {groups_str}"
    return f"Groups: {groups_str} | IDM {idm:.2f}"


def format_step5(values: dict) -> str | None:
    if "is_sharpe" not in values:
        return None
    return (
        f"IS Sharpe {values['is_sharpe']:.2f} | Realistic SR {values['realistic_sr']:.2f} "
        f"| Vol target {values['vol_target']:.0%}"
    )


def format_oos(values: dict) -> str | None:
    if "is_sr" not in values:
        return None
    base = f"SR — IS {values['is_sr']:.2f} / Test {values['test_sr']:.2f}"
    weak = values.get("test_weak_flags") or []
    if not weak:
        return base
    return f"{base} | {len(weak)} weak: {', '.join(weak)}"

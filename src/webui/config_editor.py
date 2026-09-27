"""Read/write the editable weight & vol-target sections of step3/4/5.yaml.

These are the fields CLAUDE.md calls "AI edits" / "USER EDITS" / "USER INPUT" —
forecast_weights (Step 3), group_weights / instrument_weights (Step 4), and
vol_target (Step 5). Historically these required hand-editing YAML on disk;
this module lets the frontend write them directly, in the exact shape the
calibrate/step3_rules.py / step4a_instrument_weights.py / step5_calibrate.py
scripts expect, so a save here is a drop-in replacement for a hand edit — the
existing "Run" button then recomputes downstream derived values (FDM / IDM)
from what was saved, exactly as it would from a manual edit.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from calibrate.oos_validation import run_oos_backtest
from calibrate.step5_calibrate import run_is_backtest
from src.calibration import state as st

SUM_TOL = 0.005


def _config_dir(system_dir: Path) -> Path:
    return Path(system_dir) / "config"


def _validate_sum_to_one(weights: dict[str, float]) -> list[str]:
    errors = []
    for name, w in weights.items():
        if not isinstance(w, (int, float)) or w < 0:
            errors.append(f"{name}: weight must be a non-negative number, got {w!r}")
    total = sum(float(w) for w in weights.values())
    if abs(total - 1.0) > SUM_TOL:
        errors.append(f"Weights sum to {total:.4f} — must be 1.0 ± {SUM_TOL}")
    return errors


# ── Step 3: forecast weights ─────────────────────────────────────────────────

def rule_family(rule_name: str) -> str:
    """'EWMAC_32_128' -> 'EWMAC', 'MR_10' -> 'MR', 'SEASONALITY' -> 'SEASONALITY'."""
    return rule_name.split("_")[0]


def read_forecast_weights(system_dir: Path) -> dict[str, float] | None:
    config_dir = _config_dir(system_dir)
    if not st.has_section("step3.yaml", "forecast_weights", state_dir=config_dir):
        return None
    raw = st.load_section("step3.yaml", "forecast_weights", state_dir=config_dir)
    return {k: float(v) for k, v in raw.items()}


def forecast_weight_families(weights: dict[str, float]) -> dict[str, list[str]]:
    """Group rule names by family, preserving first-seen order."""
    families: dict[str, list[str]] = {}
    for name in weights:
        families.setdefault(rule_family(name), []).append(name)
    return families


def split_family_budgets_equally(
    weights: dict[str, float], family_budgets: dict[str, float]
) -> dict[str, float]:
    """Redistribute each family's budget equally across its current variants."""
    families = forecast_weight_families(weights)
    result: dict[str, float] = {}
    for family, names in families.items():
        budget = float(family_budgets.get(family, 0.0))
        per = budget / len(names) if names else 0.0
        for name in names:
            result[name] = per
    return result


def write_forecast_weights(system_dir: Path, weights: dict[str, float]) -> None:
    errors = _validate_sum_to_one(weights)
    if errors:
        raise ValueError("; ".join(errors))
    config_dir = _config_dir(system_dir)
    st.save_section(
        "step3.yaml", "forecast_weights",
        {k: round(float(v), 6) for k, v in weights.items()},
        state_dir=config_dir,
    )


# ── Step 4: group / instrument weights ───────────────────────────────────────

def instrument_groups(system_dir: Path) -> dict[str, list[str]]:
    """{asset_type: [code, ...]} from instruments.yaml, traded instruments only."""
    instruments_path = _config_dir(system_dir) / "instruments.yaml"
    if not instruments_path.exists():
        return {}
    raw = yaml.safe_load(instruments_path.read_text()) or {}
    groups: dict[str, list[str]] = {}
    for code, cfg in raw.get("instruments", {}).items():
        if not cfg.get("traded", True):
            continue
        groups.setdefault(cfg.get("asset_type", "other"), []).append(code)
    return groups


def read_group_weights(system_dir: Path) -> dict[str, float] | None:
    config_dir = _config_dir(system_dir)
    if not st.has_section("step4.yaml", "group_weights", state_dir=config_dir):
        return None
    raw = st.load_section("step4.yaml", "group_weights", state_dir=config_dir)
    return {k: float(v) for k, v in raw.items()}


def write_group_weights(system_dir: Path, group_weights: dict[str, float]) -> None:
    errors = _validate_sum_to_one(group_weights)
    if errors:
        raise ValueError("; ".join(errors))
    config_dir = _config_dir(system_dir)
    st.save_section(
        "step4.yaml", "group_weights",
        {k: round(float(v), 6) for k, v in group_weights.items()},
        state_dir=config_dir,
    )


def read_instrument_weights(system_dir: Path) -> dict[str, float] | None:
    config_dir = _config_dir(system_dir)
    if not st.has_section("step4.yaml", "instrument_weights", state_dir=config_dir):
        return None
    raw = st.load_section("step4.yaml", "instrument_weights", state_dir=config_dir)
    return {k: float(v) for k, v in raw.items()}


def write_instrument_weights(system_dir: Path, instrument_weights: dict[str, float]) -> None:
    errors = _validate_sum_to_one(instrument_weights)
    if errors:
        raise ValueError("; ".join(errors))
    config_dir = _config_dir(system_dir)
    st.save_section(
        "step4.yaml", "instrument_weights",
        {k: round(float(v), 6) for k, v in instrument_weights.items()},
        state_dir=config_dir,
    )


def reset_instrument_weights(system_dir: Path) -> None:
    """Drop instrument_weights so the next Step 4 run re-derives an equal split within each group."""
    config_dir = _config_dir(system_dir)
    st.delete_section("step4.yaml", "instrument_weights", state_dir=config_dir)


# ── Step 5: vol target ────────────────────────────────────────────────────────

VOL_TARGET_MIN = 0.02
VOL_TARGET_MAX = 0.50


def read_vol_target(system_dir: Path) -> float | None:
    config_dir = _config_dir(system_dir)
    if not st.has_section("step5.yaml", "vol_target", state_dir=config_dir):
        return None
    return float(st.load_section("step5.yaml", "vol_target", state_dir=config_dir))


def write_vol_target(system_dir: Path, vol_target: float) -> None:
    if not (VOL_TARGET_MIN <= vol_target <= VOL_TARGET_MAX):
        raise ValueError(
            f"vol_target {vol_target} out of range [{VOL_TARGET_MIN}, {VOL_TARGET_MAX}]"
        )
    config_dir = _config_dir(system_dir)
    st.save_section("step5.yaml", "vol_target", round(float(vol_target), 4), state_dir=config_dir)


def can_preview_backtest(system_dir: Path) -> bool:
    """True once Steps 3-4 have produced everything run_is_backtest() needs."""
    config_dir = _config_dir(system_dir)
    return (
        st.has_section("step3.yaml", "forecast_weights", state_dir=config_dir)
        and st.has_section("step3.yaml", "fdm", state_dir=config_dir)
        and st.has_section("step4.yaml", "instrument_weights", state_dir=config_dir)
        and st.has_section("step4.yaml", "idm", state_dir=config_dir)
    )


def preview_vol_target(system_dir: Path, vol_target: float) -> dict:
    """Actually re-run the IS portfolio backtest at vol_target, rather than rescale a
    single reference run — lot rounding and inertia buffering (src/backtest/sizing.py)
    are nonlinear in vol_target, so this is the real SR/drawdown/equity curve for the
    target being tried, not an approximation. Fast enough (seconds) to call once per
    vol target a user tries interactively.
    """
    config_dir = _config_dir(system_dir)
    return run_is_backtest(vol_target, state_dir=config_dir)


# ── OOS validation ('Step 6') ─────────────────────────────────────────────────

def preview_oos(system_dir: Path, vol_target: float, include_all: bool = False) -> dict:
    """Re-run the OOS validation backtest at vol_target and return structured
    instrument/asset-class/rule/family tables plus a combined equity curve —
    see calibrate/oos_validation.run_oos_backtest() for the full shape.
    """
    config_dir = _config_dir(system_dir)
    return run_oos_backtest(vol_target, state_dir=config_dir, include_all=include_all)

"""Builds a system's rule selection (CLAUDE.md Step 2) from the frontend.

The candidate catalog (systems/defaults/config/rules.yaml) is the wide
starting set of rule families/variants Step 2 narrows down. Building a rule
selection means picking a subset of families, and within each parametrized
family (ewmac/breakout/tsmom/mr) a subset of its variants.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[2]
DEFAULT_RULES_CATALOG_PATH = REPO_ROOT / "systems" / "defaults" / "config" / "rules.yaml"

_VARIANT_KEYS = ("pairs", "lookbacks", "spans")

# Structural correlation risks from CLAUDE.md's Step 2 guidance — fixed priors
# from prior builds, not fitted results, so surfacing them isn't performance
# based pruning. Only the redundant/cancelling pairs are listed; the
# genuinely-diversifying pairs (e.g. ewmac vs seasonality/carry) need no flag.
_FAMILY_CORRELATION_RISKS: list[tuple[frozenset[str], str]] = [
    (frozenset({"ewmac", "breakout"}),
     "0.85–0.90 — nearly identical momentum logic; keep only one unless speeds differ meaningfully"),
    (frozenset({"ewmac", "tsmom"}),
     "0.80–0.85 — also structurally redundant with EWMAC"),
    (frozenset({"ewmac", "mr"}),
     "-0.80 to -0.90 at matching timescales — cancellation, not diversification; avoid"),
]


def load_candidate_rules(catalog_path: Path = DEFAULT_RULES_CATALOG_PATH) -> dict[str, dict]:
    """Parse the rules: section of a rules-catalog yaml, in file order."""
    raw = yaml.safe_load(Path(catalog_path).read_text()) or {}
    return raw.get("rules", {})


def _variant_key(cfg: dict) -> str | None:
    for key in _VARIANT_KEYS:
        if key in cfg:
            return key
    return None


def family_variants(family: str, cfg: dict) -> list[str] | None:
    """Return variant labels for a parametrized family, or None (carry, seasonality)."""
    key = _variant_key(cfg)
    if key is None:
        return None
    values = cfg[key]
    if key == "pairs":
        return [f"{p[0]}_{p[1]}" for p in values]
    return [str(v) for v in values]


def rule_correlation_hints(selected_families: set[str]) -> list[str]:
    """Return a note for each known risky pair with both families selected."""
    hints = []
    for pair, note in _FAMILY_CORRELATION_RISKS:
        if pair <= selected_families:
            a, b = sorted(pair)
            hints.append(f"{a}, {b}: {note}")
    return hints


def _traded_instruments(system_dir: Path) -> list[str]:
    instruments_path = Path(system_dir) / "config" / "instruments.yaml"
    if not instruments_path.exists():
        return []
    raw = yaml.safe_load(instruments_path.read_text()) or {}
    instruments = raw.get("instruments", {})
    return [code for code, cfg in instruments.items() if cfg.get("traded", True)]


def build_rules(
    system_dir: Path,
    selected_families: dict[str, list[str]],
    catalog: dict[str, dict] | None = None,
) -> Path:
    """Write config/rules.yaml for system_dir from a family -> chosen-variant-labels map.

    A family with an empty label list (carry, seasonality) is included as-is;
    seasonality's instrument list is derived from the system's own
    instruments.yaml (traded=true) rather than from the catalog, since it
    should always match that system's Step 1 universe.
    """
    if not selected_families:
        raise ValueError("Select at least one rule family.")
    if catalog is None:
        catalog = load_candidate_rules()

    config_dir = Path(system_dir) / "config"
    if not config_dir.is_dir():
        raise FileNotFoundError(
            f"No config/ directory at {config_dir} — build the universe (Step 1) first."
        )

    rules: dict[str, dict] = {}
    for family, chosen_labels in selected_families.items():
        if family not in catalog:
            raise ValueError(f"Unknown rule family: {family!r}")
        cfg = catalog[family]
        variants = family_variants(family, cfg)

        if variants is None:  # atomic family: carry, seasonality
            if family == "seasonality":
                instruments = _traded_instruments(system_dir)
                rules[family] = {"instruments": instruments} if instruments else {}
            else:
                rules[family] = {}
            continue

        key = _variant_key(cfg)
        chosen_values = [v for v, label in zip(cfg[key], variants) if label in chosen_labels]
        if not chosen_values:
            raise ValueError(f"Select at least one variant for {family!r}.")
        rules[family] = {key: chosen_values}

    rules_path = config_dir / "rules.yaml"
    rules_path.write_text(yaml.dump({"rules": rules}, default_flow_style=False, sort_keys=False))
    return rules_path

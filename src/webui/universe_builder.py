"""Builds a new system's instrument universe (CLAUDE.md Step 1) from the frontend.

The candidate catalog (config/universe_default.yaml) is a pre-vetted list of
instruments with full metadata (pointsize, spread_cost, currency, asset_type).
Building a universe means picking a subset of it; rules.yaml/base.yaml are
copied from a template system so the result is a runnable system scaffold.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[2]
DEFAULT_CATALOG_PATH = REPO_ROOT / "config" / "universe_default.yaml"

# Structural correlation priors from CLAUDE.md's Step 1 guidance — these are
# fixed historical priors, not fitted results, so surfacing them here isn't
# performance-based pruning.
_CORRELATION_CLUSTERS: list[tuple[frozenset[str], str]] = [
    (frozenset({"US500", "NAS100", "US30"}), "0.80–0.90 — treat as one unit in handcrafting"),
    (frozenset({"US500", "GER40", "UK100"}), "US vs EU equities: 0.50–0.65"),
    (frozenset({"US2YR", "US5YR", "US10YR", "US30YR"}), "0.70–0.90 within the curve; duration sub-groups"),
    (frozenset({"BUND", "US10YR"}), "0.30–0.50 (different central bank, genuinely diversifying)"),
    (frozenset({"XAU", "XAG"}), "0.70–0.80"),
    (frozenset({"Corn", "Coffee", "Sugar", "Cotton", "Soybeans"}), "0.20–0.45 — lower than metals"),
    (frozenset({"BTC", "ETH"}), "0.60–0.70"),
]


def load_candidate_catalog(catalog_path: Path = DEFAULT_CATALOG_PATH) -> dict[str, dict]:
    """Parse the instruments: section of a universe-catalog yaml, in file order."""
    raw = yaml.safe_load(Path(catalog_path).read_text()) or {}
    return raw.get("instruments", {})


def correlation_hints(selected_codes: set[str]) -> list[str]:
    """Return a note for each known cluster with >=2 of its members selected."""
    hints = []
    for cluster, note in _CORRELATION_CLUSTERS:
        members = sorted(cluster & selected_codes)
        if len(members) >= 2:
            hints.append(f"{', '.join(members)}: {note}")
    return hints


_VERSION_RE = re.compile(r"^universe_v(\d+)$")


def next_system_name(systems_root: Path, prefix: str = "universe_v") -> str:
    """Suggest the next universe_vN name, one past the highest existing N."""
    root = Path(systems_root)
    if not root.is_dir():
        return f"{prefix}1"
    versions = [
        int(m.group(1)) for p in root.iterdir() if p.is_dir()
        for m in [_VERSION_RE.match(p.name)] if m
    ]
    return f"{prefix}{max(versions) + 1 if versions else 1}"


def build_system(
    systems_root: Path,
    name: str,
    selected_codes: list[str],
    catalog: dict[str, dict] | None = None,
    template_system: str = "defaults",
) -> Path:
    """Create systems/<name>/config/ from selected catalog instruments + a template.

    instruments.yaml gets only the selected codes (equal-weight placeholders,
    traded: true), in catalog order. rules.yaml and base.yaml are copied
    verbatim from systems/<template_system>/config/ — Step 2's rule selection
    is a separate discussion, not decided here.
    """
    if not selected_codes:
        raise ValueError("Select at least one instrument to build a universe.")
    if catalog is None:
        catalog = load_candidate_catalog()

    root = Path(systems_root)
    system_dir = root / name
    if system_dir.exists():
        raise FileExistsError(f"System already exists: {system_dir}")

    selected = set(selected_codes)
    n = len(selected)
    weight = round(1.0 / n, 4)
    instruments = {}
    for code, meta in catalog.items():
        if code not in selected:
            continue
        entry = {k: v for k, v in meta.items() if k not in ("weight", "traded")}
        entry["weight"] = weight
        entry["traded"] = True
        instruments[code] = entry

    config_dir = system_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "instruments.yaml").write_text(
        yaml.dump({"instruments": instruments}, default_flow_style=False, sort_keys=False)
    )

    template_config = root / template_system / "config"
    for filename in ("rules.yaml", "base.yaml"):
        src = template_config / filename
        if src.exists():
            (config_dir / filename).write_text(src.read_text())

    return system_dir

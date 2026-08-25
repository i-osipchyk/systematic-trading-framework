"""
Step 4a: Correlation-based hierarchical instrument weight computation.

Follows the handcrafting tree from docs/decisions/step1_instrument_selection.md.

Algorithm at each level of the tree:
  1. Compute the equal-weight IS return for each sub-group (leaves pooled).
  2. Compute pairwise correlations between sibling sub-groups.
  3. Weight each sibling by  1 / (1 + mean_corr_with_siblings), normalised.
  4. Recurse into each sub-group with its allocated budget.

This ensures that highly-correlated siblings share a smaller combined budget
while uncorrelated siblings each receive a full budget allocation.

The top-level asset-class split (FX / Equities / Bonds / Commodities) is also
correlation-adjusted — not equal weight — consistent with the rest of the tree.

Output: calibrate/state/step4a_instrument_weights.yaml
Usage:
    TRADING_CONFIG=config/universe_v2.yaml uv run python calibrate/step4a_handcraft.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.backtest.config import load_instrument_configs, traded_instruments

OUTPUT_FILE = "step4a_instrument_weights.yaml"

# ── Handcrafting tree ─────────────────────────────────────────────────────────
# Leaves: list of instrument codes (equal weight within the leaf).
# Branches: dict of {name: sub-tree}.
# At every branch the algorithm computes inter-sibling correlations and weights
# inversely — more-correlated siblings share a smaller combined budget.

TREE: dict = {
    "Equities": {
        "US": ["US500", "NAS100"],
        "European": ["GER40", "UK100"],
        "JPN225": ["JPN225"],
        "HK50": ["HK50"],
    },
    "Bonds": {
        "US rates": ["US2YR", "US5YR", "US10YR", "US30YR"],
        "BUND": ["BUND"],
    },
    "Financial Commodities": {
        "Precious metals": ["XAU", "XAG"],
        "COPPER": ["COPPER"],
        "Energy": ["SpotCrude", "Gasoline"],
    },
    "Ags": {
        "Grains": ["Corn", "Soybeans", "Wheat"],
        "Tropical softs": ["Coffee", "Cocoa", "Sugar", "Cotton"],
    },
}


def _get_leaves(node: list | dict) -> list[str]:
    if isinstance(node, list):
        return node
    return [c for child in node.values() for c in _get_leaves(child)]


def _equal_weight_return(codes: list[str], returns: dict[str, pd.Series]) -> pd.Series:
    available = [c for c in codes if c in returns]
    if not available:
        return pd.Series(dtype=float)
    return pd.concat([returns[c] for c in available], axis=1).mean(axis=1)


def _corr_adjusted_budget(
    children: list[tuple[str, list | dict]],
    returns: dict[str, pd.Series],
    budget: float,
    label: str,
    level: int,
) -> dict[str, float]:
    """Distribute budget among siblings using correlation-adjusted weights."""
    # Build equal-weight return series for each child
    child_returns: dict[str, pd.Series] = {}
    for name, subtree in children:
        leaves = _get_leaves(subtree)
        r = _equal_weight_return(leaves, returns)
        if not r.empty:
            child_returns[name] = r

    present = list(child_returns.keys())
    k_total = len(children)

    if len(present) < 2:
        return {name: budget / k_total for name, _ in children}

    child_df = pd.concat(child_returns, axis=1).dropna()
    if len(child_df) < 20:
        return {name: budget / k_total for name, _ in children}

    corr = child_df.corr()

    # Print correlation info
    indent = "  " * (level + 1)
    print(f"\n{indent}[{label}] sub-group correlations:")
    for i, n1 in enumerate(present):
        for j, n2 in enumerate(present):
            if i < j:
                print(f"{indent}  {n1} ↔ {n2}: {corr.loc[n1, n2]:+.3f}")

    # 1/(1 + mean_corr_with_siblings) weighting
    avg_corrs: dict[str, float] = {}
    for name in present:
        others = [o for o in present if o != name]
        avg_corrs[name] = float(corr.loc[name, others].mean()) if others else 0.0

    inv = {name: 1.0 / (1.0 + avg_corrs[name]) for name in present}
    total = sum(inv.values())

    weights: dict[str, float] = {}
    for name in present:
        weights[name] = budget * inv[name] / total
    for name, _ in children:
        weights.setdefault(name, 0.0)

    indent2 = indent + "  "
    print(f"{indent}  → allocated weights:")
    for name, _ in children:
        avc = avg_corrs.get(name, 0.0)
        print(f"{indent2}{name}: {weights[name]*100:.1f}%  (avg sibling corr {avc:+.3f})")

    return weights


def _allocate(
    node: list | dict,
    returns: dict[str, pd.Series],
    budget: float,
    label: str = "Portfolio",
    level: int = 0,
) -> dict[str, float]:
    """Recursively allocate budget to leaf instruments."""
    if isinstance(node, list):
        available = [c for c in node if c in returns]
        if not available:
            return {}
        per = budget / len(available)
        return {c: per for c in available}

    children = list(node.items())
    child_budgets = _corr_adjusted_budget(children, returns, budget, label, level)

    result: dict[str, float] = {}
    for name, subtree in children:
        b = child_budgets.get(name, 0.0)
        result.update(_allocate(subtree, returns, b, label=name, level=level + 1))
    return result


def main(state_dir=None) -> None:
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    split_date = compute_split_date(instruments)

    print(f"  IS window end: {split_date.date()}")
    print(f"  Instruments: {len(instruments)}")
    print("\n  Loading IS returns...")

    returns: dict[str, pd.Series] = {}
    for code in instruments:
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) < 20:
            continue
        # Use vol-normalised returns so short-vol instruments don't dominate correlations
        r = is_prices.pct_change().dropna()
        roll_std = r.rolling(60, min_periods=20).std()
        r_norm = (r / roll_std).dropna()
        returns[code] = r_norm

    print(f"  Loaded {len(returns)} instruments with IS data.\n")

    # Wrap the entire tree in a root node so the top-level is also correlation-adjusted
    root: dict = TREE

    print("  Computing correlation-based hierarchical weights...")
    weights = _allocate(root, returns, budget=1.0, label="Portfolio", level=0)

    # Normalise to sum exactly to 1
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("  Final instrument weights")
    print("─" * 60)
    for class_name, subtree in TREE.items():
        leaves = _get_leaves(subtree)
        class_w = sum(weights.get(c, 0.0) for c in leaves)
        print(f"\n  {class_name}  ({class_w*100:.1f}%)")
        for code in leaves:
            if code in weights:
                print(f"    {code:<12} {weights[code]*100:5.2f}%")
    total_check = sum(weights.values())
    print(f"\n  Total: {total_check*100:.2f}%")

    # ── Build YAML ────────────────────────────────────────────────────────────
    lines = [
        "# Instrument weights — Step 4 (correlation-based hierarchical handcrafting)",
        "# ─────────────────────────────────────────────────────────────────────────",
        "# Weights derived from IS vol-normalised return correlations.",
        "# At each level of the tree, siblings are weighted by 1/(1+mean_sibling_corr),",
        "# so correlated clusters share a smaller combined budget.",
        "# Tree: docs/decisions/step1_instrument_selection.md",
        "#",
        f"# IS window: up to {split_date.date()}",
        "#",
        "instrument_weights:",
    ]
    for class_name, subtree in TREE.items():
        leaves = _get_leaves(subtree)
        class_w = sum(weights.get(c, 0.0) for c in leaves)
        lines.append(f"  # ── {class_name} ({class_w*100:.1f}%) {'─'*30}")
        for code in leaves:
            if code in weights:
                lines.append(f"  {code}: {weights[code]:.6f}")

    content = "\n".join(lines) + "\n"
    out_path = st.path(OUTPUT_FILE, state_dir=state_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    main()

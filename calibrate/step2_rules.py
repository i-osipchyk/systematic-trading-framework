"""
Step 2: Rule selection confirmation.

Displays the rule families from config/rules.yaml and waits for the user to
confirm the selection is finalised before proceeding to calibration.

Writing step2.yaml to config/ marks this step complete.

Usage:
    uv run python calibrate/step2_rules.py
    uv run python calibrate/step2_rules.py --system systems/universe_v4
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_rules_config, set_config
from src.calibration import state as st

FILENAME = "step2.yaml"


def main(state_dir=None, report_dir=None) -> dict:
    if st.exists(FILENAME, state_dir=state_dir):
        print(f"  Step 2 already confirmed ({st.path(FILENAME, state_dir=state_dir)})")
        return {}

    rules = load_rules_config()

    SEP = "─" * 60
    print(f"\n  {SEP}")
    print(f"  RULE FAMILIES  ({len(rules)} families)")
    print(f"  {SEP}")
    total_variants = 0
    for family, cfg in rules.items():
        pairs = cfg.get("pairs") or cfg.get("spans")
        if pairs:
            variants = len(pairs)
            total_variants += variants
            label = f"{variants} variant{'s' if variants != 1 else ''}"
            print(f"\n  {family.upper()}  ({label})")
            for p in pairs:
                if isinstance(p, list):
                    print(f"    ({p[0]}, {p[1]})")
                else:
                    print(f"    {p}")
        else:
            total_variants += 1
            instruments = cfg.get("instruments", [])
            print(f"\n  {family.upper()}")
            if instruments:
                print(f"    instruments: {', '.join(str(i) for i in instruments)}")
    print(f"\n  Total rule variants: {total_variants}")
    print(f"\n  {SEP}")
    print(f"  Edit {st.path(FILENAME, state_dir=state_dir).parent / 'rules.yaml'}")
    print(f"  then press Enter to confirm the rule selection is finalised...")

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        print("\n  Aborted.")
        sys.exit(1)

    st.save(FILENAME, {"confirmed": datetime.now().isoformat(timespec="seconds"),
                       "n_families": len(rules),
                       "n_variants": total_variants,
                       "families": list(rules.keys())},
            state_dir=state_dir)
    print(f"  Confirmed → {st.path(FILENAME, state_dir=state_dir)}")
    return {"n_families": len(rules), "n_variants": total_variants}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 2: Rule selection")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "config")

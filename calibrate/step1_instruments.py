"""
Step 1: Instrument choice confirmation.

Displays the instrument universe from config/instruments.yaml and waits for the
user to confirm the list is finalised before proceeding to rule selection.

Writing step1.yaml to config/ marks this step complete.

Usage:
    uv run python calibrate/step1_instruments.py
    uv run python calibrate/step1_instruments.py --system systems/universe_v4
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, set_config, traded_instruments
from src.calibration import state as st

FILENAME = "step1.yaml"


def main(state_dir=None, report_dir=None) -> dict:
    if st.exists(FILENAME, state_dir=state_dir):
        print(f"  Step 1 already confirmed ({st.path(FILENAME, state_dir=state_dir)})")
        return {}

    cfgs = load_instrument_configs()
    traded = traded_instruments(cfgs)
    helpers = [c for c, cfg in cfgs.items() if not cfg.traded]

    asset_groups: dict[str, list[str]] = {}
    for code in traded:
        g = cfgs[code].asset_type
        asset_groups.setdefault(g, []).append(code)

    SEP = "─" * 60
    print(f"\n  {SEP}")
    print(f"  INSTRUMENT UNIVERSE  ({len(traded)} traded)")
    print(f"  {SEP}")
    for group, codes in asset_groups.items():
        print(f"\n  {group.upper()} ({len(codes)})")
        for code in codes:
            cfg = cfgs[code]
            print(f"    {code:<12}  pointsize={cfg.pointsize:<10}  spread={cfg.spread_cost}  {cfg.currency}")
    if helpers:
        print(f"\n  FX helpers (not traded): {', '.join(helpers)}")
    print(f"\n  {SEP}")
    print(f"  Edit {st.path(FILENAME, state_dir=state_dir).parent / 'instruments.yaml'}")
    print(f"  then press Enter to confirm the universe is finalised...")

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        print("\n  Aborted.")
        sys.exit(1)

    st.save(FILENAME, {"confirmed": datetime.now().isoformat(timespec="seconds"),
                       "n_traded": len(traded),
                       "traded": traded},
            state_dir=state_dir)
    print(f"  Confirmed → {st.path(FILENAME, state_dir=state_dir)}")
    return {"n_traded": len(traded), "instruments": traded}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 1: Instrument choice")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "config")

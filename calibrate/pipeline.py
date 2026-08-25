"""
Calibration pipeline orchestrator.

Runs all 8 calibration steps sequentially, saving state to a timestamped
run directory under systems/. Skips steps whose output state files already
exist (unless --force or --from N is given).

Usage:
    uv run python calibrate/pipeline.py                                        # new run (universe_v3)
    uv run python calibrate/pipeline.py --config config/universe_v2           # specific build
    uv run python calibrate/pipeline.py --resume systems/universe_v3/run_X    # resume existing run
    uv run python calibrate/pipeline.py --resume systems/universe_v3/run_X --from 2  # continue after editing weights
    uv run python calibrate/pipeline.py --resume systems/universe_v3/run_X --force
    uv run python calibrate/pipeline.py --step 5                               # new run, only step 5
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import (
    load_bars_per_year, load_instrument_configs, load_rules_config, load_timeframe,
    set_config, traded_instruments,
)
from src.calibration import state as st

STEP_LINE = "─" * 60


@dataclass
class Step:
    number: int
    module: str        # e.g. 'calibrate.step3a_scalars'
    output_file: str   # e.g. '01_scalars.yaml'
    requires_user: bool
    description: str


STEPS: list[Step] = [
    #  #  module                              output file                      user?  description
    Step(0, "calibrate.step0_fetch_data",          None,                             False, "Step 0 — Fetch / update market data"),
    Step(1, "calibrate.step3_rules",               "step3a_scalars.yaml",            True,  "Step 3 — Rule calibration: scalars, correlations, cost filter, weights [USER EDITS] (→ step3*.yaml + step3_report.md)"),
    Step(2, "calibrate.step3d_fdm",                "step3d_fdm.yaml",                False, "Step 4 — Compute per-instrument FDM (→ step3d_fdm.yaml)"),
    Step(3, "calibrate.step4a_instrument_weights", "step4a_instrument_weights.yaml", True,  "Step 5 — Set instrument weights [USER INPUT] (→ step4a_instrument_weights.yaml)"),
    Step(4, "calibrate.step4b_idm",                "step4b_idm.yaml",                False, "Step 6 — Compute IDM (→ step4b_idm.yaml)"),
    Step(5, "calibrate.step5a_vol_target",         "step5_vol_target.yaml",          True,  "Step 7 — Kelly analysis & vol target [USER INPUT] (→ step5_vol_target.yaml)"),
    Step(6, "calibrate.step5b_backtest",           None,                             False, "Step 8 — Full IS+Val+Test backtest [informational]"),
    Step(7, "calibrate.oos_validation",            None,                             False, "Step 9 — IS vs Val SR breakdown by instrument, asset class, rule"),
]



def _import_step(module_name: str):
    """Dynamically import a step module and return it."""
    root = Path(__file__).parents[1]
    file_path = root / (module_name.replace(".", "/") + ".py")

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _print_status_header(steps: list[Step], from_step: int, only_step: int | None,
                         run_dir: Path) -> None:
    print(f"\n  Calibration Pipeline")
    print(f"  Run: {run_dir}/")
    print(f"  {STEP_LINE}")
    for step in steps:
        done = step.output_file is not None and st.exists(step.output_file, state_dir=run_dir)
        status = "DONE  " if done else "PENDING"
        user_tag = " [user input]" if step.requires_user else ""
        skip_tag = ""
        if only_step is not None and step.number != only_step:
            skip_tag = " [skip]"
        elif step.number < from_step:
            skip_tag = " [skip]"
        print(f"  Step {step.number}: {status}  {step.description}{user_tag}{skip_tag}")
    print(f"  {STEP_LINE}\n")


def _should_run(step: Step, from_step: int, only_step: int | None, force: bool,
                run_dir: Path) -> bool:
    if only_step is not None:
        return step.number == only_step
    if step.number < from_step:
        return False
    if force:
        return True
    if step.output_file is not None and st.exists(step.output_file, state_dir=run_dir):
        return False
    return True


def _log_step_values(step: Step, values: dict, run_dir: Path) -> None:
    """Print confirmed values from a user-input step and update run_log.yaml."""
    if not values:
        return

    print(f"\n  Logged for step {step.number} ({step.description}):")
    for key, val in values.items():
        if isinstance(val, dict):
            print(f"    {key}:")
            for k, v in val.items():
                print(f"      {k}: {v:.4f}" if isinstance(v, float) else f"      {k}: {v}")
        elif isinstance(val, float):
            print(f"    {key}: {val:.4f}  ({val:.1%})" if val < 1 else f"    {key}: {val:.4f}")
        else:
            print(f"    {key}: {val}")

    _update_run_log(run_dir, step, values)


def _update_run_log(run_dir: Path, step: Step, values: dict) -> None:
    """Append step values to run_log.yaml."""
    log_path = run_dir / "run_log.yaml"
    if log_path.exists():
        with open(log_path) as f:
            log = yaml.safe_load(f) or {}
    else:
        log = {}

    if "steps" not in log:
        log["steps"] = {}
    log["steps"][step.number] = {"name": step.description, **values}

    with open(log_path, "w") as f:
        yaml.dump(log, f, default_flow_style=False, sort_keys=False)


def _init_run_log(run_dir: Path) -> None:
    """Write initial run_log.yaml with timestamp, instruments, rules, and timeframe metadata."""
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules_cfg = load_rules_config()

    log = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "timeframe": load_timeframe(),
        "bars_per_year": load_bars_per_year(),
        "instruments": instruments,
        "rules": {
            family: {
                "family": cfg.get("family", family),
                "specs": cfg.get("pairs") or cfg.get("spans"),
            }
            for family, cfg in rules_cfg.items()
        },
        "steps": {},
    }

    log_path = run_dir / "run_log.yaml"
    if not log_path.exists():
        with open(log_path, "w") as f:
            yaml.dump(log, f, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibration pipeline")
    parser.add_argument("--config", type=str, default="config/universe_v3",
                        metavar="PATH",
                        help="Strategy config folder (default: config/universe_v3)")
    parser.add_argument("--demo", action="store_true",
                        help="Use demo account for data fetching (step 0)")
    parser.add_argument("--resume", type=str, default=None,
                        metavar="PATH",
                        help="Resume an existing run directory (skips completed steps)")
    parser.add_argument("--from", dest="from_step", type=int, default=0,
                        metavar="N", help="Start (or restart) from step N (default: 0)")
    parser.add_argument("--force", action="store_true",
                        help="Rerun all steps regardless of cached state")
    parser.add_argument("--step", type=int, default=None,
                        metavar="N", help="Run only step N")
    args = parser.parse_args()

    from_step = args.from_step
    force = args.force
    only_step = args.step
    demo = args.demo

    root = Path(__file__).parents[1]

    # ── Apply config ──────────────────────────────────────────────────────────
    config_path = root / args.config
    if not config_path.exists():
        print(f"  ERROR: config file not found: {config_path}")
        sys.exit(1)
    set_config(config_path)

    # ── Determine run directory ───────────────────────────────────────────────
    if args.resume is not None:
        run_dir = Path(args.resume)
        if not run_dir.exists():
            print(f"  ERROR: resume path does not exist: {run_dir}")
            sys.exit(1)
    else:
        config_folder = config_path.stem
        run_dir = root / "systems" / config_folder / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir.mkdir(parents=True, exist_ok=True)

    # ── Update systems/latest symlink ─────────────────────────────────────────
    latest = root / "systems" / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(run_dir.resolve())

    # ── Initialise run log (only if new run) ─────────────────────────────────
    _init_run_log(run_dir)

    _print_status_header(STEPS, from_step, only_step, run_dir)

    for step in STEPS:
        if not _should_run(step, from_step, only_step, force, run_dir):
            if step.output_file and st.exists(step.output_file, state_dir=run_dir):
                print(f"  Step {step.number}: {step.description} → skipped (cached)")
            continue

        print(f"\n  {'='*58}")
        print(f"  Step {step.number}: {step.description}")
        print(f"  {'='*58}\n")

        try:
            mod = _import_step(step.module)
            kwargs = {"state_dir": run_dir}
            if step.number == 0:
                kwargs["demo"] = demo
            result = mod.main(**kwargs)
        except KeyboardInterrupt:
            print(f"\n  Step {step.number} aborted by user.")
            sys.exit(1)
        except Exception:
            print(f"\n  Step {step.number} FAILED:")
            traceback.print_exc()
            sys.exit(1)

        if step.requires_user and isinstance(result, dict):
            _log_step_values(step, result, run_dir)

        print(f"\n  Step {step.number} complete.")

    print(f"\n  {'='*58}")
    print(f"  Pipeline complete.")
    print(f"  Run directory : {run_dir}/")
    print(f"  Run log       : {run_dir}/run_log.yaml")
    print(f"  {'='*58}\n")


if __name__ == "__main__":
    main()

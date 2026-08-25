"""
Calibration pipeline orchestrator.

Each system directory has a fixed layout:
  systems/<name>/config/   — YAML configuration files
  systems/<name>/results/  — calibration state files and reports

Steps whose output file already exists are skipped automatically (resumable).
If all steps are already complete, the pipeline exits with a notice.
Use --force to delete results and start fresh.

Usage:
    uv run python calibrate/pipeline.py --system systems/universe_v4
    uv run python calibrate/pipeline.py --system systems/universe_v4 --force
    uv run python calibrate/pipeline.py --system systems/universe_v4 --step 3
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
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
    number: str           # matches system-build-steps.md: '0', '1', '2', '3', '4', '5', 'oos'
    module: str
    output_file: str | None
    completion_key: str | None  # if set, output_file must also contain this top-level key
    requires_user: bool
    description: str


STEPS: list[Step] = [
    Step("0",   "calibrate.step0_fetch_data",          None,          None,          False, "Step 0   — Fetch / update market data"),
    Step("1",   "calibrate.step1_instruments",         "step1.yaml",  None,          True,  "Step 1   — Instrument choice [USER CONFIRMS]"),
    Step("2",   "calibrate.step2_rules",               "step2.yaml",  None,          True,  "Step 2   — Rule selection [USER CONFIRMS]"),
    Step("3",   "calibrate.step3_rules",               "step3.yaml",  "fdm",         True,  "Step 3   — Rule correlations, trading speed, forecast weights [USER EDITS]"),
    Step("4",   "calibrate.step4a_instrument_weights", "step4.yaml",  "idm",         True,  "Step 4   — Instrument weights and IDM [USER INPUT]"),
    Step("5",   "calibrate.step5_calibrate",           "step5.yaml",  "vol_target",  True,  "Step 5   — IS backtest and volatility target [USER CONFIRMS]"),
    Step("oos", "calibrate.oos_validation",            None,          None,          False, "OOS      — IS vs Val SR breakdown (run after locking all steps)"),
]


def _import_step(module_name: str):
    root = Path(__file__).parents[1]
    file_path = root / (module_name.replace(".", "/") + ".py")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _step_done(step: Step, config_dir: Path) -> bool:
    if step.output_file is None:
        return False
    if not st.exists(step.output_file, state_dir=config_dir):
        return False
    if step.completion_key:
        return st.has_section(step.output_file, step.completion_key, state_dir=config_dir)
    return True


def _all_steps_complete(steps: list[Step], config_dir: Path) -> bool:
    return all(_step_done(s, config_dir) for s in steps)


def _print_status_header(steps: list[Step], only_step: str | None, config_dir: Path) -> None:
    print(f"\n  Calibration Pipeline")
    print(f"  {STEP_LINE}")
    for step in steps:
        status = "DONE   " if _step_done(step, config_dir) else "PENDING"
        user_tag = " [user input]" if step.requires_user else ""
        skip_tag = " [skip]" if only_step is not None and step.number != only_step else ""
        print(f"  {step.description:52s} {status}{user_tag}{skip_tag}")
    print(f"  {STEP_LINE}\n")


def _should_run(step: Step, only_step: str | None, config_dir: Path) -> bool:
    if only_step is not None:
        return step.number == only_step
    return not _step_done(step, config_dir)


def _log_step_values(step: Step, values: dict, results_dir: Path) -> None:
    if not values:
        return
    print(f"\n  Logged for {step.description}:")
    for key, val in values.items():
        if isinstance(val, dict):
            print(f"    {key}:")
            for k, v in val.items():
                print(f"      {k}: {v:.4f}" if isinstance(v, float) else f"      {k}: {v}")
        elif isinstance(val, float):
            print(f"    {key}: {val:.4f}  ({val:.1%})" if val < 1 else f"    {key}: {val:.4f}")
        else:
            print(f"    {key}: {val}")
    _update_run_log(results_dir, step, values)


def _update_run_log(results_dir: Path, step: Step, values: dict) -> None:
    log_path = results_dir / "run_log.yaml"
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


def _init_run_log(results_dir: Path) -> None:
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules_cfg = load_rules_config()
    log = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "results_dir": str(results_dir),
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
    log_path = results_dir / "run_log.yaml"
    if not log_path.exists():
        with open(log_path, "w") as f:
            yaml.dump(log, f, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibration pipeline")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH",
                        help="System directory (default: systems/universe_v4). "
                             "Must contain config/ and will write to results/.")
    parser.add_argument("--demo", action="store_true",
                        help="Use demo account for data fetching (step 0)")
    parser.add_argument("--force", action="store_true",
                        help="Delete existing results and rerun all steps from scratch")
    parser.add_argument("--step", type=str, default=None,
                        metavar="ID", help="Run only this step (0, 1, 2, 3, 4, 5, oos)")
    args = parser.parse_args()

    demo = args.demo
    only_step = args.step

    root = Path(__file__).parents[1]
    system_dir = root / args.system
    config_dir = system_dir / "config"
    results_dir = system_dir / "results"

    if not config_dir.exists():
        print(f"  ERROR: config directory not found: {config_dir}")
        sys.exit(1)

    set_config(config_dir)

    if args.force:
        # Delete calibration state yamls from config_dir; leave static config files
        for f in config_dir.glob("step*.yaml"):
            f.unlink()
        if results_dir.exists():
            shutil.rmtree(results_dir)
        print(f"  Cleared calibration state from {config_dir}/ and {results_dir}/")

    results_dir.mkdir(parents=True, exist_ok=True)

    if _all_steps_complete(STEPS, config_dir) and only_step is None:
        print(f"\n  System '{args.system}' is already fully calibrated.")
        print(f"  Config/state: {config_dir}/")
        print(f"  Reports:      {results_dir}/")
        print(f"  Use --force to clear state and rerun from scratch.")
        sys.exit(0)

    _init_run_log(results_dir)
    _print_status_header(STEPS, only_step, config_dir)

    for step in STEPS:
        if not _should_run(step, only_step, config_dir):
            if _step_done(step, config_dir):
                print(f"  {step.description} → skipped (done)")
            continue

        print(f"\n  {'='*58}")
        print(f"  {step.description}")
        print(f"  {'='*58}\n")

        try:
            mod = _import_step(step.module)
            kwargs = {"state_dir": config_dir, "report_dir": results_dir}
            if step.number == "0":
                kwargs["demo"] = demo
            result = mod.main(**kwargs)
        except KeyboardInterrupt:
            print(f"\n  {step.description} — aborted by user.")
            sys.exit(1)
        except Exception:
            print(f"\n  {step.description} — FAILED:")
            traceback.print_exc()
            sys.exit(1)

        if step.requires_user and isinstance(result, dict):
            _log_step_values(step, result, results_dir)

        print(f"\n  {step.description} — complete.")

    print(f"\n  {'='*58}")
    print(f"  Pipeline complete.")
    print(f"  Config/state: {config_dir}/")
    print(f"  Reports:      {results_dir}/")
    print(f"  {'='*58}\n")


if __name__ == "__main__":
    main()

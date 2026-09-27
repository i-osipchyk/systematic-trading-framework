"""Runs one calibration step in-process for the web UI.

Mirrors calibrate/pipeline.py's per-step execution, but never blocks on
stdin: steps 1-5 finalize whatever is currently on disk in config/ (the
values the UI rendered and the user approved) instead of waiting for an
Enter keypress at a terminal — see each step's ``auto_confirm`` kwarg.
"""
from __future__ import annotations

import contextlib
import importlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from calibrate.pipeline import STEPS, Step, init_run_log, update_run_log
from src.backtest.config import set_config


@dataclass
class RunOutcome:
    ok: bool
    stdout: str
    values: dict = field(default_factory=dict)
    error: str | None = None


def _find_step(step_number: str) -> Step:
    for step in STEPS:
        if step.number == step_number:
            return step
    raise ValueError(f"Unknown step number: {step_number!r}")


def run_step(
    system_dir: Path, step_number: str, demo: bool = False, extra_kwargs: dict | None = None,
) -> RunOutcome:
    step = _find_step(step_number)
    config_dir = Path(system_dir) / "config"
    results_dir = Path(system_dir) / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    set_config(config_dir)
    init_run_log(results_dir)

    kwargs: dict = {"state_dir": config_dir, "report_dir": results_dir}
    if step.number == "0":
        kwargs["demo"] = demo
    elif step.requires_user:
        kwargs["auto_confirm"] = True
    if extra_kwargs:
        kwargs.update(extra_kwargs)

    buf = io.StringIO()
    try:
        mod = importlib.import_module(step.module)
        with contextlib.redirect_stdout(buf):
            result = mod.main(**kwargs)
    except Exception as exc:
        return RunOutcome(ok=False, stdout=buf.getvalue(), error=str(exc))

    values = result if isinstance(result, dict) else {}
    if values:
        update_run_log(results_dir, step, values)
    return RunOutcome(ok=True, stdout=buf.getvalue(), values=values)

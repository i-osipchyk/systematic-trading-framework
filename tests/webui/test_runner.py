from __future__ import annotations

from pathlib import Path

import pytest

from src.calibration import state as st


def test_run_step_auto_confirms_and_updates_run_log(config_dir: Path):
    from src.webui.runner import run_step
    system_dir = config_dir.parent

    outcome = run_step(system_dir, "1")

    assert outcome.ok is True
    assert outcome.error is None
    assert outcome.values["n_traded"] == 2
    assert outcome.values["instruments"] == ["US500", "BUND"]
    assert st.exists("step1.yaml", state_dir=config_dir)

    import yaml
    log = yaml.safe_load((system_dir / "results" / "run_log.yaml").read_text())
    assert log["steps"]["1"]["n_traded"] == 2


def test_run_step_unknown_number_raises(config_dir: Path):
    from src.webui.runner import run_step
    system_dir = config_dir.parent

    with pytest.raises(ValueError, match="Unknown step"):
        run_step(system_dir, "99")


def test_run_step_returns_error_instead_of_raising(config_dir: Path):
    from src.webui.runner import run_step
    system_dir = config_dir.parent

    # step 4 depends on step 3 having already run — invoking it first should
    # surface as a failed RunOutcome, not an uncaught exception.
    outcome = run_step(system_dir, "4")

    assert outcome.ok is False
    assert outcome.error is not None
    assert "step3.yaml" in outcome.error

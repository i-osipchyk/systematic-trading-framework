from __future__ import annotations

from pathlib import Path

from calibrate.pipeline import STEPS, step_done
from src.calibration import state as st


def test_step_done_false_when_output_file_missing(tmp_path: Path):
    step1 = next(s for s in STEPS if s.number == "1")
    assert step_done(step1, tmp_path) is False


def test_step_done_true_once_output_file_written(tmp_path: Path):
    step1 = next(s for s in STEPS if s.number == "1")
    st.save("step1.yaml", {"confirmed": "now"}, state_dir=tmp_path)
    assert step_done(step1, tmp_path) is True


def test_step_done_checks_completion_key_for_multi_section_files(tmp_path: Path):
    step3 = next(s for s in STEPS if s.number == "3")
    st.save_section("step3.yaml", "scalars", {"a": 1}, state_dir=tmp_path)
    assert step_done(step3, tmp_path) is False  # 'fdm' section still missing

    st.save_section("step3.yaml", "fdm", {"a": 1.0}, state_dir=tmp_path)
    assert step_done(step3, tmp_path) is True


def test_step_done_false_for_steps_without_an_output_file(tmp_path: Path):
    step0 = next(s for s in STEPS if s.number == "0")
    assert step_done(step0, tmp_path) is False

from __future__ import annotations

from pathlib import Path

import pytest

from src.calibration import state as st


def _run_step3(config_dir: Path, report_dir: Path) -> None:
    from calibrate.step3_rules import main as step3_main
    step3_main(state_dir=config_dir, report_dir=report_dir, auto_confirm=True)


def _run_main(config_dir: Path, report_dir: Path, **kwargs):
    from calibrate.step4a_instrument_weights import main
    return main(state_dir=config_dir, report_dir=report_dir, **kwargs)


def test_auto_confirm_accepts_default_equal_weight_templates(config_dir: Path, tmp_path: Path, monkeypatch):
    report_dir = tmp_path / "results"
    report_dir.mkdir()
    _run_step3(config_dir, report_dir)  # step4's IDM computation requires step3.yaml
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    result = _run_main(config_dir, report_dir, auto_confirm=True)

    assert st.has_section("step4.yaml", "instrument_weights", state_dir=config_dir)
    assert st.has_section("step4.yaml", "idm", state_dir=config_dir)
    assert result["group_weights"].keys() == {"index", "bond"}
    assert set(result["instrument_weights"]) == {"US500", "BUND"}
    assert result["idm"] == st.load_section("step4.yaml", "idm", state_dir=config_dir)


def test_auto_confirm_raises_on_invalid_group_weights(config_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    report_dir = tmp_path / "results"
    report_dir.mkdir()

    # Pre-write group_weights that don't sum to 1.0 — the user "edited" it wrong.
    st.save_section("step4.yaml", "group_weights", {"index": 0.9, "bond": 0.9}, state_dir=config_dir)

    with pytest.raises(ValueError, match="Weights sum to"):
        _run_main(config_dir, report_dir, auto_confirm=True)

from __future__ import annotations

from pathlib import Path

from src.calibration import state as st


def _run_main(config_dir: Path, **kwargs):
    from calibrate.step1_instruments import main
    return main(state_dir=config_dir, **kwargs)


def test_auto_confirm_writes_step1_without_blocking_on_input(config_dir: Path, monkeypatch):
    def _fail_if_called():
        raise AssertionError("input() must not be called when auto_confirm=True")
    monkeypatch.setattr("builtins.input", _fail_if_called)

    result = _run_main(config_dir, auto_confirm=True)

    assert st.exists("step1.yaml", state_dir=config_dir)
    saved = st.load("step1.yaml", state_dir=config_dir)
    assert saved["n_traded"] == 2
    assert set(saved["traded"]) == {"US500", "BUND"}
    assert result == {
        "n_traded": 2,
        "instruments": ["US500", "BUND"],
        "asset_groups": {"index": ["US500"], "bond": ["BUND"]},
    }


def test_auto_confirm_is_noop_when_already_confirmed(config_dir: Path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    _run_main(config_dir, auto_confirm=True)

    result = _run_main(config_dir, auto_confirm=True)
    assert result == {}

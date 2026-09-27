from __future__ import annotations

from pathlib import Path

import pytest

from src.calibration import state as st


def _run_step3(config_dir: Path, report_dir: Path) -> None:
    from calibrate.step3_rules import main as step3_main
    step3_main(state_dir=config_dir, report_dir=report_dir, auto_confirm=True)


def _run_step4(config_dir: Path, report_dir: Path) -> None:
    from calibrate.step4a_instrument_weights import main as step4_main
    step4_main(state_dir=config_dir, report_dir=report_dir, auto_confirm=True)


def _run_main(config_dir: Path, report_dir: Path, **kwargs):
    from calibrate.step5_calibrate import main
    return main(state_dir=config_dir, report_dir=report_dir, **kwargs)


def _prep(config_dir: Path, report_dir: Path) -> None:
    _run_step3(config_dir, report_dir)
    _run_step4(config_dir, report_dir)


def test_auto_confirm_accepts_suggested_vol_target(config_dir: Path, tmp_path: Path, monkeypatch):
    report_dir = tmp_path / "results"
    report_dir.mkdir()
    _prep(config_dir, report_dir)
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    result = _run_main(config_dir, report_dir, auto_confirm=True)

    assert st.has_section("step5.yaml", "vol_target", state_dir=config_dir)
    assert result["vol_target"] == st.load_section("step5.yaml", "vol_target", state_dir=config_dir)
    assert (report_dir / "step5_report.md").exists()


def test_auto_confirm_raises_on_vol_target_out_of_range(config_dir: Path, tmp_path: Path, monkeypatch):
    report_dir = tmp_path / "results"
    report_dir.mkdir()
    _prep(config_dir, report_dir)
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    st.save_section("step5.yaml", "vol_target", 0.99, state_dir=config_dir)

    with pytest.raises(ValueError, match="out of range"):
        _run_main(config_dir, report_dir, auto_confirm=True)


def test_main_saves_equity_curve_csv_for_the_confirmed_vol_target(config_dir: Path, tmp_path: Path, monkeypatch):
    report_dir = tmp_path / "results"
    report_dir.mkdir()
    _prep(config_dir, report_dir)
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    _run_main(config_dir, report_dir, auto_confirm=True)

    equity_path = report_dir / "step5_equity_curve.csv"
    assert equity_path.exists()
    header = equity_path.read_text().splitlines()[0]
    assert header == "date,equity"


def test_run_is_backtest_is_callable_directly_for_a_given_vol_target(config_dir: Path, tmp_path: Path):
    from calibrate.step5_calibrate import run_is_backtest
    report_dir = tmp_path / "results"
    report_dir.mkdir()
    _prep(config_dir, report_dir)

    low = run_is_backtest(0.10, state_dir=config_dir)
    high = run_is_backtest(0.30, state_dir=config_dir)

    for preview in (low, high):
        assert isinstance(preview["is_sharpe"], float)
        assert not preview["equity_curve"].empty
        assert preview["instruments"]
        assert {"half_kelly", "full_kelly", "geo_mean", "suggested"} <= preview.keys()

    # Higher vol target -> larger absolute swings in the compounded IS equity curve.
    low_range = low["equity_curve"].max() - low["equity_curve"].min()
    high_range = high["equity_curve"].max() - high["equity_curve"].min()
    assert high_range > low_range

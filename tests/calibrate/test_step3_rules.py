from __future__ import annotations

from pathlib import Path

from src.calibration import state as st


def _run_main(config_dir: Path, report_dir: Path, **kwargs):
    from calibrate.step3_rules import main
    return main(state_dir=config_dir, report_dir=report_dir, **kwargs)


def test_auto_confirm_computes_fdm_without_blocking_on_input(config_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    report_dir = tmp_path / "results"
    report_dir.mkdir()

    result = _run_main(config_dir, report_dir, auto_confirm=True)

    assert st.has_section("step3.yaml", "scalars", state_dir=config_dir)
    assert st.has_section("step3.yaml", "forecast_weights", state_dir=config_dir)
    assert st.has_section("step3.yaml", "fdm", state_dir=config_dir)
    assert result["state"] == str(st.path("step3.yaml", state_dir=config_dir))
    assert result["report"] == str(report_dir / "step3_report.md")

    saved_weights = st.load_section("step3.yaml", "forecast_weights", state_dir=config_dir)
    assert result["forecast_weights"] == {k: round(float(v), 4) for k, v in saved_weights.items()}
    assert set(result["fdm"]) <= {"US500", "BUND"}
    assert all(isinstance(v, float) for v in result["fdm"].values())

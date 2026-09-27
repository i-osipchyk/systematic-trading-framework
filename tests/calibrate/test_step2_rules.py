from __future__ import annotations

from pathlib import Path

from src.calibration import state as st


def _run_main(config_dir: Path, **kwargs):
    from calibrate.step2_rules import main
    return main(state_dir=config_dir, **kwargs)


def test_auto_confirm_writes_step2_without_blocking_on_input(config_dir: Path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    result = _run_main(config_dir, auto_confirm=True)

    assert st.exists("step2.yaml", state_dir=config_dir)
    saved = st.load("step2.yaml", state_dir=config_dir)
    assert saved["n_families"] == 1
    assert saved["n_variants"] == 2
    assert result == {
        "n_families": 1,
        "n_variants": 2,
        "families": ["ewmac"],
        "family_variants": {"ewmac": ["16_64", "32_128"]},
    }


def test_auto_confirm_labels_lookbacks_and_atomic_families(config_dir: Path, monkeypatch):
    """Regression: 'lookbacks' families (breakout, tsmom) were silently treated as
    atomic (1 variant) because the old code only checked 'pairs'/'spans'."""
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    (config_dir / "rules.yaml").write_text(
        "rules:\n"
        "  ewmac:\n"
        "    pairs: [[16, 64], [32, 128]]\n"
        "  breakout:\n"
        "    lookbacks: [20, 40, 80]\n"
        "  seasonality: {}\n"
    )

    result = _run_main(config_dir, auto_confirm=True)

    assert result["n_variants"] == 2 + 3 + 1  # ewmac(2) + breakout(3) + seasonality(1, atomic)
    assert result["family_variants"] == {
        "ewmac": ["16_64", "32_128"],
        "breakout": ["20", "40", "80"],
        "seasonality": [],
    }


def test_auto_confirm_is_noop_when_already_confirmed(config_dir: Path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    _run_main(config_dir, auto_confirm=True)

    result = _run_main(config_dir, auto_confirm=True)
    assert result == {}

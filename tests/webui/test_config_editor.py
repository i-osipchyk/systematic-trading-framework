from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.calibration import state as st
from src.webui import config_editor


def _make_system(root: Path, name: str) -> Path:
    system_dir = root / name
    (system_dir / "config").mkdir(parents=True)
    return system_dir


# ── Step 3: forecast weights ─────────────────────────────────────────────────

def test_read_forecast_weights_returns_none_before_step3_has_run(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    assert config_editor.read_forecast_weights(system_dir) is None


def test_forecast_weight_families_groups_variants_by_family():
    weights = {"EWMAC_16_64": 0.25, "EWMAC_32_128": 0.25, "SEASONALITY": 0.5}
    families = config_editor.forecast_weight_families(weights)
    assert families == {"EWMAC": ["EWMAC_16_64", "EWMAC_32_128"], "SEASONALITY": ["SEASONALITY"]}


def test_split_family_budgets_equally_divides_within_family():
    weights = {"EWMAC_16_64": 0.1, "EWMAC_32_128": 0.1, "SEASONALITY": 0.8}
    result = config_editor.split_family_budgets_equally(weights, {"EWMAC": 0.6, "SEASONALITY": 0.4})
    assert result == {"EWMAC_16_64": 0.3, "EWMAC_32_128": 0.3, "SEASONALITY": 0.4}


def test_write_forecast_weights_round_trips(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    st.save_section("step3.yaml", "forecast_weights", {"EWMAC_32_128": 0.5, "SEASONALITY": 0.5},
                     state_dir=system_dir / "config")

    config_editor.write_forecast_weights(system_dir, {"EWMAC_32_128": 0.7, "SEASONALITY": 0.3})

    assert config_editor.read_forecast_weights(system_dir) == {"EWMAC_32_128": 0.7, "SEASONALITY": 0.3}


def test_write_forecast_weights_rejects_bad_sum(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    with pytest.raises(ValueError, match="sum to"):
        config_editor.write_forecast_weights(system_dir, {"EWMAC_32_128": 0.6, "SEASONALITY": 0.6})


def test_write_forecast_weights_rejects_negative(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    with pytest.raises(ValueError, match="non-negative"):
        config_editor.write_forecast_weights(system_dir, {"EWMAC_32_128": -0.1, "SEASONALITY": 1.1})


def test_write_forecast_weights_preserves_other_sections(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    st.save_section("step3.yaml", "fdm", {"US500": 1.4}, state_dir=system_dir / "config")
    st.save_section("step3.yaml", "forecast_weights", {"EWMAC_32_128": 1.0}, state_dir=system_dir / "config")

    config_editor.write_forecast_weights(system_dir, {"EWMAC_32_128": 1.0})

    data = yaml.safe_load((system_dir / "config" / "step3.yaml").read_text())
    assert data["fdm"] == {"US500": 1.4}


# ── Step 4: group / instrument weights ───────────────────────────────────────

def test_instrument_groups_skips_untraded(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    (system_dir / "config" / "instruments.yaml").write_text(yaml.dump({
        "instruments": {
            "US500": {"asset_type": "index", "traded": True},
            "Coffee": {"asset_type": "commodity", "traded": True},
            "Retired": {"asset_type": "commodity", "traded": False},
        }
    }))
    groups = config_editor.instrument_groups(system_dir)
    assert groups == {"index": ["US500"], "commodity": ["Coffee"]}


def test_write_group_weights_rejects_bad_sum(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    with pytest.raises(ValueError, match="sum to"):
        config_editor.write_group_weights(system_dir, {"index": 0.9, "commodity": 0.5})


def test_write_group_weights_round_trips(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    config_editor.write_group_weights(system_dir, {"index": 0.4, "commodity": 0.6})
    assert config_editor.read_group_weights(system_dir) == {"index": 0.4, "commodity": 0.6}


def test_reset_instrument_weights_removes_section(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    st.save_section("step4.yaml", "instrument_weights", {"US500": 1.0}, state_dir=system_dir / "config")

    config_editor.reset_instrument_weights(system_dir)

    assert config_editor.read_instrument_weights(system_dir) is None


def test_reset_instrument_weights_is_a_noop_if_absent(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    config_editor.reset_instrument_weights(system_dir)  # must not raise
    assert config_editor.read_instrument_weights(system_dir) is None


# ── Step 5: vol target ────────────────────────────────────────────────────────

def test_write_vol_target_round_trips(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    config_editor.write_vol_target(system_dir, 0.22)
    assert config_editor.read_vol_target(system_dir) == 0.22


def test_write_vol_target_rejects_out_of_range(tmp_path: Path):
    system_dir = _make_system(tmp_path, "sys")
    with pytest.raises(ValueError, match="out of range"):
        config_editor.write_vol_target(system_dir, 0.75)

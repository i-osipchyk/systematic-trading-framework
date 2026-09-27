from __future__ import annotations

from pathlib import Path

from src.calibration import state as st


def test_delete_section_removes_only_the_given_key(tmp_path: Path):
    st.save_section("step4.yaml", "group_weights", {"index": 1.0}, state_dir=tmp_path)
    st.save_section("step4.yaml", "instrument_weights", {"US500": 1.0}, state_dir=tmp_path)

    st.delete_section("step4.yaml", "instrument_weights", state_dir=tmp_path)

    assert st.has_section("step4.yaml", "instrument_weights", state_dir=tmp_path) is False
    assert st.has_section("step4.yaml", "group_weights", state_dir=tmp_path) is True


def test_delete_section_is_a_noop_when_file_missing(tmp_path: Path):
    st.delete_section("step4.yaml", "instrument_weights", state_dir=tmp_path)  # must not raise
    assert st.exists("step4.yaml", state_dir=tmp_path) is False


def test_delete_section_is_a_noop_when_section_missing(tmp_path: Path):
    st.save_section("step4.yaml", "group_weights", {"index": 1.0}, state_dir=tmp_path)
    st.delete_section("step4.yaml", "instrument_weights", state_dir=tmp_path)  # must not raise
    assert st.load_section("step4.yaml", "group_weights", state_dir=tmp_path) == {"index": 1.0}

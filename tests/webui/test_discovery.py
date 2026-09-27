from __future__ import annotations

from pathlib import Path

from src.calibration import state as st


def _make_system(root: Path, name: str) -> Path:
    system_dir = root / name
    (system_dir / "config").mkdir(parents=True)
    return system_dir


def test_list_systems_finds_directories_with_a_config_subdir(tmp_path: Path):
    from src.webui.discovery import list_systems
    _make_system(tmp_path, "universe_v9")
    _make_system(tmp_path, "universe_v10")
    (tmp_path / "not_a_system.txt").write_text("x")

    names = list_systems(tmp_path)

    assert names == ["universe_v9", "universe_v10"]  # natural sort, not lexical


def test_list_systems_sorts_naturally_by_trailing_number(tmp_path: Path):
    from src.webui.discovery import list_systems
    for name in ["universe_v2", "universe_v11", "universe_v3", "universe_v10"]:
        _make_system(tmp_path, name)

    names = list_systems(tmp_path)

    assert names == ["universe_v2", "universe_v3", "universe_v10", "universe_v11"]


def test_list_systems_excludes_archive(tmp_path: Path):
    from src.webui.discovery import list_systems
    _make_system(tmp_path, "universe_v9")
    archived = tmp_path / "archive" / "old_build"
    (archived / "config").mkdir(parents=True)

    names = list_systems(tmp_path)

    assert names == ["universe_v9"]


def test_step_status_reports_done_and_pending(tmp_path: Path):
    from src.webui.discovery import step_status
    system_dir = _make_system(tmp_path, "universe_v9")
    st.save("step1.yaml", {"confirmed": "now"}, state_dir=system_dir / "config")

    statuses = step_status(system_dir)

    by_number = {s["number"]: s for s in statuses}
    assert by_number["1"]["done"] is True
    assert by_number["2"]["done"] is False
    assert by_number["1"]["requires_user"] is True
    assert by_number["0"]["requires_user"] is False

from __future__ import annotations

from pathlib import Path

import yaml


def test_read_run_log_returns_none_when_missing(tmp_path: Path):
    from src.webui.results import read_run_log
    assert read_run_log(tmp_path) is None


def test_read_run_log_parses_existing_file(tmp_path: Path):
    from src.webui.results import read_run_log
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "run_log.yaml").write_text(yaml.dump({"steps": {"5": {"vol_target": 0.2}}}))

    log = read_run_log(tmp_path)

    assert log["steps"]["5"]["vol_target"] == 0.2


def test_read_report_returns_none_when_missing(tmp_path: Path):
    from src.webui.results import read_report
    assert read_report(tmp_path, "step6.md") is None


def test_read_report_returns_text_when_present(tmp_path: Path):
    from src.webui.results import read_report
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "step6.md").write_text("# OOS report\n")

    assert read_report(tmp_path, "step6.md") == "# OOS report\n"

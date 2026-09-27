"""Reads a system's results/ directory for display in the web UI."""
from __future__ import annotations

from pathlib import Path

import yaml


def read_run_log(system_dir: Path) -> dict | None:
    """Parse results/run_log.yaml, or None if the pipeline hasn't produced one yet."""
    log_path = Path(system_dir) / "results" / "run_log.yaml"
    if not log_path.exists():
        return None
    return yaml.safe_load(log_path.read_text()) or {}


def read_report(system_dir: Path, filename: str) -> str | None:
    """Read a text/markdown report from results/ (e.g. step5_report.md, step6.md)."""
    report_path = Path(system_dir) / "results" / filename
    if not report_path.exists():
        return None
    return report_path.read_text()

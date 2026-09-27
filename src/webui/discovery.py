"""Finds systems under systems/ and reports each one's per-step pipeline status."""
from __future__ import annotations

import re
from pathlib import Path

from calibrate.pipeline import STEPS, step_done

_EXCLUDED = {"archive"}


def _natural_sort_key(name: str) -> list:
    """Split 'universe_v10' into ['universe_v', 10, ''] so v2 < v10 (not lexical)."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def list_systems(systems_root: Path) -> list[str]:
    """Return names of immediate subdirectories of systems_root that hold a system.

    A directory is a system if it has a config/ subdirectory. `archive/` is
    excluded — it's a container for old, retired builds, not a system itself.
    Sorted naturally (universe_v2 before universe_v10), not lexically.
    """
    root = Path(systems_root)
    if not root.is_dir():
        return []
    names = [
        p.name for p in root.iterdir()
        if p.is_dir() and p.name not in _EXCLUDED and (p / "config").is_dir()
    ]
    return sorted(names, key=_natural_sort_key)


def step_status(system_dir: Path) -> list[dict]:
    """Return per-step completion status for one system, in pipeline order."""
    config_dir = Path(system_dir) / "config"
    return [
        {
            "number": step.number,
            "description": step.description,
            "requires_user": step.requires_user,
            "done": step_done(step, config_dir),
        }
        for step in STEPS
    ]

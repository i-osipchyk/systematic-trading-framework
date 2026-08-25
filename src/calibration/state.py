from __future__ import annotations
from pathlib import Path
import yaml

STATE_DIR = Path(__file__).parents[2] / "systems" / "universe_v4" / "results"


def _resolve_dir(state_dir=None) -> Path:
    return Path(state_dir) if state_dir is not None else STATE_DIR


def save(filename: str, data: dict, state_dir=None) -> None:
    """Save dict to <state_dir>/<filename> as YAML (defaults to calibrate/state/)."""
    p = _resolve_dir(state_dir) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load(filename: str, state_dir=None) -> dict:
    """Load <state_dir>/<filename> as dict (defaults to calibrate/state/)."""
    p = _resolve_dir(state_dir) / filename
    if not p.exists():
        raise FileNotFoundError(
            f"State file not found: {p}\n  Run the previous calibration step first."
        )
    with open(p) as f:
        return yaml.safe_load(f)


def exists(filename: str, state_dir=None) -> bool:
    return (_resolve_dir(state_dir) / filename).exists()


def path(filename: str, state_dir=None) -> Path:
    return _resolve_dir(state_dir) / filename


def parse_ewmac_scalars(raw: dict) -> dict[tuple[int, int], float]:
    """Parse {'2_8': 13.35, ...} → {(2, 8): 13.35, ...}"""
    return {tuple(int(x) for x in k.split("_")): float(v) for k, v in raw.items()}


def dump_ewmac_scalars(scalars: dict[tuple[int, int], float]) -> dict:
    """Convert {(2,8): 13.35} → {'2_8': 13.35} for YAML serialization."""
    return {f"{f}_{s}": round(float(v), 4) for (f, s), v in scalars.items()}


def parse_mr_scalars(raw: dict) -> dict[int, float]:
    return {int(k): float(v) for k, v in raw.items()}


def parse_family_scalars(scalars_data: dict, registry: dict) -> dict[str, dict]:
    """Parse full scalars_data YAML dict into native family_scalars dict."""
    result = {}
    for block_name, raw in scalars_data.items():
        handler = registry.get(block_name)
        if handler and raw:
            result[block_name] = handler.parse_scalars(raw)
    return result

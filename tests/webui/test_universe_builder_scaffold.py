from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _make_dirs(root: Path, *names: str) -> None:
    for name in names:
        (root / name / "config").mkdir(parents=True)


def test_next_system_name_starts_at_1_when_empty(tmp_path: Path):
    from src.webui.universe_builder import next_system_name
    assert next_system_name(tmp_path) == "universe_v1"


def test_next_system_name_increments_past_the_max_including_double_digits(tmp_path: Path):
    from src.webui.universe_builder import next_system_name
    _make_dirs(tmp_path, "universe_v2", "universe_v9", "universe_v10", "defaults", "archive")
    assert next_system_name(tmp_path) == "universe_v11"


@pytest.fixture
def catalog() -> dict:
    return {
        "US500": {"description": "S&P 500", "asset_type": "index", "currency": "USD",
                   "weight": 0.5, "pointsize": 1.0, "spread_cost": 0.4, "lot_step": 0.1,
                   "traded": True, "ctrader_symbol": "US500"},
        "BUND": {"description": "Euro Bund", "asset_type": "bond", "currency": "EUR",
                  "weight": 0.5, "pointsize": 1000.0, "spread_cost": 0.3, "lot_step": 0.01,
                  "traded": True, "ctrader_symbol": "BUND"},
        "XAU": {"description": "Gold", "asset_type": "commodity", "currency": "USD",
                 "weight": 0.5, "pointsize": 100.0, "spread_cost": 0.21, "lot_step": 0.01,
                 "traded": True, "ctrader_symbol": "XAU"},
    }


@pytest.fixture
def template_system(tmp_path: Path) -> Path:
    d = tmp_path / "systems" / "defaults" / "config"
    d.mkdir(parents=True)
    (d / "rules.yaml").write_text("rules:\n  ewmac:\n    pairs: [[16, 64]]\n")
    (d / "base.yaml").write_text("timeframe: D1\ncapital: 100000\n")
    return tmp_path / "systems"


def test_build_system_writes_instruments_weights_and_copies_template(
    template_system: Path, catalog: dict
):
    from src.webui.universe_builder import build_system
    system_dir = build_system(
        template_system, "universe_v11", ["US500", "XAU"], catalog=catalog, template_system="defaults"
    )

    assert system_dir == template_system / "universe_v11"
    instruments = yaml.safe_load((system_dir / "config" / "instruments.yaml").read_text())["instruments"]
    assert set(instruments.keys()) == {"US500", "XAU"}
    assert instruments["US500"]["weight"] == 0.5
    assert instruments["US500"]["traded"] is True
    assert instruments["US500"]["ctrader_symbol"] == "US500"

    assert (system_dir / "config" / "rules.yaml").read_text() == "rules:\n  ewmac:\n    pairs: [[16, 64]]\n"
    assert (system_dir / "config" / "base.yaml").read_text() == "timeframe: D1\ncapital: 100000\n"


def test_build_system_preserves_catalog_order_not_selection_order(
    template_system: Path, catalog: dict
):
    from src.webui.universe_builder import build_system
    system_dir = build_system(
        template_system, "universe_v11", ["XAU", "US500"], catalog=catalog, template_system="defaults"
    )
    instruments = yaml.safe_load((system_dir / "config" / "instruments.yaml").read_text())["instruments"]
    assert list(instruments.keys()) == ["US500", "XAU"]  # catalog order: US500 before XAU


def test_build_system_rejects_empty_selection(template_system: Path, catalog: dict):
    from src.webui.universe_builder import build_system
    with pytest.raises(ValueError, match="at least one"):
        build_system(template_system, "universe_v11", [], catalog=catalog, template_system="defaults")


def test_build_system_rejects_existing_system_name(template_system: Path, catalog: dict):
    from src.webui.universe_builder import build_system
    (template_system / "universe_v11" / "config").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        build_system(template_system, "universe_v11", ["US500"], catalog=catalog, template_system="defaults")


def test_build_system_then_build_rules_produces_a_combined_universe(
    template_system: Path, catalog: dict
):
    """Creating a universe picks instruments AND rules together — build_rules'
    output should replace the template's placeholder rules.yaml, not sit
    alongside it."""
    from src.webui.rule_builder import build_rules
    from src.webui.universe_builder import build_system

    system_dir = build_system(
        template_system, "universe_v11", ["US500", "XAU"], catalog=catalog, template_system="defaults"
    )
    rules_catalog = {"ewmac": {"pairs": [[16, 64], [32, 128]]}, "carry": {}}
    build_rules(system_dir, {"ewmac": ["16_64"], "carry": []}, catalog=rules_catalog)

    rules = yaml.safe_load((system_dir / "config" / "rules.yaml").read_text())["rules"]
    assert rules == {"ewmac": {"pairs": [[16, 64]]}, "carry": {}}  # not the template's [[16, 64]] alone

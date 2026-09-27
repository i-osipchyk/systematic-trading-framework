from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

_CATALOG_YAML = textwrap.dedent("""
    rules:
      ewmac:
        pairs:
          - [2, 8]
          - [4, 16]
          - [8, 32]
      breakout:
        lookbacks:
          - 20
          - 40
      mr:
        spans:
          - 5
          - 10
      carry: {}
      seasonality:
        instruments: [US500, BUND]
    """)


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(_CATALOG_YAML)
    return p


@pytest.fixture
def catalog(catalog_path: Path) -> dict:
    from src.webui.rule_builder import load_candidate_rules
    return load_candidate_rules(catalog_path)


def test_load_candidate_rules_parses_families_in_file_order(catalog_path: Path):
    from src.webui.rule_builder import load_candidate_rules
    catalog = load_candidate_rules(catalog_path)
    assert list(catalog.keys()) == ["ewmac", "breakout", "mr", "carry", "seasonality"]


def test_load_candidate_rules_on_real_defaults_file():
    from src.webui.rule_builder import DEFAULT_RULES_CATALOG_PATH, load_candidate_rules
    catalog = load_candidate_rules(DEFAULT_RULES_CATALOG_PATH)
    assert "ewmac" in catalog
    assert "seasonality" in catalog


def test_family_variants_labels_ewmac_pairs(catalog: dict):
    from src.webui.rule_builder import family_variants
    assert family_variants("ewmac", catalog["ewmac"]) == ["2_8", "4_16", "8_32"]


def test_family_variants_labels_lookbacks_and_spans(catalog: dict):
    from src.webui.rule_builder import family_variants
    assert family_variants("breakout", catalog["breakout"]) == ["20", "40"]
    assert family_variants("mr", catalog["mr"]) == ["5", "10"]


def test_family_variants_none_for_atomic_families(catalog: dict):
    from src.webui.rule_builder import family_variants
    assert family_variants("carry", catalog["carry"]) is None
    assert family_variants("seasonality", catalog["seasonality"]) is None


def test_rule_correlation_hints_flags_ewmac_breakout_pair():
    from src.webui.rule_builder import rule_correlation_hints
    hints = rule_correlation_hints({"ewmac", "breakout"})
    assert any("ewmac" in h and "breakout" in h for h in hints)


def test_rule_correlation_hints_empty_for_diversifying_pair():
    from src.webui.rule_builder import rule_correlation_hints
    assert rule_correlation_hints({"ewmac", "seasonality"}) == []


@pytest.fixture
def system_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "system" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "instruments.yaml").write_text(yaml.dump({
        "instruments": {
            "US500": {"traded": True},
            "BUND": {"traded": True},
            "EURUSD": {"traded": False},
        }
    }))
    return tmp_path / "system"


def test_build_rules_keeps_only_selected_variants(system_dir: Path, catalog: dict):
    from src.webui.rule_builder import build_rules
    build_rules(system_dir, {"ewmac": ["4_16", "8_32"]}, catalog=catalog)

    written = yaml.safe_load((system_dir / "config" / "rules.yaml").read_text())["rules"]
    assert written == {"ewmac": {"pairs": [[4, 16], [8, 32]]}}


def test_build_rules_includes_carry_with_no_params(system_dir: Path, catalog: dict):
    from src.webui.rule_builder import build_rules
    build_rules(system_dir, {"ewmac": ["4_16"], "carry": []}, catalog=catalog)

    written = yaml.safe_load((system_dir / "config" / "rules.yaml").read_text())["rules"]
    assert written["carry"] == {}


def test_build_rules_derives_seasonality_instruments_from_system(system_dir: Path, catalog: dict):
    from src.webui.rule_builder import build_rules
    build_rules(system_dir, {"ewmac": ["4_16"], "seasonality": []}, catalog=catalog)

    written = yaml.safe_load((system_dir / "config" / "rules.yaml").read_text())["rules"]
    assert set(written["seasonality"]["instruments"]) == {"US500", "BUND"}  # EURUSD excluded (traded: false)


def test_build_rules_rejects_empty_selection(system_dir: Path, catalog: dict):
    from src.webui.rule_builder import build_rules
    with pytest.raises(ValueError, match="at least one"):
        build_rules(system_dir, {}, catalog=catalog)


def test_build_rules_rejects_family_with_no_matching_variants(system_dir: Path, catalog: dict):
    from src.webui.rule_builder import build_rules
    with pytest.raises(ValueError, match="ewmac"):
        build_rules(system_dir, {"ewmac": ["999_999"]}, catalog=catalog)


def test_build_rules_requires_existing_config_dir(tmp_path: Path, catalog: dict):
    from src.webui.rule_builder import build_rules
    with pytest.raises(FileNotFoundError):
        build_rules(tmp_path / "no_such_system", {"ewmac": ["4_16"]}, catalog=catalog)

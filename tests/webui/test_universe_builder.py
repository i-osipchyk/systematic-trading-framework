from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

_CATALOG_YAML = textwrap.dedent("""
    instruments:
      US500:
        description: S&P 500 Index
        asset_type: index
        currency: USD
        weight: 0.03
        pointsize: 1.0
        spread_cost: 0.4
        lot_step: 0.1
        traded: true
        ctrader_symbol: US500
        yf_ticker: "^GSPC"
      NAS100:
        description: Nasdaq 100 Index
        asset_type: index
        currency: USD
        weight: 0.03
        pointsize: 1.0
        spread_cost: 1.0
        lot_step: 0.1
        traded: true
        ctrader_symbol: NAS100
      BUND:
        description: Euro Bund
        asset_type: bond
        currency: EUR
        weight: 0.03
        pointsize: 1000.0
        spread_cost: 0.3
        lot_step: 0.01
        traded: true
        ctrader_symbol: BUND
    """)


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    p = tmp_path / "universe_default.yaml"
    p.write_text(_CATALOG_YAML)
    return p


def test_load_candidate_catalog_parses_instruments_in_file_order(catalog_path: Path):
    from src.webui.universe_builder import load_candidate_catalog
    catalog = load_candidate_catalog(catalog_path)

    assert list(catalog.keys()) == ["US500", "NAS100", "BUND"]
    assert catalog["US500"]["asset_type"] == "index"
    assert catalog["US500"]["pointsize"] == 1.0


def test_load_candidate_catalog_on_real_config_file():
    from src.webui.universe_builder import DEFAULT_CATALOG_PATH, load_candidate_catalog
    catalog = load_candidate_catalog(DEFAULT_CATALOG_PATH)

    assert "US500" in catalog
    assert "XAU" in catalog
    assert len(catalog) >= 25


def test_correlation_hints_flags_known_cluster_when_both_present():
    from src.webui.universe_builder import correlation_hints
    hints = correlation_hints({"US500", "NAS100"})
    assert any("US500" in h and "NAS100" in h for h in hints)


def test_correlation_hints_empty_when_only_one_member_selected():
    from src.webui.universe_builder import correlation_hints
    hints = correlation_hints({"US500"})
    assert hints == []

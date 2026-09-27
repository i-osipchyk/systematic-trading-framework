from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.backtest import config as backtest_config

_INSTRUMENTS_YAML = textwrap.dedent("""
    instruments:
      US500:
        asset_type: index
        currency: USD
        weight: 0.5
        pointsize: 1.0
        spread_cost: 0.4
        lot_step: 0.1
        traded: true
      BUND:
        asset_type: bond
        currency: EUR
        weight: 0.5
        pointsize: 1.0
        spread_cost: 0.3
        lot_step: 0.1
        traded: true
      EURUSD:
        asset_type: currency
        currency: USD
        weight: 0.0
        pointsize: 1.0
        spread_cost: 0.1
        lot_step: 1.0
        traded: false
    """)

_RULES_YAML = textwrap.dedent("""
    rules:
      ewmac:
        pairs:
          - [16, 64]
          - [32, 128]
    """)

_BASE_YAML = textwrap.dedent("""
    timeframe: D1
    bars_per_year: 256
    capital: 100000
    """)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A minimal system config/ directory (instruments.yaml, rules.yaml, base.yaml).

    Also points src.backtest.config's global CONFIG_PATH at it, since the
    calibration steps read instrument/rule definitions through that global
    rather than through the state_dir argument.
    """
    d = tmp_path / "config"
    d.mkdir()
    (d / "instruments.yaml").write_text(_INSTRUMENTS_YAML)
    (d / "rules.yaml").write_text(_RULES_YAML)
    (d / "base.yaml").write_text(_BASE_YAML)
    backtest_config.set_config(d)
    yield d
    backtest_config.set_config(backtest_config._SYSTEMS_ROOT / "universe_v4" / "config")

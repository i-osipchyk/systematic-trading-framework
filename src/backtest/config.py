from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

_CONFIG_ROOT = Path(__file__).parents[2] / "config"
# Env var TRADING_CONFIG lets subprocesses inherit the active config
CONFIG_PATH: Path = Path(os.getenv("TRADING_CONFIG", str(_CONFIG_ROOT / "default.yaml")))


def set_config(path: str | Path) -> None:
    """Override the active config file. Call before any load_* functions."""
    global CONFIG_PATH
    CONFIG_PATH = Path(path)


def _load_raw() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class InstrumentConfig:
    code: str
    ctrader_symbol: str  # symbol name on the broker platform
    pointsize: float
    spread_cost: float
    lot_step: float      # minimum tradeable lot increment (e.g. 0.01 on Pepperstone)
    currency: str        # 'USD' | 'EUR' | 'GBP' | 'JPY'
    weight: float        # portfolio instrument weight (output of calibration step 06)
    asset_type: str      # 'crypto' | 'index' | 'commodity' | 'currency'
    traded: bool         # False = FX helper only, not in the live portfolio


def load_instrument_configs() -> dict[str, InstrumentConfig]:
    raw = _load_raw()["instruments"]
    return {
        code: InstrumentConfig(
            code=code,
            ctrader_symbol=cfg.get("ctrader_symbol", code),
            pointsize=float(cfg["pointsize"]),
            spread_cost=float(cfg["spread_cost"]),
            lot_step=float(cfg.get("lot_step", 0.01)),
            currency=cfg["currency"],
            weight=float(cfg.get("weight", 0.0)),
            asset_type=cfg.get("asset_type", cfg.get("asset_class", "unknown")).lower(),
            traded=bool(cfg.get("traded", True)),
        )
        for code, cfg in raw.items()
    }


def load_rules_config() -> dict:
    """Return the raw rules dict from the active config file."""
    return _load_raw()["rules"]


_TIMEFRAME_BARS_PER_YEAR: dict[str, int] = {
    "D1": 256,
    "H4": 1536,
    "H1": 6144,
    "M1": 368640,
}


def load_timeframe() -> str:
    """Return the bar period from the active config (default: D1)."""
    return _load_raw().get("timeframe", "D1")


def load_bars_per_year() -> int:
    """Return the annualisation factor (bars per trading year).

    Uses the explicit bars_per_year field if present; otherwise falls back to
    the built-in default for the configured timeframe.
    """
    raw = _load_raw()
    if "bars_per_year" in raw:
        return int(raw["bars_per_year"])
    return _TIMEFRAME_BARS_PER_YEAR.get(raw.get("timeframe", "D1"), 256)


def load_end_date() -> datetime | None:
    """Return the optional end_date from config, or None if not set.

    When set, the WF pipeline caps its data window at this date, enforcing
    the dev/test split without looking at out-of-bounds data.
    """
    from datetime import datetime, date
    raw = _load_raw()
    val = raw.get("end_date")
    if val is None:
        return None
    if isinstance(val, str):
        return datetime.strptime(val, "%Y-%m-%d")
    # yaml may parse a date literal as a date object
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    return None


def load_split_date() -> datetime | None:
    """Return the explicit IS/OOS split date from config, or None if not set.

    When set, calibration scripts use this date directly instead of computing
    a data-driven 70/30 split. Use this for test configs where the split is
    fixed at the dev/test boundary.
    """
    from datetime import datetime, date
    raw = _load_raw()
    val = raw.get("split_date")
    if val is None:
        return None
    if isinstance(val, str):
        return datetime.strptime(val, "%Y-%m-%d")
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    return None


def traded_instruments(cfgs: dict[str, InstrumentConfig]) -> list[str]:
    """Return codes of instruments marked traded=true, in config file order."""
    return [code for code, cfg in cfgs.items() if cfg.traded]


def required_fx_helpers(cfgs: dict[str, InstrumentConfig]) -> list[str]:
    """Auto-derive which FX instruments are needed for currency conversion.

    Account currency is USD. For each non-USD traded instrument:
      EUR instruments → EURUSD
      GBP instruments → EURUSD + EURGBP
      JPY instruments → USDJPY

    Any helper that is already a traded instrument is excluded.
    """
    traded_codes = set(traded_instruments(cfgs))
    currencies = {cfgs[code].currency for code in traded_codes}
    helpers: set[str] = set()
    if "EUR" in currencies:
        helpers.add("EURUSD")
    if "GBP" in currencies:
        helpers.add("EURUSD")
        helpers.add("EURGBP")
    if "JPY" in currencies:
        helpers.add("USDJPY")
    if "CAD" in currencies:
        helpers.add("USDCAD")
    return sorted(helpers - traded_codes)

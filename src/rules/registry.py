"""
Rule family registry.

Maps config block names to handler objects. Each handler provides a uniform
interface for computing forecasts and converting between YAML and native types.

Handler interface:
    compute_all(prices, vol, scalars)  -> pd.DataFrame
    compute_one_raw(prices, variant, vol) -> pd.Series   (scalar=1.0)
    variants_from_cfg(cfg_block)       -> list
    parse_scalars(raw)                 -> dict
    dump_scalars(scalars)              -> dict
    scalar_key(variant)                -> str
    rule_name(variant)                 -> str

Imports of rule modules are deferred inside methods to avoid circular imports.
"""
from __future__ import annotations

import pandas as pd


class EWMACHandler:
    def compute_all(
        self, prices: pd.Series, vol: pd.Series | None, scalars
    ) -> pd.DataFrame:
        import src.rules.ewmac as mod
        return mod.all_ewmac_forecasts(prices, vol, scalars=scalars)

    def compute_one_raw(
        self, prices: pd.Series, variant: tuple, vol: pd.Series | None
    ) -> pd.Series:
        import src.rules.ewmac as mod
        fast, slow = variant
        return mod.ewmac(prices, fast, slow, vol, scalar=1.0)

    def variants_from_cfg(self, cfg_block: dict) -> list:
        return [tuple(p) for p in cfg_block.get("pairs", [])]

    def parse_scalars(self, raw: dict) -> dict:
        return {tuple(int(x) for x in k.split("_")): float(v) for k, v in raw.items()}

    def dump_scalars(self, scalars: dict) -> dict:
        return {f"{f}_{s}": round(float(v), 4) for (f, s), v in scalars.items()}

    def scalar_key(self, variant: tuple) -> str:
        f, s = variant
        return f"{f}_{s}"

    def rule_name(self, variant: tuple) -> str:
        f, s = variant
        return f"EWMAC_{f}_{s}"


class MRHandler:
    def compute_all(
        self, prices: pd.Series, vol: pd.Series | None, scalars
    ) -> pd.DataFrame:
        import src.rules.mr as mod
        return mod.all_mr_forecasts(prices, vol, scalars=scalars)

    def compute_one_raw(
        self, prices: pd.Series, variant: int, vol: pd.Series | None
    ) -> pd.Series:
        import src.rules.mr as mod
        return mod.mean_reversion(prices, variant, vol, scalar=1.0)

    def variants_from_cfg(self, cfg_block: dict) -> list:
        return list(cfg_block.get("spans", []))

    def parse_scalars(self, raw: dict) -> dict:
        return {int(k): float(v) for k, v in raw.items()}

    def dump_scalars(self, scalars: dict) -> dict:
        return {str(k): round(float(v), 4) for k, v in scalars.items()}

    def scalar_key(self, variant: int) -> str:
        return str(variant)

    def rule_name(self, variant: int) -> str:
        return f"MR_{variant}"


class BreakoutHandler:
    def compute_all(
        self, prices: pd.Series, vol: pd.Series | None, scalars
    ) -> pd.DataFrame:
        import src.rules.breakout as mod
        return mod.all_breakout_forecasts(prices, scalars=scalars)

    def compute_one_raw(
        self, prices: pd.Series, variant: int, vol: pd.Series | None
    ) -> pd.Series:
        import src.rules.breakout as mod
        return mod.breakout(prices, variant, scalar=1.0)

    def variants_from_cfg(self, cfg_block: dict) -> list:
        return list(cfg_block.get("lookbacks", []))

    def parse_scalars(self, raw: dict) -> dict:
        return {int(k): float(v) for k, v in raw.items()}

    def dump_scalars(self, scalars: dict) -> dict:
        return {str(k): round(float(v), 4) for k, v in scalars.items()}

    def scalar_key(self, variant: int) -> str:
        return str(variant)

    def rule_name(self, variant: int) -> str:
        return f"BREAKOUT_{variant}"


class TSMOMHandler:
    def compute_all(
        self, prices: pd.Series, vol: pd.Series | None, scalars
    ) -> pd.DataFrame:
        import src.rules.tsmom as mod
        return mod.all_tsmom_forecasts(prices, scalars=scalars)

    def compute_one_raw(
        self, prices: pd.Series, variant: int, vol: pd.Series | None
    ) -> pd.Series:
        import src.rules.tsmom as mod
        return mod.tsmom(prices, variant, scalar=1.0)

    def variants_from_cfg(self, cfg_block: dict) -> list:
        return list(cfg_block.get("lookbacks", []))

    def parse_scalars(self, raw: dict) -> dict:
        return {int(k): float(v) for k, v in raw.items()}

    def dump_scalars(self, scalars: dict) -> dict:
        return {str(k): round(float(v), 4) for k, v in scalars.items()}

    def scalar_key(self, variant: int) -> str:
        return str(variant)

    def rule_name(self, variant: int) -> str:
        return f"TSMOM_{variant}"


REGISTRY: dict[str, object] = {
    "ewmac": EWMACHandler(),
    "mr": MRHandler(),
    "breakout": BreakoutHandler(),
    "tsmom": TSMOMHandler(),
}

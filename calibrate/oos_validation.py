"""
OOS validation: IS vs Val (2010-2017) SR breakdown by instrument, asset class, and rule.

For each rule: computes isolated single-rule portfolio SR (one rule at a time, 100% weight,
no FDM, IDM kept so leverage is comparable across rules).
For asset classes: aggregates per-instrument PnL by group.

Usage:
    TRADING_CONFIG=config/universe_40yr_wf.yaml uv run python calibrate/oos_validation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_instrument_configs, traded_instruments, required_fx_helpers
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.metrics import performance_report, TRADING_DAYS_PER_YEAR
from src.backtest.pnl import gross_pnl, transaction_costs, to_usd
from src.backtest.sizing import compute_positions
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

IS_END   = pd.Timestamp("2010-01-01")
VAL_END  = pd.Timestamp("2018-01-01")
CAPITAL  = 10_000.0
VOL_TGT  = 0.15
IDM      = 2.500

GROUPS: dict[str, list[str]] = {
    "FX":          ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD"],
    "Equities":    ["US500", "NAS100", "GER40", "JPN225", "HK50"],
    "Bonds":       ["US2YR", "US5YR", "US10YR", "US30YR", "BUND"],
    "Commodities": ["XAU", "XAG", "COPPER", "SpotCrude", "NatGas",
                    "Coffee", "Cocoa", "Sugar", "Corn", "Cotton"],
}

ALL_RULES = ["EWMAC_8_32", "EWMAC_32_128", "EWMAC_64_256", "BREAKOUT_20", "CARRY", "SEASONALITY"]


def _sr(pnl: pd.Series, capital: float = CAPITAL) -> float:
    r = pnl / capital
    if r.std() == 0 or len(r.dropna()) < 20:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def _ret(pnl: pd.Series, capital: float = CAPITAL) -> float:
    n = len(pnl.dropna())
    if n == 0:
        return float("nan")
    return float(pnl.sum() / capital * TRADING_DAYS_PER_YEAR / n)


def main() -> None:
    scalars_data  = st.load("step3a_scalars.yaml")
    weights_data  = st.load("step3d_forecast_weights.yaml")
    fdm_data      = st.load("step3d_fdm.yaml")
    inst_wts_data = st.load("step4a_instrument_weights.yaml")

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }
    instrument_weights: dict[str, float] = {
        k: float(v) for k, v in inst_wts_data["instrument_weights"].items()
    }

    cfgs      = load_instrument_configs()
    codes     = traded_instruments(cfgs)

    # FX helpers
    fx_helpers = required_fx_helpers(cfgs)
    all_fx_keys = set(fx_helpers) | {"EURUSD", "EURGBP", "USDJPY", "USDCAD"}
    fx_prices = {}
    for k in all_fx_keys:
        try:
            fx_prices[k] = load_adjusted_prices(k)
        except FileNotFoundError:
            pass
    eurusd = fx_prices.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices.get("USDJPY", pd.Series(dtype=float))
    usdcad = fx_prices.get("USDCAD", pd.Series(dtype=float))

    # ── Pre-load prices and build per-instrument full-period PnL ─────────────
    # combined_pnl[code] → full-history net PnL series
    # rule_pnl[rule][code] → full-history gross PnL for isolated rule
    combined_pnl: dict[str, pd.Series]       = {}
    rule_pnl: dict[str, dict[str, pd.Series]] = {r: {} for r in ALL_RULES}

    for code in codes:
        if code not in cfgs:
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_data, _ = split_series(prices, IS_END)
        if len(is_data) < 20:
            continue

        cfg  = cfgs[code]
        vol  = daily_vol(prices)
        fdm  = float(fdm_data.get(code, 1.0))
        w    = instrument_weights.get(code, cfg.weight)
        fx   = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, prices.index,
                               usdjpy_prices=usdjpy, usdcad_prices=usdcad)

        # ── Combined forecast PnL ────────────────────────────────────────────
        fc = combined_forecast(prices, vol, fdm=fdm,
                               family_scalars=family_scalars,
                               rule_weights=rule_weights,
                               instrument_code=code)
        pos = compute_positions(prices=prices, vol=vol, forecast=fc["combined"],
                                pointsize=cfg.pointsize, capital=CAPITAL,
                                vol_target=VOL_TGT, idm=IDM, fx_rate_to_usd=fx,
                                instrument_weight=w)
        gpnl_n  = gross_pnl(pos, prices, cfg.pointsize)
        costs_n = transaction_costs(pos, cfg.spread_cost, cfg.pointsize)
        net_n   = to_usd(gpnl_n - costs_n, cfg.currency, eurusd, eurgbp, usdjpy, usdcad)
        combined_pnl[code] = net_n

        # ── Per-rule isolated PnL ────────────────────────────────────────────
        for family_name, fam_scalars in family_scalars.items():
            handler = REGISTRY[family_name]

            if family_name == "seasonality":
                rule_name = "SEASONALITY"
                fc_df = handler.compute_all(prices, vol, fam_scalars, instrument_code=code)
                if "SEASONALITY" not in fc_df.columns:
                    continue
                rule_fc = fc_df["SEASONALITY"].clip(-20, 20)
                rule_pos = compute_positions(prices=prices, vol=vol, forecast=rule_fc,
                                            pointsize=cfg.pointsize, capital=CAPITAL,
                                            vol_target=VOL_TGT, idm=IDM, fx_rate_to_usd=fx,
                                            instrument_weight=w)
                gpnl_r = gross_pnl(rule_pos, prices, cfg.pointsize)
                pnl_r  = to_usd(gpnl_r, cfg.currency, eurusd, eurgbp, usdjpy, usdcad)
                rule_pnl[rule_name][code] = pnl_r
                continue

            for variant, scalar in fam_scalars.items():
                rule_name = handler.rule_name(variant)
                raw = handler.compute_one_raw(prices, variant, vol, instrument_code=code)
                rule_fc = (raw * scalar).clip(-20, 20)
                rule_pos = compute_positions(prices=prices, vol=vol, forecast=rule_fc,
                                            pointsize=cfg.pointsize, capital=CAPITAL,
                                            vol_target=VOL_TGT, idm=IDM, fx_rate_to_usd=fx,
                                            instrument_weight=w)
                gpnl_r = gross_pnl(rule_pos, prices, cfg.pointsize)
                pnl_r  = to_usd(gpnl_r, cfg.currency, eurusd, eurgbp, usdjpy, usdcad)
                rule_pnl[rule_name][code] = pnl_r

    # ── TABLE 1: Per-instrument IS vs Val SR ─────────────────────────────────
    print("\n" + "=" * 62)
    print("  TABLE 1 — Per-instrument SR (IS 1984–2010 | Val 2010–2017)")
    print("=" * 62)
    hdr = f"  {'Instrument':<12} {'IS SR':>7} {'Val SR':>8}  {'IS Ret':>7} {'Val Ret':>8}"
    print(hdr)
    print("  " + "─" * 50)

    inst_is_pnl:  dict[str, pd.Series] = {}
    inst_val_pnl: dict[str, pd.Series] = {}

    for grp_name, grp_codes in GROUPS.items():
        print(f"  {grp_name}")
        for code in grp_codes:
            if code not in combined_pnl:
                continue
            pnl = combined_pnl[code]
            is_p  = pnl[pnl.index < IS_END]
            val_p = pnl[(pnl.index >= IS_END) & (pnl.index < VAL_END)]
            inst_is_pnl[code]  = is_p
            inst_val_pnl[code] = val_p
            sr_is  = _sr(is_p)
            sr_val = _sr(val_p)
            r_is   = _ret(is_p)
            r_val  = _ret(val_p)
            flag = " *" if sr_val < -0.30 else ""
            print(f"  {'  '+code:<12} {sr_is:>7.2f} {sr_val:>8.2f}  {r_is:>6.1%} {r_val:>8.1%}{flag}")

    # Portfolio totals — fill_value=0 so instruments not yet active don't propagate NaN
    port_is  = pd.DataFrame(inst_is_pnl).fillna(0).sum(axis=1)
    port_val = pd.DataFrame(inst_val_pnl).fillna(0).sum(axis=1)
    print("  " + "─" * 50)
    print(f"  {'  PORTFOLIO':<12} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f}  "
          f"{_ret(port_is):>6.1%} {_ret(port_val):>8.1%}")

    # ── TABLE 2: Per-asset-class IS vs Val SR ────────────────────────────────
    print("\n" + "=" * 62)
    print("  TABLE 2 — Asset class SR (IS 1984–2010 | Val 2010–2017)")
    print("=" * 62)
    hdr2 = f"  {'Asset class':<14} {'IS SR':>7} {'Val SR':>8}  {'IS Ret':>7} {'Val Ret':>8}"
    print(hdr2)
    print("  " + "─" * 50)

    for grp_name, grp_codes in GROUPS.items():
        grp_is_dict  = {c: inst_is_pnl[c]  for c in grp_codes if c in inst_is_pnl}
        grp_val_dict = {c: inst_val_pnl[c] for c in grp_codes if c in inst_val_pnl}
        if not grp_is_dict:
            continue
        grp_is  = pd.DataFrame(grp_is_dict).fillna(0).sum(axis=1)
        grp_val = pd.DataFrame(grp_val_dict).fillna(0).sum(axis=1)
        print(f"  {grp_name:<14} {_sr(grp_is):>7.2f} {_sr(grp_val):>8.2f}  "
              f"{_ret(grp_is):>6.1%} {_ret(grp_val):>8.1%}")

    print("  " + "─" * 50)
    print(f"  {'PORTFOLIO':<14} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f}  "
          f"{_ret(port_is):>6.1%} {_ret(port_val):>8.1%}")

    # ── TABLE 3: Per-rule IS vs Val SR (portfolio-level, each rule in isolation) ──
    print("\n" + "=" * 62)
    print("  TABLE 3 — Rule SR (isolated, full portfolio, IS vs Val)")
    print("=" * 62)
    hdr3 = f"  {'Rule':<16} {'IS SR':>7} {'Val SR':>8}  {'IS Ret':>7} {'Val Ret':>8}"
    print(hdr3)
    print("  " + "─" * 50)

    for rule in ALL_RULES:
        r_pnl = rule_pnl.get(rule, {})
        if not r_pnl:
            continue
        rule_is_dict  = {c: s[s.index < IS_END]                             for c, s in r_pnl.items()}
        rule_val_dict = {c: s[(s.index >= IS_END) & (s.index < VAL_END)]    for c, s in r_pnl.items()}
        rule_is_sum  = pd.DataFrame(rule_is_dict).fillna(0).sum(axis=1)
        rule_val_sum = pd.DataFrame(rule_val_dict).fillna(0).sum(axis=1)
        print(f"  {rule:<16} {_sr(rule_is_sum):>7.2f} {_sr(rule_val_sum):>8.2f}  "
              f"{_ret(rule_is_sum):>6.1%} {_ret(rule_val_sum):>8.1%}")

    print("  " + "─" * 50)
    print(f"  {'COMBINED':<16} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f}  "
          f"{_ret(port_is):>6.1%} {_ret(port_val):>8.1%}")
    print()
    print("  Note: rule SR uses isolated single-rule positions (100% weight, no FDM).")
    print("  Combined SR uses full calibrated parameters including FDMs.")
    print("  (* = Val SR < -0.30)")


if __name__ == "__main__":
    main()

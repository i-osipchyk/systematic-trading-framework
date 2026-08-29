"""
OOS validation: IS vs Val (2010–2017) SR breakdown by instrument, asset class, and rule.

Loads all calibrated parameters from the given run directory, then runs IS and
Val periods for each instrument and rule in isolation.

INPUT STATE FILES (from system config/ directory):
  - step3.yaml  (sections: scalars, forecast_weights, fdm)
  - step4.yaml  (sections: instrument_weights, idm)

OUTPUT: printed tables + results/step6.md (portfolio, asset class, rule, family,
  and per-instrument IS/Val/Test SR; val_weak flags for instruments with Val SR < -0.30).

Flags:
  --system PATH       system directory (default: systems/universe_v4)
  --include-all       include all instruments regardless of 'traded: false' in config

Usage:
    uv run python calibrate/oos_validation.py --system systems/universe_v4
    uv run python calibrate/oos_validation.py --system systems/universe_v4 --include-all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import io

import numpy as np
import pandas as pd


class _Tee:
    """Write to both the original stdout and an internal buffer."""
    def __init__(self, orig):
        self._orig = orig
        self._buf = io.StringIO()

    def write(self, data):
        self._orig.write(data)
        self._buf.write(data)

    def flush(self):
        self._orig.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue()


sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import load_capital, load_instrument_configs, set_config, traded_instruments, required_fx_helpers
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.metrics import performance_report, TRADING_DAYS_PER_YEAR
from src.backtest.pnl import gross_pnl, transaction_costs, to_usd
from src.backtest.sizing import apply_inertia, compute_positions, round_to_lot
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

_VOL_PLACEHOLDER = 0.20  # must match step5_calibrate._VOL_PLACEHOLDER so IS SR is comparable
_ctx = {"capital": 100_000.0}  # mutable; main() sets the real value from config before computing

GROUPS: dict[str, list[str]] = {
    "FX":       ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD"],
    "Equities": ["US500", "NAS100", "GER40", "JPN225", "HK50", "UK100"],
    "Bonds":    ["US2YR", "US5YR", "US10YR", "US30YR", "BUND"],
    "Metals":   ["XAU", "XAG", "COPPER"],
    "Energy":   ["SpotCrude", "Gasoline"],
    "Ags":      ["Coffee", "Cocoa", "Sugar", "Corn", "Cotton", "Soybeans", "Wheat"],
}


def _sr(pnl: pd.Series) -> float:
    cap = _ctx["capital"]
    r = pnl / cap
    if r.std() == 0 or len(r.dropna()) < 20:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def _ret(pnl: pd.Series) -> float:
    n = len(pnl.dropna())
    if n == 0:
        return float("nan")
    return float(pnl.sum() / _ctx["capital"] * TRADING_DAYS_PER_YEAR / n)


def _mdd(pnl: pd.Series) -> float:
    if len(pnl.dropna()) < 2:
        return float("nan")
    r = pnl / _ctx["capital"]
    equity = (1 + r).cumprod()
    hwm = equity.cummax()
    dd = (equity - hwm) / hwm
    return float(dd.min())


def main(state_dir=None, include_all: bool = False, vol_target: float | None = None, report_dir=None) -> dict:
    # All metrics use _VOL_PLACEHOLDER (same as step5) so IS SR is directly comparable.
    # The confirmed vol_target from step5.yaml is read for the footer display only.
    vol_target_display: float | None = None
    try:
        vol_target_display = float(st.load_section("step5.yaml", "vol_target", state_dir=state_dir))
    except Exception:
        pass
    vol_target = _VOL_PLACEHOLDER  # position sizing; ignore any passed-in override

    capital = load_capital()
    _ctx["capital"] = capital

    # Use the same IS split date as step5 / run_portfolio
    is_end = pd.Timestamp(compute_split_date())

    scalars_data  = st.load_section("step3.yaml", "scalars",           state_dir=state_dir)
    weights_data  = st.load_section("step3.yaml", "forecast_weights",  state_dir=state_dir)
    fdm_data      = st.load_section("step3.yaml", "fdm",               state_dir=state_dir)
    inst_wts_data = st.load_section("step4.yaml", "instrument_weights", state_dir=state_dir)
    idm_data      = st.load_section("step4.yaml", "idm",               state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {k: float(v) for k, v in weights_data.items()}
    instrument_weights: dict[str, float] = {k: float(v) for k, v in inst_wts_data.items()}
    idm = float(idm_data)

    # Rule names come from the loaded forecast weights — no hardcoded list
    all_rules = list(rule_weights.keys())

    cfgs = load_instrument_configs()
    if include_all:
        codes = list(cfgs.keys())
    else:
        codes = traded_instruments(cfgs)

    # Val/test boundary: midpoint of the OOS window, computed from price data.
    # Avoids empty val periods when IS ends near or after a hard-coded date.
    _data_ends = []
    for _code in codes:
        try:
            _data_ends.append(load_adjusted_prices(_code).index.max())
        except FileNotFoundError:
            pass
    data_end = pd.Timestamp(max(_data_ends)) if _data_ends else is_end + pd.DateOffset(years=4)
    val_end = is_end + (data_end - is_end) / 2

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

    combined_pnl: dict[str, pd.Series]        = {}
    rule_pnl: dict[str, dict[str, pd.Series]] = {r: {} for r in all_rules}

    for code in codes:
        if code not in cfgs:
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_data, _ = split_series(prices, is_end)
        if len(is_data) < 20:
            continue

        cfg = cfgs[code]
        vol = daily_vol(prices)
        fdm = float(fdm_data.get(code, 1.0))
        w   = instrument_weights.get(code, cfg.weight)
        fx  = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, prices.index,
                              usdjpy_prices=usdjpy, usdcad_prices=usdcad)

        # Combined forecast PnL (with rounding and position inertia)
        fc = combined_forecast(prices, vol, fdm=fdm,
                               family_scalars=family_scalars,
                               rule_weights=rule_weights,
                               instrument_code=code)
        pos = compute_positions(prices=prices, vol=vol, forecast=fc["combined"],
                                pointsize=cfg.pointsize, capital=capital,
                                vol_target=vol_target, idm=idm, fx_rate_to_usd=fx,
                                instrument_weight=w)
        pos = apply_inertia(round_to_lot(pos, cfg.lot_step))
        gpnl_n  = gross_pnl(pos, prices, cfg.pointsize)
        costs_n = transaction_costs(pos, cfg.spread_cost, cfg.pointsize)
        combined_pnl[code] = to_usd(gpnl_n - costs_n, cfg.currency,
                                    eurusd, eurgbp, usdjpy, usdcad)

        # Per-rule isolated PnL
        for family_name, fam_scalars in family_scalars.items():
            handler = REGISTRY[family_name]

            if family_name == "seasonality":
                rule_name = "SEASONALITY"
                if rule_name not in rule_pnl:
                    continue
                fc_df = handler.compute_all(prices, vol, fam_scalars, instrument_code=code)
                if "SEASONALITY" not in fc_df.columns:
                    continue
                rule_fc = fc_df["SEASONALITY"].clip(-20, 20)
                rule_pos = compute_positions(prices=prices, vol=vol, forecast=rule_fc,
                                            pointsize=cfg.pointsize, capital=capital,
                                            vol_target=vol_target, idm=idm, fx_rate_to_usd=fx,
                                            instrument_weight=w)
                gpnl_r = gross_pnl(rule_pos, prices, cfg.pointsize)
                rule_pnl[rule_name][code] = to_usd(gpnl_r, cfg.currency,
                                                   eurusd, eurgbp, usdjpy, usdcad)
                continue

            for variant, scalar in fam_scalars.items():
                rule_name = handler.rule_name(variant)
                if rule_name not in rule_pnl:
                    continue
                raw = handler.compute_one_raw(prices, variant, vol, instrument_code=code)
                rule_fc = (raw * scalar).clip(-20, 20)
                rule_pos = compute_positions(prices=prices, vol=vol, forecast=rule_fc,
                                            pointsize=cfg.pointsize, capital=capital,
                                            vol_target=vol_target, idm=idm, fx_rate_to_usd=fx,
                                            instrument_weight=w)
                gpnl_r = gross_pnl(rule_pos, prices, cfg.pointsize)
                rule_pnl[rule_name][code] = to_usd(gpnl_r, cfg.currency,
                                                   eurusd, eurgbp, usdjpy, usdcad)

    def _split3(pnl: pd.Series):
        is_p   = pnl[pnl.index < is_end]
        val_p  = pnl[(pnl.index >= is_end) & (pnl.index < val_end)]
        test_p = pnl[pnl.index >= val_end]
        return is_p, val_p, test_p

    tee = _Tee(sys.stdout)
    sys.stdout = tee

    if include_all:
        print("  (--include-all: showing all instruments regardless of 'traded' flag)")
        print(f"  Calibrated weights used for {len(instrument_weights)} instruments; "
              f"config default weight for the rest.\n")

    # ── TABLE 1: Per-instrument IS | Val | Test SR ───────────────────────────
    print("\n" + "=" * 78)
    print(f"  TABLE 1 — Per-instrument SR  (IS –{is_end.year} | Val {is_end.year}–{val_end.year} | Test {val_end.year}–)")
    print("=" * 78)
    hdr = (f"  {'Instrument':<12} {'IS SR':>7} {'Val SR':>8} {'Test SR':>8}"
           f"  {'IS Ret':>7} {'Val Ret':>8} {'Test Ret':>9}")
    print(hdr)
    print("  " + "─" * 66)

    inst_is_pnl:   dict[str, pd.Series] = {}
    inst_val_pnl:  dict[str, pd.Series] = {}
    inst_test_pnl: dict[str, pd.Series] = {}

    for grp_name, grp_codes in GROUPS.items():
        print(f"  {grp_name}")
        for code in grp_codes:
            if code not in combined_pnl:
                continue
            is_p, val_p, test_p = _split3(combined_pnl[code])
            inst_is_pnl[code]   = is_p
            inst_val_pnl[code]  = val_p
            inst_test_pnl[code] = test_p
            traded_flag = "" if cfgs[code].traded else " [excl]"
            flag = " *" if _sr(val_p) < -0.30 else ""
            print(f"  {'  '+code:<12} {_sr(is_p):>7.2f} {_sr(val_p):>8.2f} {_sr(test_p):>8.2f}"
                  f"  {_ret(is_p):>6.1%} {_ret(val_p):>8.1%} {_ret(test_p):>9.1%}"
                  f"{flag}{traded_flag}")

    port_is   = pd.DataFrame(inst_is_pnl).fillna(0).sum(axis=1)
    port_val  = pd.DataFrame(inst_val_pnl).fillna(0).sum(axis=1)
    port_test = pd.DataFrame(inst_test_pnl).fillna(0).sum(axis=1)
    print("  " + "─" * 66)
    print(f"  {'  PORTFOLIO':<12} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f} {_sr(port_test):>8.2f}"
          f"  {_ret(port_is):>6.1%} {_ret(port_val):>8.1%} {_ret(port_test):>9.1%}")
    print(f"  {'  Max DD':<12} {'':>7} {'':>8} {'':>8}"
          f"  {_mdd(port_is):>6.1%} {_mdd(port_val):>8.1%} {_mdd(port_test):>9.1%}")

    # ── TABLE 2: Per-asset-class IS | Val | Test SR ──────────────────────────
    print("\n" + "=" * 78)
    print(f"  TABLE 2 — Asset class SR  (IS –{is_end.year} | Val {is_end.year}–{val_end.year} | Test {val_end.year}–)")
    print("=" * 78)
    hdr2 = (f"  {'Asset class':<14} {'IS SR':>7} {'Val SR':>8} {'Test SR':>8}"
            f"  {'IS Ret':>7} {'Val Ret':>8} {'Test Ret':>9}")
    print(hdr2)
    print("  " + "─" * 66)

    for grp_name, grp_codes in GROUPS.items():
        grp_is_dict   = {c: inst_is_pnl[c]   for c in grp_codes if c in inst_is_pnl}
        grp_val_dict  = {c: inst_val_pnl[c]  for c in grp_codes if c in inst_val_pnl}
        grp_test_dict = {c: inst_test_pnl[c] for c in grp_codes if c in inst_test_pnl}
        if not grp_is_dict:
            continue
        grp_is   = pd.DataFrame(grp_is_dict).fillna(0).sum(axis=1)
        grp_val  = pd.DataFrame(grp_val_dict).fillna(0).sum(axis=1)
        grp_test = pd.DataFrame(grp_test_dict).fillna(0).sum(axis=1)
        print(f"  {grp_name:<14} {_sr(grp_is):>7.2f} {_sr(grp_val):>8.2f} {_sr(grp_test):>8.2f}"
              f"  {_ret(grp_is):>6.1%} {_ret(grp_val):>8.1%} {_ret(grp_test):>9.1%}")

    print("  " + "─" * 66)
    print(f"  {'PORTFOLIO':<14} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f} {_sr(port_test):>8.2f}"
          f"  {_ret(port_is):>6.1%} {_ret(port_val):>8.1%} {_ret(port_test):>9.1%}")

    # ── TABLE 3: Per-rule IS | Val | Test SR ─────────────────────────────────
    print("\n" + "=" * 78)
    print("  TABLE 3 — Rule SR  (isolated, full portfolio, IS | Val | Test)")
    print("=" * 78)
    hdr3 = (f"  {'Rule':<16} {'IS SR':>7} {'Val SR':>8} {'Test SR':>8}"
            f"  {'IS Ret':>7} {'Val Ret':>8} {'Test Ret':>9}")
    print(hdr3)
    print("  " + "─" * 66)

    for rule in all_rules:
        r_pnl = rule_pnl.get(rule, {})
        if not r_pnl:
            continue
        r_is_dict   = {c: _split3(s)[0] for c, s in r_pnl.items()}
        r_val_dict  = {c: _split3(s)[1] for c, s in r_pnl.items()}
        r_test_dict = {c: _split3(s)[2] for c, s in r_pnl.items()}
        r_is   = pd.DataFrame(r_is_dict).fillna(0).sum(axis=1)
        r_val  = pd.DataFrame(r_val_dict).fillna(0).sum(axis=1)
        r_test = pd.DataFrame(r_test_dict).fillna(0).sum(axis=1)
        print(f"  {rule:<16} {_sr(r_is):>7.2f} {_sr(r_val):>8.2f} {_sr(r_test):>8.2f}"
              f"  {_ret(r_is):>6.1%} {_ret(r_val):>8.1%} {_ret(r_test):>9.1%}")

    print("  " + "─" * 66)
    print(f"  {'COMBINED':<16} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f} {_sr(port_test):>8.2f}"
          f"  {_ret(port_is):>6.1%} {_ret(port_val):>8.1%} {_ret(port_test):>9.1%}")

    # ── TABLE 4: Per-rule-family IS | Val | Test SR ───────────────────────────
    family_map: dict[str, list[str]] = {}
    for rule in all_rules:
        if rule.startswith("EWMAC"):
            family_map.setdefault("Trend", []).append(rule)
        elif rule == "CARRY":
            family_map.setdefault("Carry", []).append(rule)
        elif rule == "SEASONALITY":
            family_map.setdefault("Seasonality", []).append(rule)
        else:
            family_map.setdefault("Other", []).append(rule)

    print("\n" + "=" * 78)
    print("  TABLE 4 — Rule family SR  (equal-weight within family, IS | Val | Test)")
    print("=" * 78)
    hdr4 = (f"  {'Family':<16} {'Rules':>5} {'IS SR':>7} {'Val SR':>8} {'Test SR':>8}"
            f"  {'IS Ret':>7} {'Val Ret':>8} {'Test Ret':>9}")
    print(hdr4)
    print("  " + "─" * 71)

    for fam_name, fam_rules in family_map.items():
        fam_is_parts, fam_val_parts, fam_test_parts = [], [], []
        for rule in fam_rules:
            r_pnl = rule_pnl.get(rule, {})
            if not r_pnl:
                continue
            r_is_dict   = {c: _split3(s)[0] for c, s in r_pnl.items()}
            r_val_dict  = {c: _split3(s)[1] for c, s in r_pnl.items()}
            r_test_dict = {c: _split3(s)[2] for c, s in r_pnl.items()}
            fam_is_parts.append(pd.DataFrame(r_is_dict).fillna(0).sum(axis=1))
            fam_val_parts.append(pd.DataFrame(r_val_dict).fillna(0).sum(axis=1))
            fam_test_parts.append(pd.DataFrame(r_test_dict).fillna(0).sum(axis=1))
        if not fam_is_parts:
            continue
        fam_is   = pd.concat(fam_is_parts,   axis=1).fillna(0).mean(axis=1)
        fam_val  = pd.concat(fam_val_parts,  axis=1).fillna(0).mean(axis=1)
        fam_test = pd.concat(fam_test_parts, axis=1).fillna(0).mean(axis=1)
        print(f"  {fam_name:<16} {len(fam_rules):>5} {_sr(fam_is):>7.2f} {_sr(fam_val):>8.2f} {_sr(fam_test):>8.2f}"
              f"  {_ret(fam_is):>6.1%} {_ret(fam_val):>8.1%} {_ret(fam_test):>9.1%}")

    print("  " + "─" * 71)
    print(f"  {'COMBINED':<16} {'':>5} {_sr(port_is):>7.2f} {_sr(port_val):>8.2f} {_sr(port_test):>8.2f}"
          f"  {_ret(port_is):>6.1%} {_ret(port_val):>8.1%} {_ret(port_test):>9.1%}")
    print()
    confirmed_str = f"  (confirmed vol target: {vol_target_display:.0%})" if vol_target_display else ""
    print(f"  Metrics computed at vol placeholder: {vol_target:.0%}{confirmed_str}   Capital: ${capital:,.0f}")
    print("  Note: rule/family SR uses isolated single-rule positions (no FDM, no rounding, no inertia).")
    print("  Family SR = equal-weight mean across member rules.")
    print("  Combined SR uses full calibrated parameters (FDMs, IDM, instrument weights, rounding, inertia).")
    print("  (* = Val SR < -0.30   [excl] = excluded in active config)")

    sys.stdout = tee._orig
    _md_content = tee.getvalue()

    # ── Build structured results and save step6.yaml ─────────────────────────
    def _row(is_s, val_s, test_s):
        return {
            "is":   {"sr": round(_sr(is_s), 3),  "ret": round(_ret(is_s), 4)},
            "val":  {"sr": round(_sr(val_s), 3),  "ret": round(_ret(val_s), 4)},
            "test": {"sr": round(_sr(test_s), 3), "ret": round(_ret(test_s), 4)},
        }

    instruments_out = {}
    for grp_codes in GROUPS.values():
        for code in grp_codes:
            if code not in inst_is_pnl:
                continue
            row = _row(inst_is_pnl[code], inst_val_pnl[code], inst_test_pnl[code])
            row["val_flagged"] = _sr(inst_val_pnl[code]) < -0.30
            instruments_out[code] = row

    asset_classes_out = {}
    for grp_name, grp_codes in GROUPS.items():
        grp_is   = pd.DataFrame({c: inst_is_pnl[c]   for c in grp_codes if c in inst_is_pnl}).fillna(0).sum(axis=1)
        grp_val  = pd.DataFrame({c: inst_val_pnl[c]  for c in grp_codes if c in inst_val_pnl}).fillna(0).sum(axis=1)
        grp_test = pd.DataFrame({c: inst_test_pnl[c] for c in grp_codes if c in inst_test_pnl}).fillna(0).sum(axis=1)
        if grp_is.empty:
            continue
        asset_classes_out[grp_name] = _row(grp_is, grp_val, grp_test)

    rules_out = {}
    for rule in all_rules:
        r_pnl = rule_pnl.get(rule, {})
        if not r_pnl:
            continue
        r_is   = pd.DataFrame({c: _split3(s)[0] for c, s in r_pnl.items()}).fillna(0).sum(axis=1)
        r_val  = pd.DataFrame({c: _split3(s)[1] for c, s in r_pnl.items()}).fillna(0).sum(axis=1)
        r_test = pd.DataFrame({c: _split3(s)[2] for c, s in r_pnl.items()}).fillna(0).sum(axis=1)
        rules_out[rule] = _row(r_is, r_val, r_test)

    families_out = {}
    for fam_name, fam_rules in family_map.items():
        fam_is_parts, fam_val_parts, fam_test_parts = [], [], []
        for rule in fam_rules:
            r_pnl = rule_pnl.get(rule, {})
            if not r_pnl:
                continue
            fam_is_parts.append(pd.DataFrame({c: _split3(s)[0] for c, s in r_pnl.items()}).fillna(0).sum(axis=1))
            fam_val_parts.append(pd.DataFrame({c: _split3(s)[1] for c, s in r_pnl.items()}).fillna(0).sum(axis=1))
            fam_test_parts.append(pd.DataFrame({c: _split3(s)[2] for c, s in r_pnl.items()}).fillna(0).sum(axis=1))
        if not fam_is_parts:
            continue
        row = _row(
            pd.concat(fam_is_parts,   axis=1).fillna(0).mean(axis=1),
            pd.concat(fam_val_parts,  axis=1).fillna(0).mean(axis=1),
            pd.concat(fam_test_parts, axis=1).fillna(0).mean(axis=1),
        )
        row["n_rules"] = len(fam_rules)
        families_out[fam_name] = row

    val_weak = [c for c, v in instruments_out.items() if v["val_flagged"]]

    portfolio_row = _row(port_is, port_val, port_test)
    portfolio_row["is"]["max_dd"]   = round(_mdd(port_is),   4)
    portfolio_row["val"]["max_dd"]  = round(_mdd(port_val),  4)
    portfolio_row["test"]["max_dd"] = round(_mdd(port_test), 4)

    if report_dir is None:
        report_dir = Path(state_dir).parent / "results" if state_dir else None

    if report_dir is not None:
        md_path = Path(report_dir) / "step6.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(md_path, "w") as f:
            f.write("```\n")
            f.write(_md_content)
            f.write("```\n")
        print(f"\n  Results saved → {md_path}")

    summary = {
        "is_sr":         portfolio_row["is"]["sr"],
        "val_sr":        portfolio_row["val"]["sr"],
        "test_sr":       portfolio_row["test"]["sr"],
        "is_ret":        portfolio_row["is"]["ret"],
        "val_ret":       portfolio_row["val"]["ret"],
        "test_ret":      portfolio_row["test"]["ret"],
        "is_max_dd":     portfolio_row["is"]["max_dd"],
        "val_max_dd":    portfolio_row["val"]["max_dd"],
        "test_max_dd":   portfolio_row["test"]["max_dd"],
        "val_weak_flags": val_weak,
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OOS validation")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    parser.add_argument("--include-all", action="store_true",
                        help="Include all instruments regardless of 'traded: false'")
    parser.add_argument("--vol-target", type=float, default=None,
                        metavar="FLOAT", help="Override vol target (default: read from step5.yaml)")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "config", include_all=args.include_all, vol_target=args.vol_target)

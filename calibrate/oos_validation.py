"""
OOS validation: IS vs Test SR breakdown by instrument, asset class, and rule.

Loads all calibrated parameters from the given run directory, then runs IS and
Test (the full OOS window, one-shot) periods for each instrument and rule in
isolation.

INPUT STATE FILES (from system config/ directory):
  - step3.yaml  (sections: scalars, forecast_weights, fdm)
  - step4.yaml  (sections: instrument_weights, idm)

OUTPUT: printed tables + results/step6.md (portfolio, asset class, rule, family,
  and per-instrument IS/Test SR; test_weak flags for instruments with Test SR < -0.30).

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
from src.backtest.metrics import equity_curve, performance_report, TRADING_DAYS_PER_YEAR
from src.backtest.pnl import gross_pnl, transaction_costs, to_usd
from src.backtest.sizing import apply_inertia, compute_positions, round_to_lot
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

_VOL_PLACEHOLDER = 0.20  # default when no vol_target is passed in (matches step5_calibrate's placeholder)
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


def _compute(vol_target: float | None, state_dir=None, include_all: bool = False) -> dict:
    """Run the isolated per-instrument / per-rule OOS backtests at `vol_target`
    (falls back to the 0.20 first-look placeholder) and return the raw pnl series
    every table and the equity curve are built from. Pure computation, no printing
    — shared by the CLI report (main()) and the web UI preview (run_oos_backtest()).

    Position sizing is nonlinear (lot rounding, inertia — src/backtest/sizing.py),
    so SR shifts slightly with vol_target, same as Step 5. Use the vol_target
    Step 5 confirmed to keep IS SR comparable across scripts, or try others
    interactively; the confirmed value is also read here for display only.
    """
    vol_target_display: float | None = None
    try:
        vol_target_display = float(st.load_section("step5.yaml", "vol_target", state_dir=state_dir))
    except Exception:
        pass
    if vol_target is None:
        vol_target = _VOL_PLACEHOLDER

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

    return {
        "vol_target": vol_target,
        "vol_target_display": vol_target_display,
        "capital": capital,
        "is_end": is_end,
        "cfgs": cfgs,
        "include_all": include_all,
        "combined_pnl": combined_pnl,
        "rule_pnl": rule_pnl,
        "all_rules": all_rules,
    }


def _split2(pnl: pd.Series, is_end: pd.Timestamp):
    is_p   = pnl[pnl.index < is_end]
    test_p = pnl[pnl.index >= is_end]
    return is_p, test_p


def _row(is_s, test_s):
    return {
        "is":   {"sr": round(_sr(is_s), 3),  "ret": round(_ret(is_s), 4)},
        "test": {"sr": round(_sr(test_s), 3), "ret": round(_ret(test_s), 4)},
    }


def _build_outputs(c: dict) -> dict:
    """Split every pnl series into IS/Test and roll up instrument -> asset
    class -> rule -> family -> portfolio. Pure data, no printing — shared by the
    CLI report (main()) and the web UI preview (run_oos_backtest()).
    """
    is_end = c["is_end"]
    combined_pnl, rule_pnl, all_rules, cfgs = c["combined_pnl"], c["rule_pnl"], c["all_rules"], c["cfgs"]

    inst_is_pnl:   dict[str, pd.Series] = {}
    inst_test_pnl: dict[str, pd.Series] = {}
    instruments_out = {}
    for grp_codes in GROUPS.values():
        for code in grp_codes:
            if code not in combined_pnl:
                continue
            is_p, test_p = _split2(combined_pnl[code], is_end)
            inst_is_pnl[code], inst_test_pnl[code] = is_p, test_p
            row = _row(is_p, test_p)
            row["test_flagged"] = _sr(test_p) < -0.30
            row["traded"] = cfgs[code].traded
            instruments_out[code] = row

    port_is   = pd.DataFrame(inst_is_pnl).fillna(0).sum(axis=1)
    port_test = pd.DataFrame(inst_test_pnl).fillna(0).sum(axis=1)

    asset_classes_out = {}
    for grp_name, grp_codes in GROUPS.items():
        grp_is   = pd.DataFrame({c_: inst_is_pnl[c_]   for c_ in grp_codes if c_ in inst_is_pnl}).fillna(0).sum(axis=1)
        grp_test = pd.DataFrame({c_: inst_test_pnl[c_] for c_ in grp_codes if c_ in inst_test_pnl}).fillna(0).sum(axis=1)
        if grp_is.empty:
            continue
        asset_classes_out[grp_name] = _row(grp_is, grp_test)

    rules_out = {}
    for rule in all_rules:
        r_pnl = rule_pnl.get(rule, {})
        if not r_pnl:
            continue
        r_is   = pd.DataFrame({c_: _split2(s, is_end)[0] for c_, s in r_pnl.items()}).fillna(0).sum(axis=1)
        r_test = pd.DataFrame({c_: _split2(s, is_end)[1] for c_, s in r_pnl.items()}).fillna(0).sum(axis=1)
        rules_out[rule] = _row(r_is, r_test)

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

    families_out = {}
    for fam_name, fam_rules in family_map.items():
        fam_is_parts, fam_test_parts = [], []
        for rule in fam_rules:
            r_pnl = rule_pnl.get(rule, {})
            if not r_pnl:
                continue
            fam_is_parts.append(pd.DataFrame({c_: _split2(s, is_end)[0] for c_, s in r_pnl.items()}).fillna(0).sum(axis=1))
            fam_test_parts.append(pd.DataFrame({c_: _split2(s, is_end)[1] for c_, s in r_pnl.items()}).fillna(0).sum(axis=1))
        if not fam_is_parts:
            continue
        row = _row(
            pd.concat(fam_is_parts,   axis=1).fillna(0).mean(axis=1),
            pd.concat(fam_test_parts, axis=1).fillna(0).mean(axis=1),
        )
        row["n_rules"] = len(fam_rules)
        families_out[fam_name] = row

    test_weak = [code for code, v in instruments_out.items() if v["test_flagged"]]

    portfolio_row = _row(port_is, port_test)
    portfolio_row["is"]["max_dd"]   = round(_mdd(port_is),   4)
    portfolio_row["test"]["max_dd"] = round(_mdd(port_test), 4)

    summary = {
        "is_sr":          portfolio_row["is"]["sr"],
        "test_sr":        portfolio_row["test"]["sr"],
        "is_ret":         portfolio_row["is"]["ret"],
        "test_ret":       portfolio_row["test"]["ret"],
        "is_max_dd":      portfolio_row["is"]["max_dd"],
        "test_max_dd":    portfolio_row["test"]["max_dd"],
        "test_weak_flags": test_weak,
    }

    return {
        "instruments_out": instruments_out,
        "asset_classes_out": asset_classes_out,
        "rules_out": rules_out,
        "families_out": families_out,
        "portfolio_row": portfolio_row,
        "test_weak": test_weak,
        "summary": summary,
        "port_is": port_is,
        "port_test": port_test,
    }


def _print_tables(c: dict, built: dict) -> str:
    """Print Table 1-4 + footer from already-built structured output, tee'd to a
    buffer that becomes step6.md's content. Sourced from `built` (not recomputed)
    so the log and the structured data can never diverge.
    """
    is_end = c["is_end"]
    pr = built["portfolio_row"]

    tee = _Tee(sys.stdout)
    sys.stdout = tee

    if c["include_all"]:
        print("  (--include-all: showing all instruments regardless of 'traded' flag)")
        print(f"  Calibrated weights used for {len(c['combined_pnl'])} instruments; "
              f"config default weight for the rest.\n")

    print("\n" + "=" * 78)
    print(f"  TABLE 1 — Per-instrument SR  (IS –{is_end.year} | Test {is_end.year}–)")
    print("=" * 78)
    hdr = (f"  {'Instrument':<12} {'IS SR':>7} {'Test SR':>8}"
           f"  {'IS Ret':>7} {'Test Ret':>9}")
    print(hdr)
    print("  " + "─" * 54)
    for grp_name, grp_codes in GROUPS.items():
        rows_in_group = [code for code in grp_codes if code in built["instruments_out"]]
        if not rows_in_group:
            continue
        print(f"  {grp_name}")
        for code in rows_in_group:
            row = built["instruments_out"][code]
            traded_flag = "" if row["traded"] else " [excl]"
            flag = " *" if row["test_flagged"] else ""
            print(f"  {'  '+code:<12} {row['is']['sr']:>7.2f} {row['test']['sr']:>8.2f}"
                  f"  {row['is']['ret']:>6.1%} {row['test']['ret']:>9.1%}"
                  f"{flag}{traded_flag}")

    print("  " + "─" * 54)
    print(f"  {'  PORTFOLIO':<12} {pr['is']['sr']:>7.2f} {pr['test']['sr']:>8.2f}"
          f"  {pr['is']['ret']:>6.1%} {pr['test']['ret']:>9.1%}")
    print(f"  {'  Max DD':<12} {'':>7} {'':>8}"
          f"  {pr['is']['max_dd']:>6.1%} {pr['test']['max_dd']:>9.1%}")

    print("\n" + "=" * 78)
    print(f"  TABLE 2 — Asset class SR  (IS –{is_end.year} | Test {is_end.year}–)")
    print("=" * 78)
    hdr2 = (f"  {'Asset class':<14} {'IS SR':>7} {'Test SR':>8}"
            f"  {'IS Ret':>7} {'Test Ret':>9}")
    print(hdr2)
    print("  " + "─" * 54)
    for grp_name, row in built["asset_classes_out"].items():
        print(f"  {grp_name:<14} {row['is']['sr']:>7.2f} {row['test']['sr']:>8.2f}"
              f"  {row['is']['ret']:>6.1%} {row['test']['ret']:>9.1%}")
    print("  " + "─" * 54)
    print(f"  {'PORTFOLIO':<14} {pr['is']['sr']:>7.2f} {pr['test']['sr']:>8.2f}"
          f"  {pr['is']['ret']:>6.1%} {pr['test']['ret']:>9.1%}")

    print("\n" + "=" * 78)
    print("  TABLE 3 — Rule SR  (isolated, full portfolio, IS | Test)")
    print("=" * 78)
    hdr3 = (f"  {'Rule':<16} {'IS SR':>7} {'Test SR':>8}"
            f"  {'IS Ret':>7} {'Test Ret':>9}")
    print(hdr3)
    print("  " + "─" * 54)
    for rule, row in built["rules_out"].items():
        print(f"  {rule:<16} {row['is']['sr']:>7.2f} {row['test']['sr']:>8.2f}"
              f"  {row['is']['ret']:>6.1%} {row['test']['ret']:>9.1%}")
    print("  " + "─" * 54)
    print(f"  {'COMBINED':<16} {pr['is']['sr']:>7.2f} {pr['test']['sr']:>8.2f}"
          f"  {pr['is']['ret']:>6.1%} {pr['test']['ret']:>9.1%}")

    print("\n" + "=" * 78)
    print("  TABLE 4 — Rule family SR  (equal-weight within family, IS | Test)")
    print("=" * 78)
    hdr4 = (f"  {'Family':<16} {'Rules':>5} {'IS SR':>7} {'Test SR':>8}"
            f"  {'IS Ret':>7} {'Test Ret':>9}")
    print(hdr4)
    print("  " + "─" * 59)
    for fam_name, row in built["families_out"].items():
        print(f"  {fam_name:<16} {row['n_rules']:>5} {row['is']['sr']:>7.2f} {row['test']['sr']:>8.2f}"
              f"  {row['is']['ret']:>6.1%} {row['test']['ret']:>9.1%}")
    print("  " + "─" * 59)
    print(f"  {'COMBINED':<16} {'':>5} {pr['is']['sr']:>7.2f} {pr['test']['sr']:>8.2f}"
          f"  {pr['is']['ret']:>6.1%} {pr['test']['ret']:>9.1%}")
    print()

    vol_target, vol_target_display = c["vol_target"], c["vol_target_display"]
    if vol_target_display is None or abs(vol_target_display - vol_target) < 1e-9:
        note = ""
    else:
        note = f"  (Step 5 confirmed: {vol_target_display:.0%})"
    print(f"  Metrics computed at vol target: {vol_target:.0%}{note}   Capital: ${c['capital']:,.0f}")
    print("  Note: rule/family SR uses isolated single-rule positions (no FDM, no rounding, no inertia).")
    print("  Family SR = equal-weight mean across member rules.")
    print("  Combined SR uses full calibrated parameters (FDMs, IDM, instrument weights, rounding, inertia).")
    print("  (* = Test SR < -0.30   [excl] = excluded in active config)")

    sys.stdout = tee._orig
    return tee.getvalue()


def main(state_dir=None, include_all: bool = False, vol_target: float | None = None, report_dir=None) -> dict:
    computed = _compute(vol_target, state_dir=state_dir, include_all=include_all)
    built = _build_outputs(computed)
    md_content = _print_tables(computed, built)

    if report_dir is None:
        report_dir = Path(state_dir).parent / "results" if state_dir else None

    if report_dir is not None:
        md_path = Path(report_dir) / "step6.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(md_path, "w") as f:
            f.write("```\n")
            f.write(md_content)
            f.write("```\n")
        print(f"\n  Results saved → {md_path}")

    return built["summary"]


def run_oos_backtest(vol_target: float, state_dir=None, include_all: bool = False) -> dict:
    """Re-run the OOS validation at `vol_target` and return structured tables plus
    a combined IS->Test equity curve — for the web UI to render tables/big-font
    metrics/equity curve directly instead of parsing the printed log. Does not write
    step6.md (main() owns that); safe to call repeatedly and cheaply (a few seconds).
    """
    computed = _compute(vol_target, state_dir=state_dir, include_all=include_all)
    built = _build_outputs(computed)

    full_pnl = pd.concat([built["port_is"], built["port_test"]]).sort_index()
    equity = equity_curve(full_pnl, computed["capital"])

    return {
        "vol_target": computed["vol_target"],
        "capital": computed["capital"],
        "is_end": computed["is_end"],
        "instruments": built["instruments_out"],
        "asset_classes": built["asset_classes_out"],
        "rules": built["rules_out"],
        "families": built["families_out"],
        "portfolio": built["portfolio_row"],
        "test_weak": built["test_weak"],
        "equity_curve": equity,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OOS validation")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    parser.add_argument("--include-all", action="store_true",
                        help="Include all instruments regardless of 'traded: false'")
    parser.add_argument("--vol-target", type=float, default=None,
                        metavar="FLOAT", help="Position-sizing vol target (default: 0.20 first-look placeholder)")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "config", include_all=args.include_all, vol_target=args.vol_target)

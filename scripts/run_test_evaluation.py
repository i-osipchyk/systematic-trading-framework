"""
Blind test-period evaluation: 2018-2026.

Calibrates all parameters on IS (2011-2018) using the frozen dev weights,
then runs the full IS+OOS backtest.  Uses the same non-interactive approach
as wf_pipeline.py — no user input required.

Usage:
    TRADING_CONFIG=config/test_2018_2026.yaml uv run python scripts/run_test_evaluation.py
    TRADING_CONFIG=config/test_2018_2026.yaml uv run python scripts/run_test_evaluation.py \
        --setup-dir  systems/dev_freeze/wf_run_main/setup \
        --state-dir  systems/test_2018_2026/final
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

import src.backtest.config as config_mod

from src.backtest.config import load_instrument_configs, load_split_date, required_fx_helpers, traded_instruments
from src.backtest.engine import _fx_rate_to_usd, run_portfolio
from src.backtest.metrics import annual_turnover, performance_report, sharpe_ratio
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

VOL_FLOOR = 0.15
FIXED_VOL = 0.20


def _import_step(module_name: str):
    root = Path(__file__).parents[1]
    file_path = root / (module_name.replace(".", "/") + ".py")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _suppress():
    return contextlib.redirect_stdout(io.StringIO())


def _auto_vol_target(
    instruments, family_scalars, rule_weights, fdm_data,
    instrument_weights_raw, is_end, capital,
):
    cfgs = load_instrument_configs()
    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices_map = {code: load_adjusted_prices(code) for code in fx_helper_codes}
    for _fx in ("EURUSD", "EURGBP", "USDJPY"):
        if _fx in instruments and _fx not in fx_prices_map:
            fx_prices_map[_fx] = load_adjusted_prices(_fx)
    eurusd = fx_prices_map.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices_map.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices_map.get("USDJPY", pd.Series(dtype=float))

    all_pnl: dict[str, pd.Series] = {}
    n = len(instruments)
    for code in instruments:
        if code not in cfgs:
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, is_end)
        if len(is_prices) < 20:
            continue
        vol_is = daily_vol(is_prices)
        cfg = cfgs[code]
        fdm = float(fdm_data.get(code, 1.0))
        inst_weight = instrument_weights_raw.get(code, 1.0 / n)
        fc_is = combined_forecast(
            is_prices, vol_is, fdm=fdm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
            instrument_code=code,
        )
        fx = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, is_prices.index, usdjpy_prices=usdjpy)
        pos = compute_positions(
            prices=is_prices, vol=vol_is, forecast=fc_is["combined"],
            pointsize=cfg.pointsize, capital=capital,
            vol_target=FIXED_VOL, idm=1.0, fx_rate_to_usd=fx,
            instrument_weight=inst_weight,
        )
        gpnl = gross_pnl(pos, is_prices, cfg.pointsize)
        costs = transaction_costs(pos, cfg.spread_cost, cfg.pointsize)
        all_pnl[code] = to_usd(gpnl, cfg.currency, eurusd, eurgbp, usdjpy) \
                       - to_usd(costs, cfg.currency, eurusd, eurgbp, usdjpy)

    portfolio_pnl = pd.DataFrame(all_pnl).sum(axis=1)
    is_sr = sharpe_ratio(portfolio_pnl, capital)
    if is_sr <= 0:
        return is_sr, VOL_FLOOR
    realistic_sr = is_sr * 0.75
    vol_target = float(np.clip(np.sqrt(realistic_sr * realistic_sr / 2.0), VOL_FLOOR, 0.40))
    return is_sr, vol_target


def main(setup_dir: Path, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)

    split_date = load_split_date()
    if split_date is None:
        raise RuntimeError("test config must have split_date set")

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    capital = 10_000.0

    print(f"\n  {'='*60}")
    print(f"  Blind test evaluation")
    print(f"  {'='*60}")
    print(f"  IS  : 2011-01-01 → {split_date.date()}")
    print(f"  OOS : {split_date.date()} → (all available data)")
    print(f"  Instruments: {', '.join(instruments)}")
    print(f"  State dir  : {state_dir}")
    print(f"  {'='*60}\n")

    # Copy locked structural weights from dev_freeze setup
    for fname in ["02_family_weights.yaml", "02_forecast_weights.yaml",
                  "06_group_weights.yaml", "06_instrument_weights.yaml"]:
        src = setup_dir / fname
        if src.exists():
            shutil.copy2(src, state_dir / fname)

    weights_data = st.load("02_forecast_weights.yaml", state_dir=state_dir)
    inst_weights_data = st.load("06_instrument_weights.yaml", state_dir=state_dir)
    rule_weights: dict[str, float] = {k: float(v) for k, v in weights_data["forecast_weights"].items()}
    instrument_weights_raw: dict[str, float] = {k: float(v) for k, v in inst_weights_data["instrument_weights"].items()}

    # Step 01: scalars (calibrate on IS only)
    print("  [01] Rule scalars...", end="", flush=True)
    step01 = _import_step("calibrate.01_scale_forecasts")
    with _suppress():
        step01.main(state_dir=state_dir, split_date=split_date)
    scalars_data = st.load("01_scalars.yaml", state_dir=state_dir)
    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    print(" done")

    # Step 03: FDM
    print("  [03] FDM...", end="", flush=True)
    step03 = _import_step("calibrate.03_fdm")
    with _suppress():
        step03.main(state_dir=state_dir, split_date=split_date)
    fdm_data = st.load("03_fdm.yaml", state_dir=state_dir)
    calibrated_fdms = {k: float(v) for k, v in fdm_data.items()}
    print(" done")

    # Vol target: Kelly auto
    print("  [05] Vol target...", end="", flush=True)
    is_sr, vol_target = _auto_vol_target(
        instruments, family_scalars, rule_weights, fdm_data,
        instrument_weights_raw, split_date, capital,
    )
    floor_msg = " [floor]" if is_sr <= 0 else ""
    print(f" IS SR={is_sr:.2f}  vol_target={vol_target:.0%}{floor_msg}")
    st.save("05_vol_target.yaml", {"vol_target": round(vol_target, 4), "is_sharpe": round(is_sr, 4)},
            state_dir=state_dir)

    # Step 07: IDM
    print("  [07] IDM...", end="", flush=True)
    step07 = _import_step("calibrate.07_idm")
    with _suppress():
        step07.main(state_dir=state_dir, split_date=split_date)
    idm_data = st.load("07_idm.yaml", state_dir=state_dir)
    calibrated_idm = float(idm_data["idm"])
    print(f" {calibrated_idm:.3f}")

    # Patch instrument weights
    patched_cfgs = {
        code: replace(cfg, weight=instrument_weights_raw.get(code, cfg.weight))
        for code, cfg in cfgs.items()
    }
    original_load = config_mod.load_instrument_configs
    config_mod.load_instrument_configs = lambda: patched_cfgs

    # Step 08: full IS+OOS backtest
    print("  [08] Backtest...", end="", flush=True)
    try:
        result = run_portfolio(
            instruments=instruments,
            split_date=split_date,
            capital=capital,
            vol_target=vol_target,
            calibrated_fdms=calibrated_fdms,
            calibrated_idm=calibrated_idm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
        )
    finally:
        config_mod.load_instrument_configs = original_load
    print(" done\n")

    # ── Results ──────────────────────────────────────────────────────────────
    bar = "=" * 64
    print(f"\n  {bar}")
    print(f"  Blind test results")
    print(f"  {bar}")
    print(f"  Split date  : {result.split_date.date()}")
    print(f"  Vol target  : {vol_target:.0%}   IDM: {calibrated_idm:.3f}")
    print()
    print(f"  {'Period':<6} {'gSharpe':>8} {'Sharpe':>8} {'Ann Ret':>9} {'Max DD':>9} {'Bars':>6}")
    print(f"  {'─'*48}")
    for label, pnl, gpnl in [
        ("IS",  result.is_pnl,
         pd.concat([r.gross_pnl_usd for r in result.instrument_results.values()], axis=1).sum(axis=1)
         .loc[lambda s: s.index < split_date]),
        ("OOS", result.oos_pnl,
         pd.concat([r.gross_pnl_usd for r in result.instrument_results.values()], axis=1).sum(axis=1)
         .loc[lambda s: s.index >= split_date]),
    ]:
        m   = performance_report(pnl,  capital)
        mg  = performance_report(gpnl, capital)
        n   = len(pnl.dropna())
        print(f"  {label:<6} {mg['sharpe']:>8.2f} {m['sharpe']:>8.2f}"
              f" {m['ann_return']:>8.1%} {m['max_drawdown']:>8.1%} {n:>6}")

    print()
    print(f"  Per-instrument OOS breakdown:")
    hdr = f"  {'Code':<10} {'gSR IS':>7} {'SR IS':>7} {'gSR OOS':>8} {'SR OOS':>7} {'Ret IS':>8} {'Ret OOS':>9}"
    print(hdr)
    print(f"  {'─'*len(hdr.rstrip())}")
    for code, ir in result.instrument_results.items():
        is_g  = performance_report(ir.gross_pnl_usd[ir.gross_pnl_usd.index < split_date],  capital)
        oos_g = performance_report(ir.gross_pnl_usd[ir.gross_pnl_usd.index >= split_date], capital)
        is_n  = performance_report(ir.net_pnl_usd[ir.net_pnl_usd.index < split_date],      capital)
        oos_n = performance_report(ir.net_pnl_usd[ir.net_pnl_usd.index >= split_date],     capital)
        print(f"  {code:<10} {is_g['sharpe']:>7.2f} {is_n['sharpe']:>7.2f}"
              f" {oos_g['sharpe']:>8.2f} {oos_n['sharpe']:>7.2f}"
              f" {is_n['ann_return']:>7.1%} {oos_n['ann_return']:>8.1%}")

    print(f"\n  (gSR = pre-cost Sharpe, SR = post-cost Sharpe)")
    print(f"  State dir: {state_dir}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-dir",  default="systems/dev_freeze/wf_run_main/setup",
                        help="Directory with pre-set 02/06 weight files")
    parser.add_argument("--state-dir",  default="systems/test_2018_2026/final",
                        help="Output directory for calibrated state files")
    args = parser.parse_args()
    main(Path(args.setup_dir), Path(args.state_dir))

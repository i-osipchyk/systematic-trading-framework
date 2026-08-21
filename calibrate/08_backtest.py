"""
Step 08: Full IS+OOS backtest with all calibrated parameters.

Loads all state files, patches module-level SCALARS, applies calibrated
instrument weights, then runs the two-pass portfolio backtest skipping
pass 1 (FDMs and IDM already known).

Usage:
    uv run python calibrate/08_backtest.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import src.rules.ewmac as ewmac_mod
import src.rules.mr as mr_mod

from src.calibration import state as st
from src.backtest.config import load_instrument_configs, traded_instruments
from src.backtest.engine import INSTRUMENTS, run_portfolio
from src.backtest.metrics import annual_turnover, performance_report


def main(state_dir=None) -> None:
    # Load all state
    scalars_data = st.load("01_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("02_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("03_fdm.yaml", state_dir=state_dir)
    vol_target_data = st.load("05_vol_target.yaml", state_dir=state_dir)
    inst_weights_data = st.load("06_instrument_weights.yaml", state_dir=state_dir)
    idm_data = st.load("07_idm.yaml", state_dir=state_dir)

    ewmac_scalars = st.parse_ewmac_scalars(scalars_data.get("ewmac", {}))
    mr_scalars = st.parse_mr_scalars(scalars_data.get("mr", {}))
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }
    calibrated_fdms: dict[str, float] = {
        k: float(v) for k, v in fdm_data.items()
    }
    vol_target = float(vol_target_data["vol_target"])
    instrument_weights_raw: dict[str, float] = {
        k: float(v) for k, v in inst_weights_data["instrument_weights"].items()
    }
    calibrated_idm = float(idm_data["idm"])

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)

    # Patch module-level SCALARS so any code using the defaults gets calibrated values
    ewmac_mod.SCALARS = ewmac_scalars  # type: ignore[assignment]
    mr_mod.SCALARS = mr_scalars        # type: ignore[assignment]

    # Apply calibrated instrument weights to configs
    patched_cfgs: dict = {}
    for code, cfg in cfgs.items():
        w = instrument_weights_raw.get(code, cfg.weight)
        patched_cfgs[code] = replace(cfg, weight=w)

    # Monkey-patch load_instrument_configs to return our patched configs
    import src.backtest.engine as engine_mod
    import src.backtest.config as config_mod
    original_load = config_mod.load_instrument_configs
    config_mod.load_instrument_configs = lambda: patched_cfgs  # type: ignore[assignment]

    print(f"{'─'*60}")
    print(f"  Calibrated backtest")
    print(f"{'─'*60}")
    print(f"  Vol target  : {vol_target:.0%}")
    print(f"  IDM         : {calibrated_idm:.3f}")
    print()

    try:
        result = run_portfolio(
            instruments=instruments,
            capital=10_000.0,
            vol_target=vol_target,
            calibrated_fdms=calibrated_fdms,
            calibrated_idm=calibrated_idm,
            ewmac_scalars=ewmac_scalars,
            mr_scalars=mr_scalars,
            rule_weights=rule_weights,
        )
    finally:
        # Restore original function
        config_mod.load_instrument_configs = original_load

    # ── Header ────────────────────────────────────────────────────────────────
    print(f"{'─'*60}")
    print(f"  Backtest summary")
    print(f"{'─'*60}")
    print(f"  Split date  : {result.split_date.date()}")
    print(f"  Capital     : ${result.capital:>12,.0f}")
    print(f"  Vol target  : {vol_target:.0%}")
    print(f"  IDM         : {result.idm:.3f}")
    print()

    # ── Per-instrument calibration ────────────────────────────────────────────
    print(f"  {'Instrument':<10} {'FDM':>6} {'Weight':>8}")
    print(f"  {'─'*26}")
    for code in instruments:
        if code in result.fdms:
            w = instrument_weights_raw.get(code, 0.0)
            print(f"  {code:<10} {result.fdms[code]:>6.3f} {w:>8.1%}")

    # ── Portfolio performance ─────────────────────────────────────────────────
    print()
    print(f"  Portfolio performance:")
    print(f"  {'Period':<6} {'Sharpe':>8} {'Ann Ret':>9} {'Max DD':>9} {'Bars':>6}")
    print(f"  {'─'*44}")
    for label, pnl in [("IS", result.is_pnl), ("OOS", result.oos_pnl)]:
        m = performance_report(pnl, result.capital, label=label)
        n = len(pnl.dropna())
        print(f"  {label:<6} {m['sharpe']:>8.2f} {m['ann_return']:>8.1%}"
              f" {m['max_drawdown']:>8.1%} {n:>6}")

    # ── Per-instrument breakdown ──────────────────────────────────────────────
    print()
    print(f"  Per-instrument breakdown (IS → OOS):")
    hdr = (f"  {'Code':<10} {'gSR IS':>7} {'SR IS':>7} {'gSR OOS':>8} {'SR OOS':>7} "
           f"{'Ret IS':>8} {'Ret OOS':>9} {'Turnover':>9}")
    print(hdr)
    print(f"  {'─'*len(hdr.rstrip())}")

    split = result.split_date
    for code, ir in result.instrument_results.items():
        is_gross  = ir.gross_pnl_usd[ir.gross_pnl_usd.index < split]
        oos_gross = ir.gross_pnl_usd[ir.gross_pnl_usd.index >= split]
        is_pnl    = ir.net_pnl_usd[ir.net_pnl_usd.index < split]
        oos_pnl   = ir.net_pnl_usd[ir.net_pnl_usd.index >= split]
        is_pos    = ir.positions[ir.positions.index < split]

        is_gm  = performance_report(is_gross,  result.capital)
        oos_gm = performance_report(oos_gross, result.capital)
        is_m   = performance_report(is_pnl,    result.capital)
        oos_m  = performance_report(oos_pnl,   result.capital)
        tv     = annual_turnover(is_pos)

        print(f"  {code:<10} {is_gm['sharpe']:>7.2f} {is_m['sharpe']:>7.2f}"
              f" {oos_gm['sharpe']:>8.2f} {oos_m['sharpe']:>7.2f}"
              f" {is_m['ann_return']:>7.1%} {oos_m['ann_return']:>8.1%}"
              f" {tv:>9.1f}")

    print(f"\n  gSR = pre-cost Sharpe  SR = post-cost Sharpe")
    print(f"  (Turnover = roundtrips/year on IS, normalised by mean position size)")


if __name__ == "__main__":
    main()

"""
Step 5b: Full IS+OOS backtest with all calibrated parameters.

Loads all state files, applies calibrated instrument weights, then runs the
two-pass portfolio backtest skipping pass 1 (FDMs and IDM already known).

Usage:
    uv run python calibrate/step5b_backtest.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.calibration import state as st
from src.backtest.config import load_capital, load_instrument_configs, traded_instruments
from src.backtest.engine import INSTRUMENTS, run_portfolio
from src.backtest.metrics import annual_turnover, performance_report
from src.rules.registry import REGISTRY


def main(state_dir=None) -> None:
    scalars_data = st.load("step3a_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("step3d_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("step3d_fdm.yaml", state_dir=state_dir)
    vol_target_data = st.load("step5_vol_target.yaml", state_dir=state_dir)
    inst_weights_data = st.load("step4a_instrument_weights.yaml", state_dir=state_dir)
    idm_data = st.load("step4b_idm.yaml", state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
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

    # Apply calibrated instrument weights to configs
    patched_cfgs: dict = {}
    for code, cfg in cfgs.items():
        w = instrument_weights_raw.get(code, cfg.weight)
        patched_cfgs[code] = replace(cfg, weight=w)

    # Monkey-patch load_instrument_configs to return our patched configs
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
            capital=load_capital(),
            vol_target=vol_target,
            calibrated_fdms=calibrated_fdms,
            calibrated_idm=calibrated_idm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
        )
    finally:
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

    # ── IS performance only ───────────────────────────────────────────────────
    # OOS data (val / test) is NOT examined at this step. All five parameters
    # are locked first; OOS validation runs exactly once afterward as a
    # separate one-shot step (calibrate/oos_validation.py).
    split = result.split_date
    is_pnl = result.is_pnl

    print()
    print(f"  IS portfolio performance:")
    print(f"  {'Period':<12} {'Sharpe':>8} {'Ann Ret':>9} {'Max DD':>9} {'Bars':>6}")
    print(f"  {'─'*50}")
    m = performance_report(is_pnl, result.capital, label="IS")
    n = len(is_pnl.dropna())
    print(f"  {'IS 84–10':<12} {m['sharpe']:>8.2f} {m['ann_return']:>8.1%}"
          f" {m['max_drawdown']:>8.1%} {n:>6}")

    # ── Per-instrument IS breakdown ───────────────────────────────────────────
    print()
    print(f"  Per-instrument IS breakdown:")
    hdr = (f"  {'Code':<10} {'SR IS':>7} {'Ret IS':>8} {'Max DD':>8} {'TV':>6}")
    print(hdr)
    print(f"  {'─'*len(hdr.rstrip())}")

    for code, ir in result.instrument_results.items():
        is_net = ir.net_pnl_usd[ir.net_pnl_usd.index < split]
        is_pos = ir.positions[ir.positions.index < split]

        is_m = performance_report(is_net, result.capital)
        tv   = annual_turnover(is_pos)

        print(f"  {code:<10} {is_m['sharpe']:>7.2f}"
              f" {is_m['ann_return']:>7.1%} {is_m['max_drawdown']:>7.1%} {tv:>6.1f}")

    print(f"\n  SR = post-cost Sharpe  TV = IS roundtrips/year")
    print(f"  OOS not shown — locked after Step 5; run oos_validation.py separately.")


if __name__ == "__main__":
    main()

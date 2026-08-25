"""
Step 5: IS backtest, Kelly analysis, and vol target confirmation.

Runs the full IS-only portfolio backtest with all calibrated parameters, prints
per-instrument and portfolio-level IS results, then computes Kelly / half-Kelly
/ geometric-mean vol target suggestions and asks the user to confirm one.

INPUT STATE FILES:
  - step3a_scalars.yaml            (from step 3)
  - step3d_forecast_weights.yaml   (from step 3)
  - step3d_fdm.yaml                (from step 3)
  - step4a_instrument_weights.yaml (from step 4)
  - step4b_idm.yaml                (from step 4)

OUTPUT STATE FILES:
  - step5_vol_target.yaml
      vol_target: float

Usage:
    uv run python calibrate/step5_calibrate.py
    uv run python calibrate/step5_calibrate.py --system systems/universe_v4
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import (
    load_capital, load_instrument_configs, load_rules_config, required_fx_helpers,
    set_config, traded_instruments,
)
from src.backtest.engine import run_portfolio
from src.backtest.metrics import annual_turnover, performance_report
from src.calibration import state as st
from src.rules.registry import REGISTRY

FILENAME = "step5_vol_target.yaml"
_VOL_PLACEHOLDER = 0.20   # SR is scale-invariant; placeholder for IS run


def main(state_dir=None) -> dict:
    scalars_data   = st.load("step3a_scalars.yaml",           state_dir=state_dir)
    weights_data   = st.load("step3d_forecast_weights.yaml",  state_dir=state_dir)
    fdm_data       = st.load("step3d_fdm.yaml",               state_dir=state_dir)
    inst_w_data    = st.load("step4a_instrument_weights.yaml", state_dir=state_dir)
    idm_data       = st.load("step4b_idm.yaml",               state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }
    calibrated_fdms: dict[str, float] = {k: float(v) for k, v in fdm_data.items()}
    instrument_weights: dict[str, float] = {
        k: float(v) for k, v in inst_w_data["instrument_weights"].items()
    }
    idm = float(idm_data["idm"])
    capital = load_capital()

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)

    # Patch instrument weights into configs
    patched_cfgs = {code: replace(cfg, weight=instrument_weights.get(code, cfg.weight))
                   for code, cfg in cfgs.items()}
    import src.backtest.config as _cfg_mod
    _orig = _cfg_mod.load_instrument_configs
    _cfg_mod.load_instrument_configs = lambda: patched_cfgs  # type: ignore[assignment]

    print(f"  Running IS portfolio (vol={_VOL_PLACEHOLDER:.0%} placeholder, IDM={idm:.3f})...")
    try:
        result = run_portfolio(
            instruments=instruments,
            capital=capital,
            vol_target=_VOL_PLACEHOLDER,
            calibrated_fdms=calibrated_fdms,
            calibrated_idm=idm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
        )
    finally:
        _cfg_mod.load_instrument_configs = _orig

    split = result.split_date
    is_pnl = result.is_pnl

    SEP = "─" * 70

    # ── Portfolio IS results ──────────────────────────────────────────────────
    port_m = performance_report(is_pnl, capital)
    is_sharpe = port_m["sharpe"]

    print(f"\n  {SEP}")
    print(f"  IS PORTFOLIO  ({split.year} end)  vol placeholder {_VOL_PLACEHOLDER:.0%}")
    print(f"  {SEP}")
    print(f"  {'Sharpe':>10}  {'Ann Return':>11}  {'Max DD':>9}  {'Bars':>6}")
    print(f"  {'─' * 44}")
    n_bars = len(is_pnl.dropna())
    print(f"  {port_m['sharpe']:>10.2f}  {port_m['ann_return']:>10.1%}"
          f"  {port_m['max_drawdown']:>8.1%}  {n_bars:>6}")

    # ── Per-instrument IS breakdown ───────────────────────────────────────────
    print(f"\n  {SEP}")
    print("  PER-INSTRUMENT IS BREAKDOWN")
    print(f"  {SEP}")
    inst_rows: list[tuple] = []
    for code, ir in result.instrument_results.items():
        is_net = ir.net_pnl_usd[ir.net_pnl_usd.index < split]
        is_pos = ir.positions[ir.positions.index < split]
        m   = performance_report(is_net, capital)
        tv  = annual_turnover(is_pos)
        w   = instrument_weights.get(code, 0.0)
        fdm = calibrated_fdms.get(code, 1.0)
        inst_rows.append((code, m["sharpe"], m["ann_return"], m["max_drawdown"], tv, w, fdm))

    cw = max(len(r[0]) for r in inst_rows) if inst_rows else 10
    print(f"  {'Code':<{cw}}  {'SR':>6}  {'Ret':>7}  {'MaxDD':>7}  {'TV':>5}  {'Wt':>6}  {'FDM':>5}")
    print(f"  {'─' * (cw + 46)}")
    for code, sr, ret, dd, tv, w, fdm in inst_rows:
        print(f"  {code:<{cw}}  {sr:>6.2f}  {ret:>6.1%}  {dd:>6.1%}  {tv:>5.1f}  {w:>5.1%}  {fdm:>5.3f}")

    # ── Kelly analysis ────────────────────────────────────────────────────────
    realistic_sr = is_sharpe * 0.75
    full_kelly   = realistic_sr
    half_kelly   = realistic_sr / 2.0
    geo_mean     = float(np.sqrt(max(full_kelly * half_kelly, 0.0)))
    suggested    = float(np.clip(geo_mean, 0.05, 0.40))

    print(f"\n  {SEP}")
    print("  KELLY ANALYSIS  (realistic SR = IS SR × 0.75)")
    print(f"  {SEP}")
    print(f"  IS Sharpe (after costs)      : {is_sharpe:>6.2f}")
    print(f"  Realistic future SR          : {realistic_sr:>6.2f}")
    print(f"  {'─' * 42}")
    print(f"  Full Kelly vol target        : {full_kelly:>6.1%}")
    print(f"  Half Kelly vol target        : {half_kelly:>6.1%}")
    print(f"  Geometric mean               : {geo_mean:>6.1%}  (√full×half)")
    print(f"  Suggested (capped at 40%)    : {suggested:>6.1%}")
    print(f"  {'─' * 42}")
    print(f"  Trend-following returns are positively skewed")
    print(f"  → lean toward Full Kelly rather than Half")

    # ── Write vol target template ─────────────────────────────────────────────
    if not st.exists(FILENAME, state_dir=state_dir):
        content = (
            "# Volatility target — Step 5\n"
            "# ─────────────────────────────────────────────────────────────────\n"
            "# Edit vol_target below and press Enter in the terminal.\n"
            "#\n"
            f"# IS Sharpe (after costs) : {is_sharpe:.2f}\n"
            f"# Realistic SR (×0.75)    : {realistic_sr:.2f}\n"
            f"#\n"
            f"# Full Kelly              : {full_kelly:.2%}\n"
            f"# Half Kelly              : {half_kelly:.2%}\n"
            f"# Geometric mean          : {geo_mean:.2%}  (√full×half)\n"
            f"# Suggested (cap 40%)     : {suggested:.2%}  ← pre-filled\n"
            "#\n"
            "# Range: 0.02 – 0.50\n"
            "#\n"
            f"vol_target: {suggested:.2f}\n"
        )
        path = st.path(FILENAME, state_dir=state_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"\n  Wrote template → {path}")

    print(f"\n  Edit {st.path(FILENAME, state_dir=state_dir)}")
    print(f"  then press Enter to confirm...")

    vol_target: float | None = None
    while True:
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            print("\n  Aborted.")
            sys.exit(1)
        if not st.exists(FILENAME, state_dir=state_dir):
            print("  ERROR: file not found.")
            continue
        data = yaml.safe_load(st.path(FILENAME, state_dir=state_dir).read_text())
        vt = data.get("vol_target")
        if not isinstance(vt, (int, float)):
            print("  ERROR: vol_target must be a number.")
            continue
        if not (0.02 <= vt <= 0.50):
            print(f"  ERROR: {vt} out of range [0.02, 0.50].")
            continue
        vol_target = float(vt)
        break

    print(f"  Vol target confirmed: {vol_target:.0%}")

    # ── Markdown report ───────────────────────────────────────────────────────
    lines: list[str] = ["# Step 5 IS Backtest & Vol Target Report", ""]

    lines += ["## IS Portfolio", "",
              f"| Metric | Value |", f"|--------|-------|",
              f"| Sharpe (after costs) | {port_m['sharpe']:.2f} |",
              f"| Ann Return | {port_m['ann_return']:.1%} |",
              f"| Max Drawdown | {port_m['max_drawdown']:.1%} |",
              f"| IS bars | {n_bars} |", ""]

    lines += ["## Per-Instrument IS Breakdown", "",
              f"| Code | SR | Ret | Max DD | TV | Weight | FDM |",
              f"|------|----|-----|--------|----|--------|-----|"]
    for code, sr, ret, dd, tv, w, fdm in inst_rows:
        lines.append(f"| {code} | {sr:.2f} | {ret:.1%} | {dd:.1%} | {tv:.1f} | {w:.1%} | {fdm:.3f} |")
    lines.append("")

    lines += ["## Kelly Analysis", "",
              f"| | Value |", f"|--|-------|",
              f"| IS Sharpe | {is_sharpe:.2f} |",
              f"| Realistic SR (×0.75) | {realistic_sr:.2f} |",
              f"| Full Kelly | {full_kelly:.2%} |",
              f"| Half Kelly | {half_kelly:.2%} |",
              f"| Geometric mean (√full×half) | {geo_mean:.2%} |",
              f"| Suggested (capped at 40%) | {suggested:.2%} |",
              f"| **Confirmed vol target** | **{vol_target:.2%}** |", ""]

    report_path = st.path("step5_report.md", state_dir=state_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))
    print(f"  Saved: {st.path(FILENAME, state_dir=state_dir)}")
    print(f"  Saved: {report_path}")

    return {
        "is_sharpe":       round(is_sharpe, 4),
        "realistic_sr":    round(realistic_sr, 4),
        "full_kelly":      round(full_kelly, 4),
        "half_kelly":      round(half_kelly, 4),
        "geo_mean":        round(geo_mean, 4),
        "vol_target":      vol_target,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 5: IS backtest & vol target")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    args = parser.parse_args()
    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "results")

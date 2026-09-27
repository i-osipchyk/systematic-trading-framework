"""
Step 5: IS backtest, Kelly analysis, and vol target confirmation.

Runs the full IS-only portfolio backtest with all calibrated parameters, prints
per-instrument and portfolio-level IS results, then computes Kelly / half-Kelly
/ geometric-mean vol target suggestions and asks the user to confirm one.

Position sizing is linear in vol_target *before* lot rounding and inertia
buffering (src/backtest/sizing.py), both of which are nonlinear — so Sharpe
is only approximately scale-invariant across vol targets, not exactly. The
web UI (src/webui/config_editor.py) uses run_is_backtest() below to actually
re-run the portfolio at whatever vol_target the user is trying, rather than
rescale a single placeholder run, so the previewed equity curve/SR/Kelly
numbers are the real ones for that target.

INPUT STATE FILES:
  - step3.yaml  (sections: scalars, forecast_weights, fdm)
  - step4.yaml  (sections: instrument_weights, idm)

OUTPUT STATE FILES:
  - step5.yaml
      vol_target: float

Usage:
    uv run python calibrate/step5_calibrate.py
    uv run python calibrate/step5_calibrate.py --system systems/universe_v4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import (
    load_capital, load_instrument_configs, set_config, traded_instruments,
)
from src.backtest.engine import run_portfolio
from src.backtest.metrics import annual_turnover, equity_curve, performance_report
from src.calibration import state as st
from src.rules.registry import REGISTRY

FILENAME = "step5.yaml"
_VOL_PLACEHOLDER = 0.20   # first-look default before the user has tried anything


def _load_calibrated_inputs(state_dir) -> dict:
    scalars_data     = st.load_section("step3.yaml", "scalars",           state_dir=state_dir)
    forecast_weights = st.load_section("step3.yaml", "forecast_weights",   state_dir=state_dir)
    calibrated_fdms  = {k: float(v) for k, v in
                        st.load_section("step3.yaml", "fdm", state_dir=state_dir).items()}
    instrument_weights = {k: float(v) for k, v in
                          st.load_section("step4.yaml", "instrument_weights", state_dir=state_dir).items()}
    idm = float(st.load_section("step4.yaml", "idm", state_dir=state_dir))
    return {
        "family_scalars": st.parse_family_scalars(scalars_data, REGISTRY),
        "rule_weights": {k: float(v) for k, v in forecast_weights.items()},
        "calibrated_fdms": calibrated_fdms,
        "instrument_weights": instrument_weights,
        "idm": idm,
    }


def run_is_backtest(vol_target: float, state_dir=None) -> dict:
    """Run the full IS portfolio backtest at a specific vol_target.

    Cheap enough (a few seconds for a handful of instruments over decades of
    daily bars) to call repeatedly, e.g. once per vol target the user tries
    in the web UI. Returns portfolio + per-instrument metrics, the IS equity
    curve, and Kelly sizing recommendations derived from the *measured*
    Sharpe at this vol_target.
    """
    inputs = _load_calibrated_inputs(state_dir)
    capital = load_capital()
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)

    result = run_portfolio(
        instruments=instruments,
        capital=capital,
        vol_target=vol_target,
        calibrated_fdms=inputs["calibrated_fdms"],
        calibrated_idm=inputs["idm"],
        family_scalars=inputs["family_scalars"],
        rule_weights=inputs["rule_weights"],
        instrument_weights=inputs["instrument_weights"],
    )

    split = result.split_date
    is_pnl = result.is_pnl
    port_m = performance_report(is_pnl, capital)
    is_sharpe = port_m["sharpe"]

    inst_rows: list[dict] = []
    for code, ir in result.instrument_results.items():
        is_net = ir.net_pnl_usd[ir.net_pnl_usd.index < split]
        is_pos = ir.positions[ir.positions.index < split]
        m = performance_report(is_net, capital)
        inst_rows.append({
            "code": code,
            "sharpe": m["sharpe"],
            "ann_return": m["ann_return"],
            "max_drawdown": m["max_drawdown"],
            "turnover": annual_turnover(is_pos),
            "weight": inputs["instrument_weights"].get(code, 0.0),
            "fdm": inputs["calibrated_fdms"].get(code, 1.0),
        })

    realistic_sr = is_sharpe * 0.75
    full_kelly   = realistic_sr
    half_kelly   = realistic_sr / 2.0
    geo_mean     = float(np.sqrt(max(full_kelly * half_kelly, 0.0)))
    suggested    = float(np.clip(geo_mean, 0.05, 0.40))

    return {
        "vol_target":   vol_target,
        "is_sharpe":    round(is_sharpe, 4),
        "ann_return":   round(port_m["ann_return"], 4),
        "max_drawdown": round(port_m["max_drawdown"], 4),
        "n_bars":       len(is_pnl.dropna()),
        "realistic_sr": round(realistic_sr, 4),
        "full_kelly":   round(full_kelly, 4),
        "half_kelly":   round(half_kelly, 4),
        "geo_mean":     round(geo_mean, 4),
        "suggested":    round(suggested, 4),
        "equity_curve": equity_curve(is_pnl, capital),
        "instruments":  inst_rows,
        "split_date":   split,
        "capital":      capital,
    }


def _print_report(preview: dict) -> None:
    SEP = "─" * 70
    vt = preview["vol_target"]

    print(f"\n  {SEP}")
    print(f"  IS PORTFOLIO  vol {vt:.0%}")
    print(f"  {SEP}")
    print(f"  {'Sharpe':>10}  {'Ann Return':>11}  {'Max DD':>9}  {'Bars':>6}")
    print(f"  {'─' * 44}")
    print(f"  {preview['is_sharpe']:>10.2f}  {preview['ann_return']:>10.1%}"
          f"  {preview['max_drawdown']:>8.1%}  {preview['n_bars']:>6}")

    print(f"\n  {SEP}")
    print("  PER-INSTRUMENT IS BREAKDOWN")
    print(f"  {SEP}")
    inst_rows = preview["instruments"]
    cw = max(len(r["code"]) for r in inst_rows) if inst_rows else 10
    print(f"  {'Code':<{cw}}  {'SR':>6}  {'Ret':>7}  {'MaxDD':>7}  {'TV':>5}  {'Wt':>6}  {'FDM':>5}")
    print(f"  {'─' * (cw + 46)}")
    for r in inst_rows:
        print(f"  {r['code']:<{cw}}  {r['sharpe']:>6.2f}  {r['ann_return']:>6.1%}  "
              f"{r['max_drawdown']:>6.1%}  {r['turnover']:>5.1f}  {r['weight']:>5.1%}  {r['fdm']:>5.3f}")

    print(f"\n  {SEP}")
    print("  KELLY ANALYSIS  (realistic SR = IS SR × 0.75)")
    print(f"  {SEP}")
    print(f"  IS Sharpe (after costs)      : {preview['is_sharpe']:>6.2f}")
    print(f"  Realistic future SR          : {preview['realistic_sr']:>6.2f}")
    print(f"  {'─' * 42}")
    print(f"  Full Kelly vol target        : {preview['full_kelly']:>6.1%}")
    print(f"  Half Kelly vol target        : {preview['half_kelly']:>6.1%}")
    print(f"  Geometric mean               : {preview['geo_mean']:>6.1%}  (√full×half)")
    print(f"  Suggested (capped at 40%)    : {preview['suggested']:>6.1%}")
    print(f"  {'─' * 42}")
    print(f"  Trend-following returns are positively skewed")
    print(f"  → lean toward Full Kelly rather than Half")


def _write_report(report_path: Path, final: dict) -> None:
    lines: list[str] = ["# Step 5 IS Backtest & Vol Target Report", ""]

    lines += ["## IS Portfolio", "",
              f"| Metric | Value |", f"|--------|-------|",
              f"| Vol target | {final['vol_target']:.1%} |",
              f"| Sharpe (after costs) | {final['is_sharpe']:.2f} |",
              f"| Ann Return | {final['ann_return']:.1%} |",
              f"| Max Drawdown | {final['max_drawdown']:.1%} |",
              f"| IS bars | {final['n_bars']} |", ""]

    lines += ["## Per-Instrument IS Breakdown", "",
              f"| Code | SR | Ret | Max DD | TV | Weight | FDM |",
              f"|------|----|-----|--------|----|--------|-----|"]
    for r in final["instruments"]:
        lines.append(f"| {r['code']} | {r['sharpe']:.2f} | {r['ann_return']:.1%} | "
                     f"{r['max_drawdown']:.1%} | {r['turnover']:.1f} | {r['weight']:.1%} | {r['fdm']:.3f} |")
    lines.append("")

    lines += ["## Kelly Analysis", "",
              f"| | Value |", f"|--|-------|",
              f"| IS Sharpe | {final['is_sharpe']:.2f} |",
              f"| Realistic SR (×0.75) | {final['realistic_sr']:.2f} |",
              f"| Full Kelly | {final['full_kelly']:.2%} |",
              f"| Half Kelly | {final['half_kelly']:.2%} |",
              f"| Geometric mean (√full×half) | {final['geo_mean']:.2%} |",
              f"| Suggested (capped at 40%) | {final['suggested']:.2%} |",
              f"| **Confirmed vol target** | **{final['vol_target']:.2%}** |", ""]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


def main(state_dir=None, report_dir=None, auto_confirm: bool = False) -> dict:
    if report_dir is None:
        report_dir = state_dir

    # First look at a default vol target, purely to seed the vol_target
    # template and give the user Kelly numbers to react to.
    preview = run_is_backtest(_VOL_PLACEHOLDER, state_dir=state_dir)
    print(f"  Running IS portfolio (vol={_VOL_PLACEHOLDER:.0%} first look)...")
    _print_report(preview)

    if not st.has_section(FILENAME, "vol_target", state_dir=state_dir):
        st.save_section(FILENAME, "vol_target", round(preview["suggested"], 2), state_dir=state_dir)
        print(f"\n  Wrote vol_target section → {st.path(FILENAME, state_dir=state_dir)}")

    step5_path = st.path(FILENAME, state_dir=state_dir)
    print(f"\n  Edit vol_target in: {step5_path}")

    def _read_vol_target() -> float:
        data = yaml.safe_load(step5_path.read_text()) or {}
        vt = data.get("vol_target")
        if not isinstance(vt, (int, float)):
            raise ValueError(f"vol_target must be a number, got {vt!r} in {step5_path}")
        if not (0.02 <= vt <= 0.50):
            raise ValueError(f"vol_target {vt} out of range [0.02, 0.50] in {step5_path}")
        return float(vt)

    vol_target: float
    if auto_confirm:
        print(f"  auto_confirm=True — validating the vol_target currently on disk.")
        vol_target = _read_vol_target()
    else:
        print(f"  then press Enter to confirm...")
        while True:
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                print("\n  Aborted.")
                sys.exit(1)
            try:
                vol_target = _read_vol_target()
            except ValueError as exc:
                print(f"  ERROR: {exc}")
                continue
            break

    print(f"  Vol target confirmed: {vol_target:.0%}")

    # Re-run at the confirmed target — lot rounding/inertia mean the actual
    # SR/drawdown/equity curve at this vol can differ slightly from the
    # first-look preview above.
    final = preview if vol_target == _VOL_PLACEHOLDER else run_is_backtest(vol_target, state_dir=state_dir)

    report_path = st.path("step5_report.md", state_dir=report_dir)
    _write_report(report_path, final)

    equity_path = st.path("step5_equity_curve.csv", state_dir=report_dir)
    final["equity_curve"].rename("equity").to_csv(equity_path, header=True, index_label="date")

    print(f"  Saved: {step5_path}")
    print(f"  Saved: {report_path}")
    print(f"  Saved: {equity_path}")

    return {
        "is_sharpe":       final["is_sharpe"],
        "realistic_sr":    final["realistic_sr"],
        "full_kelly":      final["full_kelly"],
        "half_kelly":      final["half_kelly"],
        "geo_mean":        final["geo_mean"],
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
    main(state_dir=system_dir / "config", report_dir=system_dir / "results")

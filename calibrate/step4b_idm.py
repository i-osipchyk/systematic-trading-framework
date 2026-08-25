"""
Step 4b: Compute IDM from IS instrument return correlations.

Runs IS-only portfolio with calibrated parameters (IDM=1.0), builds the
return correlation matrix, then derives IDM = 1/sqrt(w'Cw).

INPUT STATE FILES:
  - step3a_scalars.yaml         (from step 3a)
  - step3d_forecast_weights.yaml (from step 3d)
  - step3d_fdm.yaml              (from step 3d)
  - step4a_instrument_weights.yaml (from step 4a)

OUTPUT STATE FILES:
  - step4b_idm.yaml
      idm: float

Usage:
    uv run python calibrate/step4b_idm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.calibration import state as st
from src.backtest.config import load_bars_per_year, load_capital, load_instrument_configs, traded_instruments, required_fx_helpers
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.idm import compute_idm

_VOL_PLACEHOLDER = 0.20  # fixed vol target used only for position sizing; IDM is scale-invariant
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol


def main(state_dir=None, split_date=None) -> None:
    scalars_data = st.load("step3a_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("step3d_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("step3d_fdm.yaml", state_dir=state_dir)
    inst_weights_data = st.load("step4a_instrument_weights.yaml", state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }
    instrument_weights_raw: dict[str, float] = {
        k: float(v) for k, v in inst_weights_data["instrument_weights"].items()
    }

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    if split_date is None:
        split_date = compute_split_date(instruments)
    capital = 10_000.0

    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices_map = {code: load_adjusted_prices(code) for code in fx_helper_codes}
    # Some FX instruments are traded (not in fx_helpers) but still needed for conversion
    for _fx in ("EURUSD", "EURGBP", "USDJPY", "USDCAD"):
        if _fx in instruments and _fx not in fx_prices_map:
            fx_prices_map[_fx] = load_adjusted_prices(_fx)
    eurusd = fx_prices_map.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices_map.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices_map.get("USDJPY", pd.Series(dtype=float))
    usdcad = fx_prices_map.get("USDCAD", pd.Series(dtype=float))

    print(f"  Split date: {split_date.date()}")
    print(f"  Vol target: {_VOL_PLACEHOLDER:.0%} (placeholder — IDM is scale-invariant)\n")
    print("  Running IS portfolio (IDM=1.0)...")

    is_pnl_per_instrument: dict[str, pd.Series] = {}

    for code in instruments:
        if code not in cfgs:
            print(f"  WARNING: no config for {code}, skipping.")
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            print(f"  WARNING: no data for {code}, skipping.")
            continue

        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) < 20:
            continue
        vol_is = daily_vol(is_prices)
        cfg = cfgs[code]
        fdm = float(fdm_data.get(code, 1.0))
        inst_weight = instrument_weights_raw.get(code, 0.0)

        fc_is = combined_forecast(
            is_prices, vol_is, fdm=fdm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
            instrument_code=code,
        )
        fx = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, is_prices.index,
                             usdjpy_prices=usdjpy, usdcad_prices=usdcad)

        pos = compute_positions(
            prices=is_prices, vol=vol_is, forecast=fc_is["combined"],
            pointsize=cfg.pointsize, capital=capital,
            vol_target=_VOL_PLACEHOLDER, idm=1.0, fx_rate_to_usd=fx,
            instrument_weight=inst_weight,
        )
        gpnl = gross_pnl(pos, is_prices, cfg.pointsize)
        costs = transaction_costs(pos, cfg.spread_cost, cfg.pointsize)
        gpnl_usd = to_usd(gpnl, cfg.currency, eurusd, eurgbp, usdjpy, usdcad_prices=usdcad)
        costs_usd = to_usd(costs, cfg.currency, eurusd, eurgbp, usdjpy, usdcad_prices=usdcad)
        net = gpnl_usd - costs_usd
        is_pnl_per_instrument[code] = net / capital

    # Build return correlation matrix
    is_returns = pd.DataFrame(is_pnl_per_instrument)
    ordered_instruments = list(is_returns.columns)
    weights_arr = np.array([instrument_weights_raw.get(c, 0.0)
                            for c in ordered_instruments])

    idm = compute_idm(is_returns, weights=weights_arr)

    corr = is_returns.dropna(how="all").corr(min_periods=20)
    corr_vals = corr.values
    corr_vals = np.where(np.isnan(corr_vals), 0.0, corr_vals)
    np.fill_diagonal(corr_vals, 1.0)

    w = weights_arr / weights_arr.sum()
    port_var = float(w @ corr_vals @ w)
    raw_idm = 1.0 / np.sqrt(port_var)
    capped = idm < raw_idm

    SEP = "─" * 70

    # ── Console: IDM ───────────────────────────────────────────────────────────
    col_w = max(len(c) for c in ordered_instruments)
    print(f"\n  {SEP}")
    print("  IDM  (portfolio-weighted IS PnL correlations)")
    print(f"  {SEP}")
    print(f"  Raw IDM  = 1/sqrt({port_var:.4f}) = {raw_idm:.3f}")
    if capped:
        print(f"  IDM      = {idm:.3f}  (capped at 2.5)")
    else:
        print(f"  IDM      = {idm:.3f}")

    # ── Markdown report — append IDM section to step4_report.md ──────────────
    report_path = st.path("step4_report.md", state_dir=state_dir)
    idm_lines: list[str] = [
        "## IDM  (portfolio-weighted IS PnL correlations)", "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Raw IDM (1/√(w'Cw)) | {raw_idm:.3f} |",
        f"| IDM (after cap 2.5) | {idm:.3f} |",
        f"| Portfolio variance w'Cw | {port_var:.4f} |",
        "",
    ]
    with open(report_path, "a") as f:
        f.write("\n".join(idm_lines))

    # ── Minimum position size check ────────────────────────────────────────────
    capital = load_capital()
    too_small: list[tuple[str, float, float]] = []  # (code, median_lots, lot_step)

    for code in ordered_instruments:
        cfg = cfgs[code]
        inst_weight = instrument_weights_raw.get(code, 0.0)
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) < 20:
            continue
        from src.rules.vol import daily_vol as _daily_vol
        vol_is = _daily_vol(is_prices)
        annual_vol_price = (vol_is * is_prices).mean() * (load_bars_per_year() ** 0.5)
        if annual_vol_price == 0 or cfg.pointsize == 0:
            continue
        target_lots = (capital * _VOL_PLACEHOLDER * idm * inst_weight) / (annual_vol_price * cfg.pointsize)
        if target_lots < cfg.lot_step:
            too_small.append((code, round(target_lots, 4), cfg.lot_step))

    SEP2 = "─" * 70
    print(f"\n  {SEP2}")
    print(f"  MINIMUM POSITION CHECK  (capital={capital:,.0f} USD, vol={_VOL_PLACEHOLDER:.0%}, IDM={idm:.2f})")
    print(f"  {SEP2}")
    if too_small:
        print(f"  {'Instrument':<14} {'Target lots':>12}  {'Min lot':>8}  Status")
        print(f"  {'─' * 48}")
        for code, lots, step in too_small:
            print(f"  {code:<14} {lots:>12.4f}  {step:>8.4f}  ⚠ below minimum")
    else:
        print("  All instruments clear the minimum lot threshold.")

    # Append min-position section to report
    min_pos_lines: list[str] = [
        f"## Minimum Position Check",
        f"",
        f"Capital: {capital:,.0f} USD | Vol target: {_VOL_PLACEHOLDER:.0%} | IDM: {idm:.3f}",
        "",
    ]
    if too_small:
        min_pos_lines += [
            "| Instrument | Target lots | Min lot |",
            "|------------|-------------|---------|",
        ]
        for code, lots, step in too_small:
            min_pos_lines.append(f"| {code} | {lots:.4f} | {step:.4f} |")
    else:
        min_pos_lines.append("All instruments clear the minimum lot threshold.")
    min_pos_lines.append("")

    with open(report_path, "a") as f:
        f.write("\n".join(min_pos_lines))

    # Save state
    st.save("step4b_idm.yaml", {"idm": round(idm, 4)}, state_dir=state_dir)
    print(f"\n  Saved:")
    print(f"    {st.path('step4b_idm.yaml', state_dir=state_dir)}")
    print(f"    {report_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 4b: IDM computation")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    args = parser.parse_args()

    from src.backtest.config import set_config
    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "results")

"""
Step 4b: Compute IDM from IS instrument return correlations.

Runs IS-only portfolio with calibrated parameters (IDM=1.0), builds the
return correlation matrix, then derives IDM = 1/sqrt(w'Cw).

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
from src.backtest.config import load_instrument_configs, traded_instruments, required_fx_helpers
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.idm import compute_idm
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol


def main(state_dir=None, split_date=None) -> None:
    # Load all state
    scalars_data = st.load("step3a_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("step3d_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("step3d_fdm.yaml", state_dir=state_dir)
    vol_target_data = st.load("step5_vol_target.yaml", state_dir=state_dir)
    inst_weights_data = st.load("step4a_instrument_weights.yaml", state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }
    vol_target = float(vol_target_data["vol_target"])
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
    print(f"  Vol target: {vol_target:.0%}\n")
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
            vol_target=vol_target, idm=1.0, fx_rate_to_usd=fx,
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

    # Print correlation matrix
    corr = is_returns.dropna(how="all").corr(min_periods=20)
    corr_vals = corr.values
    corr_vals = np.where(np.isnan(corr_vals), 0.0, corr_vals)
    np.fill_diagonal(corr_vals, 1.0)

    print()
    print("  IS instrument return correlation matrix")
    header = "  " + " " * 8 + "".join(f"{c:>8}" for c in ordered_instruments)
    print(header)
    print("  " + "─" * (8 + 8 * len(ordered_instruments)))
    for i, code in enumerate(ordered_instruments):
        row = f"  {code:<8}" + "".join(f"{corr_vals[i, j]:>8.3f}"
                                        for j in range(len(ordered_instruments)))
        print(row)

    # IDM derivation
    w = weights_arr / weights_arr.sum()
    port_var = w @ corr_vals @ w
    cap_msg = "" if idm < 2.5 else "  (capped at 2.5)"
    capped = idm >= 2.5
    not_capped_msg = "not capped" if not capped else "capped"
    print()
    print(f"  IDM = 1/sqrt({port_var:.3f}) = {1.0/np.sqrt(port_var):.3f}  ({not_capped_msg}; cap = 2.5)")
    if capped:
        print(f"  IDM (after cap) = {idm:.3f}")

    # Save state
    st.save("step4b_idm.yaml", {"idm": round(idm, 4)}, state_dir=state_dir)
    print(f"\n  Saved → {st.path('07_idm.yaml', state_dir=state_dir)}")


if __name__ == "__main__":
    main()

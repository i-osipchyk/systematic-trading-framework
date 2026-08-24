"""
Step 3c: Cost filtering — empirical IS turnover and standardised cost ceiling.

Measures roundtrips/year per rule (pooled across instruments) and per
instrument (combined forecast). Prints the 0.13/turnover cost ceiling so
rule-instrument combinations that exceed it can be flagged for exclusion.

Usage:
    uv run python calibrate/step3c_cost_filter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.calibration import state as st
from src.backtest.config import load_bars_per_year, load_instrument_configs, traded_instruments, required_fx_helpers
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.sizing import compute_positions
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

COST_BUDGET = 0.13  # Carver's turnover × max_standardised_cost constant


def _roundtrips_per_year(positions: pd.Series) -> float:
    daily_trades = positions.diff().abs()
    mean_pos = positions.abs().mean()
    if mean_pos == 0:
        return 0.0
    n_years = len(positions.dropna()) / load_bars_per_year()
    if n_years == 0:
        return 0.0
    return float(daily_trades.sum() / 2 / mean_pos / n_years)


def main(state_dir=None, split_date=None) -> None:
    scalars_data = st.load("step3a_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("step3d_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("step3d_fdm.yaml", state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    if split_date is None:
        split_date = compute_split_date(instruments)

    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices = {code: load_adjusted_prices(code) for code in fx_helper_codes}
    for fx in ("EURUSD", "EURGBP", "USDJPY", "USDCAD"):
        if fx in instruments and fx not in fx_prices:
            fx_prices[fx] = load_adjusted_prices(fx)
    eurusd = fx_prices.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices.get("USDJPY", pd.Series(dtype=float))
    usdcad = fx_prices.get("USDCAD", pd.Series(dtype=float))

    # Collect all rule names from family_scalars
    all_rule_names: list[str] = []
    for family_name, scalars in family_scalars.items():
        handler = REGISTRY[family_name]
        for variant in scalars:
            all_rule_names.append(handler.rule_name(variant))

    rule_turnovers: dict[str, list[float]] = {r: [] for r in all_rule_names}
    instrument_turnovers: dict[str, float] = {}

    print(f"  Split date (IS end): {split_date.date()}\n")
    print("  Computing IS turnover per rule and instrument...")

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

        fx = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, is_prices.index,
                             usdjpy_prices=usdjpy, usdcad_prices=usdcad)

        # Per-rule turnover via REGISTRY
        for family_name, scalars in family_scalars.items():
            handler = REGISTRY[family_name]

            # Seasonality scalars are {instrument_code: {month: float}} — compute_all
            # handles the lookup; compute_one_raw always returns zeros for this family.
            if family_name == "seasonality":
                fc_df = handler.compute_all(is_prices, vol_is, scalars,
                                            instrument_code=code)
                if "SEASONALITY" in fc_df.columns:
                    forecast = fc_df["SEASONALITY"].clip(-20, 20)
                    pos = compute_positions(
                        prices=is_prices, vol=vol_is, forecast=forecast,
                        pointsize=cfg.pointsize, capital=10_000.0,
                        vol_target=0.15, idm=1.0, fx_rate_to_usd=fx,
                        instrument_weight=1.0,
                    )
                    rule_turnovers["SEASONALITY"].append(_roundtrips_per_year(pos))
                continue

            for variant, scalar in scalars.items():
                rule_name = handler.rule_name(variant)
                raw = handler.compute_one_raw(is_prices, variant, vol_is,
                                              instrument_code=code)
                forecast = (raw * scalar).clip(-20, 20)
                pos = compute_positions(
                    prices=is_prices, vol=vol_is, forecast=forecast,
                    pointsize=cfg.pointsize, capital=10_000.0,
                    vol_target=0.15, idm=1.0, fx_rate_to_usd=fx,
                    instrument_weight=1.0,
                )
                rule_turnovers[rule_name].append(_roundtrips_per_year(pos))

        # Combined forecast turnover
        fc_is = combined_forecast(
            is_prices, vol_is, fdm=fdm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
            instrument_code=code,
        )
        combined_pos = compute_positions(
            prices=is_prices, vol=vol_is, forecast=fc_is["combined"],
            pointsize=cfg.pointsize, capital=10_000.0,
            vol_target=0.15, idm=1.0, fx_rate_to_usd=fx,
            instrument_weight=cfg.weight,
        )
        instrument_turnovers[code] = _roundtrips_per_year(combined_pos)

    pooled_rule_turnovers = {
        rule: float(np.mean(vals)) if vals else 0.0
        for rule, vals in rule_turnovers.items()
    }

    inst_weights = [cfgs[code].weight for code in instrument_turnovers]
    inst_tvs = [instrument_turnovers[code] for code in instrument_turnovers]
    total_w = sum(inst_weights)
    weighted_avg = (
        float(sum(w * tv for w, tv in zip(inst_weights, inst_tvs)) / total_w)
        if total_w > 0 else 0.0
    )

    st.save("step3c_turnover.yaml", {
        "rules": {k: round(v, 2) for k, v in pooled_rule_turnovers.items()},
        "instruments": {k: round(v, 2) for k, v in instrument_turnovers.items()},
        "weighted_avg": round(weighted_avg, 2),
    }, state_dir=state_dir)

    # Print per-rule table with cost ceiling
    print()
    print(f"  {'Rule':<18} {'Turnover':>10}  {'Max std cost':>13}  (0.13/turnover)")
    print(f"  {'─' * 48}")
    for rule, tv in pooled_rule_turnovers.items():
        ceiling = COST_BUDGET / tv if tv > 0 else float("inf")
        print(f"  {rule:<18} {tv:>10.1f}  {ceiling:>13.4f}")

    # Per-instrument combined turnover
    print()
    print(f"  {'Instrument':<14} {'Turnover':>10}")
    print(f"  {'─' * 26}")
    for code, tv in instrument_turnovers.items():
        print(f"  {code:<14} {tv:>10.1f}")

    print()
    print(f"  Portfolio weighted avg turnover: {weighted_avg:.1f} RT/yr")
    print(f"\n  Saved → {st.path('step3c_turnover.yaml', state_dir=state_dir)}")


if __name__ == "__main__":
    main()

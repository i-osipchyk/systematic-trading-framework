"""
Step 04: Measure empirical IS turnover per rule and per instrument.

Runs each rule's forecast separately (scalar 1.0 FDM, IDM, weight) and
computes roundtrips/year, pooled across instruments.

Usage:
    uv run python calibrate/04_turnover.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.calibration import state as st
from src.backtest.config import load_bars_per_year, load_instrument_configs, traded_instruments, required_fx_helpers
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.ewmac import ewmac
from src.rules.mr import mean_reversion
from src.rules.vol import daily_vol


def _roundtrips_per_year(positions: pd.Series) -> float:
    daily_trades = positions.diff().abs()
    mean_pos = positions.abs().mean()
    if mean_pos == 0:
        return 0.0
    n_years = len(positions.dropna()) / load_bars_per_year()
    if n_years == 0:
        return 0.0
    return float(daily_trades.sum() / 2 / mean_pos / n_years)


def main(state_dir=None) -> None:
    # Load state
    scalars_data = st.load("01_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("02_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("03_fdm.yaml", state_dir=state_dir)

    ewmac_scalars = st.parse_ewmac_scalars(scalars_data.get("ewmac", {}))
    mr_scalars = st.parse_mr_scalars(scalars_data.get("mr", {}))
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    split_date = compute_split_date(instruments)

    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices = {code: load_adjusted_prices(code) for code in fx_helper_codes}
    # USDJPY is traded (not in fx_helpers) but still needed for JPY→USD conversion
    if "USDJPY" in instruments and "USDJPY" not in fx_prices:
        fx_prices["USDJPY"] = load_adjusted_prices("USDJPY")
    eurusd_prices = fx_prices.get("EURUSD", pd.Series(dtype=float))
    eurgbp_prices = fx_prices.get("EURGBP", pd.Series(dtype=float))
    usdjpy_prices = fx_prices.get("USDJPY", pd.Series(dtype=float))

    # Build rule list
    ewmac_rules = [(f, s) for f, s in ewmac_scalars.keys()]
    mr_rule_spans = list(mr_scalars.keys())
    all_rule_names = (
        [f"EWMAC_{f}_{s}" for f, s in ewmac_rules] +
        [f"MR_{span}" for span in mr_rule_spans]
    )

    # Per-rule turnover accumulator: {rule_name: [turnover_per_instrument]}
    rule_turnovers: dict[str, list[float]] = {r: [] for r in all_rule_names}
    # Per-instrument turnover (combined forecast)
    instrument_turnovers: dict[str, float] = {}

    print(f"  Split date: {split_date.date()}\n")
    print("  Computing turnover per rule and instrument...")

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
        vol_is = daily_vol(is_prices)
        cfg = cfgs[code]
        fdm = float(fdm_data.get(code, 1.0))

        def _fx(idx: pd.Index) -> pd.Series | float:
            from src.backtest.engine import _fx_rate_to_usd
            return _fx_rate_to_usd(cfg.currency, eurusd_prices, eurgbp_prices, idx,
                                   usdjpy_prices=usdjpy_prices)

        # Per-rule turnover
        for fast, slow in ewmac_rules:
            rule_name = f"EWMAC_{fast}_{slow}"
            scalar = ewmac_scalars[(fast, slow)]
            forecast = ewmac(is_prices, fast, slow, vol_is, scalar=scalar)
            pos = compute_positions(
                prices=is_prices, vol=vol_is, forecast=forecast,
                pointsize=cfg.pointsize, capital=10_000.0,
                vol_target=0.15, idm=1.0, fx_rate_to_usd=_fx(is_prices.index),
                instrument_weight=1.0,
            )
            rule_turnovers[rule_name].append(_roundtrips_per_year(pos))

        for span in mr_rule_spans:
            rule_name = f"MR_{span}"
            scalar = mr_scalars[span]
            forecast = mean_reversion(is_prices, span, vol_is, scalar=scalar)
            pos = compute_positions(
                prices=is_prices, vol=vol_is, forecast=forecast,
                pointsize=cfg.pointsize, capital=10_000.0,
                vol_target=0.15, idm=1.0, fx_rate_to_usd=_fx(is_prices.index),
                instrument_weight=1.0,
            )
            rule_turnovers[rule_name].append(_roundtrips_per_year(pos))

        # Combined forecast turnover
        fc_is = combined_forecast(
            is_prices, vol_is, fdm=fdm,
            ewmac_scalars=ewmac_scalars,
            mr_scalars=mr_scalars,
            rule_weights=rule_weights,
        )
        combined_pos = compute_positions(
            prices=is_prices, vol=vol_is, forecast=fc_is["combined"],
            pointsize=cfg.pointsize, capital=10_000.0,
            vol_target=0.15, idm=1.0, fx_rate_to_usd=_fx(is_prices.index),
            instrument_weight=cfg.weight,
        )
        instrument_turnovers[code] = _roundtrips_per_year(combined_pos)

    # Pool rule turnovers (average across instruments)
    pooled_rule_turnovers = {
        rule: float(np.mean(vals)) if vals else 0.0
        for rule, vals in rule_turnovers.items()
    }

    # Portfolio weighted average turnover
    inst_weights = [cfgs[code].weight for code in instrument_turnovers]
    inst_tvs = [instrument_turnovers[code] for code in instrument_turnovers]
    total_w = sum(inst_weights)
    weighted_avg = float(
        sum(w * tv for w, tv in zip(inst_weights, inst_tvs)) / total_w
    ) if total_w > 0 else 0.0

    # Save state
    st.save("04_turnover.yaml", {
        "rules": {k: round(v, 2) for k, v in pooled_rule_turnovers.items()},
        "instruments": {k: round(v, 2) for k, v in instrument_turnovers.items()},
        "weighted_avg": round(weighted_avg, 2),
    }, state_dir=state_dir)

    # Print table
    print()
    print(f"  {'Rule':<16} {'Turnover (RT/yr)':>17}")
    print(f"  {'─' * 35}")
    for rule, tv in pooled_rule_turnovers.items():
        print(f"  {rule:<16} {tv:>17.1f}")

    print()
    print(f"  {'Instrument':<14} {'Turnover (RT/yr)':>17}")
    print(f"  {'─' * 33}")
    for code, tv in instrument_turnovers.items():
        print(f"  {code:<14} {tv:>17.1f}")

    print()
    print(f"  Portfolio weighted avg turnover: {weighted_avg:.1f} RT/yr")
    print(f"\n  Saved → {st.path('04_turnover.yaml', state_dir=state_dir)}")


if __name__ == "__main__":
    main()

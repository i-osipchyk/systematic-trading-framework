"""
Step 05: Kelly analysis → user confirms vol target.

Runs IS-only portfolio backtest with calibrated scalars and FDMs,
computes Sharpe, applies Kelly criterion, then asks user to confirm a
volatility target.

Usage:
    uv run python calibrate/05_vol_target.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.calibration import state as st
from src.backtest.config import load_instrument_configs, traded_instruments, required_fx_helpers
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.metrics import sharpe_ratio
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

FILENAME = "05_vol_target.yaml"
FIXED_VOL_FOR_MEASUREMENT = 0.20


def _run_is_portfolio(
    instruments: list[str],
    family_scalars: dict,
    rule_weights: dict,
    fdm_data: dict,
    capital: float = 10_000.0,
) -> tuple[float, float]:
    """Run IS-only portfolio and return (is_sharpe, vol_target_used)."""
    cfgs = load_instrument_configs()
    split_date = compute_split_date(instruments)
    n = len(instruments)
    equal_weight = 1.0 / n

    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices_map = {code: load_adjusted_prices(code) for code in fx_helper_codes}
    for _fx in ("EURUSD", "EURGBP", "USDJPY"):
        if _fx in instruments and _fx not in fx_prices_map:
            fx_prices_map[_fx] = load_adjusted_prices(_fx)
    eurusd = fx_prices_map.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices_map.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices_map.get("USDJPY", pd.Series(dtype=float))

    all_pnl = {}

    for code in instruments:
        if code not in cfgs:
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue

        is_prices, _ = split_series(prices, split_date)
        vol_is = daily_vol(is_prices)
        cfg = cfgs[code]
        fdm = float(fdm_data.get(code, 1.0))

        fc_is = combined_forecast(
            is_prices, vol_is, fdm=fdm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
        )
        fx = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, is_prices.index,
                             usdjpy_prices=usdjpy)

        pos = compute_positions(
            prices=is_prices, vol=vol_is, forecast=fc_is["combined"],
            pointsize=cfg.pointsize, capital=capital,
            vol_target=FIXED_VOL_FOR_MEASUREMENT,
            idm=1.0,
            fx_rate_to_usd=fx,
            instrument_weight=equal_weight,
        )

        gpnl = gross_pnl(pos, is_prices, cfg.pointsize)
        costs = transaction_costs(pos, cfg.spread_cost, cfg.pointsize)
        gpnl_usd = to_usd(gpnl, cfg.currency, eurusd, eurgbp, usdjpy)
        costs_usd = to_usd(costs, cfg.currency, eurusd, eurgbp, usdjpy)
        all_pnl[code] = (gpnl_usd - costs_usd)

    portfolio_pnl = pd.DataFrame(all_pnl).sum(axis=1)
    sr = sharpe_ratio(portfolio_pnl, capital)
    return sr, FIXED_VOL_FOR_MEASUREMENT


def main(state_dir=None) -> None:
    scalars_data = st.load("01_scalars.yaml", state_dir=state_dir)
    weights_data = st.load("02_forecast_weights.yaml", state_dir=state_dir)
    fdm_data = st.load("03_fdm.yaml", state_dir=state_dir)

    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)

    print("  Running IS portfolio backtest (vol target fixed at"
          f" {FIXED_VOL_FOR_MEASUREMENT:.0%} for SR measurement)...")
    is_sharpe, _ = _run_is_portfolio(
        instruments, family_scalars, rule_weights, fdm_data
    )

    # Kelly analysis
    realistic_sr = is_sharpe * 0.75
    full_kelly = realistic_sr          # as a vol fraction
    half_kelly = realistic_sr / 2.0
    suggested = float(np.clip(np.sqrt(full_kelly * half_kelly), 0.05, 0.40))

    print()
    print(f"  IS Sharpe (after costs)     : {is_sharpe:.2f}")
    print(f"  Realistic future SR (×0.75) : {realistic_sr:.2f}")
    print(f"  {'─' * 38}")
    print(f"  Full Kelly vol target       : {full_kelly:.0%}")
    print(f"  Half Kelly vol target       : {half_kelly:.0%}")
    print(f"  Suggested (geometric mean)  : {suggested:.0%}")
    print(f"  {'─' * 38}")
    print(f"  Return distribution skew    : positive (trend-following)")
    print(f"                                → lean toward Full Kelly")

    template_existed = st.exists(FILENAME, state_dir=state_dir)

    if not template_existed:
        content = (
            "# Volatility target configuration\n"
            "# ─────────────────────────────────────────────────────────────────\n"
            "# Edit vol_target below and save, then press Enter in the terminal.\n"
            "#\n"
            f"# Kelly analysis:\n"
            f"#   IS Sharpe            : {is_sharpe:.2f}\n"
            f"#   Realistic SR (×0.75) : {realistic_sr:.2f}\n"
            f"#   Full Kelly           : {full_kelly:.2%}\n"
            f"#   Half Kelly           : {half_kelly:.2%}\n"
            f"#   Suggested            : {suggested:.2%}\n"
            "#\n"
            "# Range: 0.02 to 0.50 (e.g. 0.15 = 15%)\n"
            "#\n"
            f"vol_target: {suggested:.2f}\n"
        )
        actual_path = st.path(FILENAME, state_dir=state_dir)
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        actual_path.write_text(content)
        print(f"\n  Wrote template → {actual_path}")

    print()
    print(f"  Edit {st.path(FILENAME, state_dir=state_dir)}")
    print(f"  → set vol_target, then press Enter")
    print()

    while True:
        try:
            input("  Press Enter when done (Ctrl+C to abort)...")
        except KeyboardInterrupt:
            print("\n  Aborted.")
            sys.exit(1)

        if not st.exists(FILENAME, state_dir=state_dir):
            print("  ERROR: file not found.")
            continue

        data = yaml.safe_load(st.path(FILENAME, state_dir=state_dir).read_text())
        vol_target = data.get("vol_target")

        if not isinstance(vol_target, (int, float)):
            print("  ERROR: vol_target must be a number.")
            continue
        if not (0.02 <= vol_target <= 0.50):
            print(f"  ERROR: vol_target {vol_target} out of range [0.02, 0.50].")
            continue
        break

    print(f"  Vol target set to {vol_target:.0%}")
    print(f"\n  Saved → {st.path(FILENAME, state_dir=state_dir)}")

    return {
        "is_sharpe": round(is_sharpe, 4),
        "realistic_sharpe": round(realistic_sr, 4),
        "full_kelly": round(full_kelly, 4),
        "half_kelly": round(half_kelly, 4),
        "vol_target": float(vol_target),
    }


if __name__ == "__main__":
    main()

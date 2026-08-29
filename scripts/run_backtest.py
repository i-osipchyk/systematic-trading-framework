#!/usr/bin/env python3
"""
Run the full IS/OOS backtest and print a performance report.

Usage:
    uv run python scripts/run_backtest.py
    uv run python scripts/run_backtest.py --capital 50000 --vol-target 0.25
"""

import argparse

from src.backtest.engine import INSTRUMENTS, run_portfolio
from src.backtest.metrics import annual_turnover, performance_report


def main():
    parser = argparse.ArgumentParser(description="Run IS/OOS backtest")
    parser.add_argument("--capital",    type=float, default=100_000.0,
                        help="Starting capital in USD (default: 10,000)")
    parser.add_argument("--vol-target", type=float, default=0.15,
                        help="Annual volatility target 0–1 (default: 0.20)")
    args = parser.parse_args()

    result = run_portfolio(capital=args.capital, vol_target=args.vol_target)

    # ── Header ────────────────────────────────────────────────────────────────
    print(f"{'─'*60}")
    print(f"  Backtest summary")
    print(f"{'─'*60}")
    print(f"  Split date  : {result.split_date.date()}")
    print(f"  Capital     : ${result.capital:>12,.0f}")
    print(f"  Vol target  : {args.vol_target:.0%}")
    print(f"  IDM         : {result.idm:.3f}")
    print()

    # ── Per-instrument calibration ────────────────────────────────────────────
    print(f"  {'Instrument':<10} {'FDM':>6}")
    print(f"  {'─'*18}")
    for code in INSTRUMENTS:
        if code in result.fdms:
            print(f"  {code:<10} {result.fdms[code]:>6.3f}")

    # ── Portfolio performance ─────────────────────────────────────────────────
    print()
    print(f"  Portfolio performance:")
    print(f"  {'Period':<6} {'Sharpe':>8} {'Ann Ret':>9} {'Max DD':>9} {'Bars':>6}")
    print(f"  {'─'*44}")
    for label, pnl in [("IS", result.is_pnl), ("OOS", result.oos_pnl)]:
        m = performance_report(pnl, result.capital, label=label)
        n = pnl.dropna().__len__()
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

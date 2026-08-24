"""
Step 00: Ensure all required instrument data is present and up to date.

For each instrument in the config (traded + FX helpers):
  - If no local data: fetch from the earliest date found across existing files
    (or 2018-01-01 if nothing exists) through today.
  - If data exists but ends more than 5 days ago: fetch from the last bar
    date through today.
  - If data is current: skip.

Uses a subprocess to invoke fetch_history.py so the Twisted reactor can
be started fresh for each fetch batch.

Usage:
    uv run python calibrate/step0_fetch_data.py
    uv run python calibrate/step0_fetch_data.py --demo
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import (
    CONFIG_PATH,
    load_instrument_configs,
    load_timeframe,
    required_fx_helpers,
)
from src.data.pst_writer import adjusted_prices_dir

import pandas as pd

DEFAULT_START = date(2018, 1, 1)
STALENESS_DAYS = 5   # allow weekends + public holidays


def _data_status(code: str) -> tuple[date | None, date | None]:
    """Return (first_date, last_date) for a local CSV, or (None, None) if missing."""
    path = adjusted_prices_dir() / f"{code}.csv"
    if not path.exists():
        return None, None
    series = pd.read_csv(path, index_col=0, parse_dates=True).squeeze()
    first = series.index.min().date()
    last = series.index.max().date()
    return first, last


def _run_fetch(codes: list[str], from_dt: date, to_dt: date, demo: bool, period: str) -> None:
    """Invoke fetch_history.py in a subprocess for the given instrument codes."""
    cmd = [
        "uv", "run", "python", "scripts/fetch_history.py",
        "--from", str(from_dt),
        "--to",   str(to_dt),
        "--period", period,
        "--instruments", *codes,
    ]
    if demo:
        cmd.append("--demo")

    # Pass the active config path so the subprocess uses the same config
    env = {**os.environ, "TRADING_CONFIG": str(CONFIG_PATH)}

    print(f"\n  Fetching {len(codes)} instrument(s): {', '.join(codes)}")
    print(f"  Range: {from_dt} → {to_dt}")
    print(f"  Command: {' '.join(cmd[3:])}\n")

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print(f"\n  WARNING: fetch exited with code {result.returncode} — check output above.")


def main(state_dir=None, demo: bool = False) -> None:
    cfgs = load_instrument_configs()
    # Fetch everything declared in the config (traded or not) so FX helpers
    # that are explicitly listed are always available to the backtest engine.
    # Also include any auto-detected helpers that aren't in the config at all.
    config_codes = list(cfgs.keys())
    extra_helpers = [c for c in required_fx_helpers(cfgs) if c not in cfgs]
    all_needed = config_codes + extra_helpers
    period = load_timeframe()

    today = datetime.now(timezone.utc).date()
    print(f"  Timeframe: {period}")

    # ── Assess status of each instrument ─────────────────────────────────────
    missing:       list[str] = []
    needs_update:  list[tuple[str, date]] = []  # (code, last_date)
    up_to_date:    list[str] = []
    existing_starts: list[date] = []

    for code in all_needed:
        first, last = _data_status(code)
        if first is None:
            missing.append(code)
        else:
            existing_starts.append(first)
            if last < today - timedelta(days=STALENESS_DAYS):
                needs_update.append((code, last))
            else:
                up_to_date.append(code)

    global_start = min(existing_starts) if existing_starts else DEFAULT_START

    # ── Print status table ────────────────────────────────────────────────────
    print(f"  {'Code':<10} {'Status':<20} {'First':>12} {'Last':>12}")
    print(f"  {'─'*56}")
    for code in up_to_date:
        first, last = _data_status(code)
        print(f"  {code:<10} {'up to date':<20} {str(first):>12} {str(last):>12}")
    for code, last in needs_update:
        first, _ = _data_status(code)
        print(f"  {code:<10} {'needs update':<20} {str(first):>12} {str(last):>12}")
    for code in missing:
        print(f"  {code:<10} {'MISSING':<20} {'—':>12} {'—':>12}")

    if not missing and not needs_update:
        print(f"\n  All data is current.")
        return

    if missing:
        print(f"\n  Missing instruments → fetching from {global_start} (earliest found date)")
        _run_fetch(missing, global_start, today, demo, period)

    if needs_update:
        # Group by last_date to minimise subprocess calls
        batches: dict[date, list[str]] = {}
        for code, last in needs_update:
            batches.setdefault(last, []).append(code)
        for last_date, codes in sorted(batches.items()):
            print(f"\n  Stale instruments (last bar: {last_date}) → updating to today")
            _run_fetch(codes, last_date, today, demo, period)

    print(f"\n  Data fetch complete.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Use demo account")
    args = parser.parse_args()
    main(demo=args.demo)

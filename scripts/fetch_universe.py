"""
Fetch 40-year price history for the target 25-instrument universe.

Priority order per instrument:
  1. Nasdaq Data Link CHRIS  (Panama continuous, requires NASDAQ_DATA_LINK_API_KEY)
  2. Yahoo Finance            (front-month futures or cash index, always available)

After downloading external data, the script appends any existing cTrader data
(already on disk in data/futures/D1/) for the most recent period, filling the
gap between the last external bar and today.

The combined series is written to:
  data/futures/D1/adjusted_prices_csv/<CODE>.csv
  data/futures/D1/multiple_prices_csv/<CODE>.csv

Usage:
    uv run python scripts/fetch_universe.py
    uv run python scripts/fetch_universe.py --start 1984-01-01
    uv run python scripts/fetch_universe.py --no-quandl        # yfinance only
    uv run python scripts/fetch_universe.py --instruments XAU COPPER
    uv run python scripts/fetch_universe.py --dry-run          # print plan, no writes
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.data.pst_writer import (
    write_adjusted_prices,
    write_multiple_prices,
    adjusted_prices_dir,
)
from src.data.yf_loader import fetch_yfinance
from src.data.quandl_loader import fetch_quandl

UNIVERSE_CONFIG = ROOT / "config" / "universe_40yr.yaml"
TIMEFRAME = "D1"  # universe is daily; always write to the D1 data directory


def load_universe() -> dict:
    with open(UNIVERSE_CONFIG) as f:
        return yaml.safe_load(f)["instruments"]


def load_existing(code: str) -> pd.DataFrame | None:
    """Load existing adjusted prices from disk (any source, already written)."""
    path = adjusted_prices_dir("D1") / f"{code}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["DATETIME"])
    df = df.rename(columns={"price": "CLOSE"})
    df["DATETIME"] = pd.to_datetime(df["DATETIME"])
    return df[["DATETIME", "CLOSE"]].dropna()


def merge_series(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Merge two DATETIME/CLOSE DataFrames, preferring new data on overlap."""
    if old is None or old.empty:
        return new
    combined = pd.concat([old, new], ignore_index=True)
    combined = combined.drop_duplicates(subset="DATETIME", keep="last")
    combined = combined.sort_values("DATETIME").reset_index(drop=True)
    return combined


def df_to_pst_format(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Convert a DATETIME/CLOSE DataFrame to pst_writer-compatible format."""
    out = df.copy()
    out["DATETIME"] = out["DATETIME"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out["OPEN"] = out["CLOSE"]
    out["HIGH"] = out["CLOSE"]
    out["LOW"] = out["CLOSE"]
    out["VOLUME"] = 0
    return out[["DATETIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]]


def fetch_instrument(
    code: str,
    cfg: dict,
    start: str,
    use_quandl: bool,
) -> pd.DataFrame | None:
    """Fetch price data for a single instrument.

    Returns a DATETIME/CLOSE DataFrame, or None on failure.
    """
    frames: list[pd.DataFrame] = []

    # 1. Quandl CHRIS (best for continuous futures)
    if use_quandl and cfg.get("quandl_dataset"):
        print(f"  [quandl] {cfg['quandl_dataset']} ... ", end="", flush=True)
        raw = fetch_quandl(cfg["quandl_dataset"], start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            frames.append(raw[["DATETIME", "CLOSE"]])
            print(f"{len(raw)} bars from {raw['DATETIME'].iloc[0].date()} to {raw['DATETIME'].iloc[-1].date()}")
        else:
            print("no data")

    # 2. Yahoo Finance
    if cfg.get("yf_ticker") and (not frames or frames[0]["DATETIME"].iloc[0].year > int(start[:4]) + 3):
        print(f"  [yfinance] {cfg['yf_ticker']} ... ", end="", flush=True)
        raw = fetch_yfinance(cfg["yf_ticker"], start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            frames.append(raw[["DATETIME", "CLOSE"]])
            print(f"{len(raw)} bars from {raw['DATETIME'].iloc[0].date()} to {raw['DATETIME'].iloc[-1].date()}")
        else:
            print("no data")

    if not frames:
        return None

    # Take the frame with earliest start date; then append later frames for recency
    frames.sort(key=lambda d: d["DATETIME"].iloc[0])
    result = frames[0]
    for extra in frames[1:]:
        result = merge_series(result, extra)

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch 40-year universe history")
    parser.add_argument("--start", default="1984-01-01", help="Earliest date to fetch (YYYY-MM-DD)")
    parser.add_argument("--no-quandl", action="store_true", help="Skip Nasdaq Data Link, use yfinance only")
    parser.add_argument("--instruments", nargs="+", metavar="CODE", help="Subset of instrument codes")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    args = parser.parse_args()

    universe = load_universe()
    if args.instruments:
        missing = set(args.instruments) - set(universe)
        if missing:
            print(f"ERROR: Unknown instruments: {missing}")
            sys.exit(1)
        universe = {k: v for k, v in universe.items() if k in args.instruments}

    use_quandl = not args.no_quandl

    print(f"\nFetching {len(universe)} instruments from {args.start}")
    print(f"Quandl: {'enabled (set NASDAQ_DATA_LINK_API_KEY)' if use_quandl else 'disabled'}")
    if args.dry_run:
        print("DRY RUN — no files will be written\n")

    results: dict[str, str] = {}

    for code, cfg in universe.items():
        print(f"\n{'─'*60}")
        print(f"  {code} — {cfg.get('description', '')}")

        df = fetch_instrument(code, cfg, start=args.start, use_quandl=use_quandl)

        if df is None or df.empty:
            print(f"  WARNING: no data for {code} — skipped")
            results[code] = "NO DATA"
            continue

        # Merge with any existing on-disk data
        existing = load_existing(code)
        if existing is not None and not existing.empty:
            before = len(df)
            df = merge_series(df, existing)
            added = len(df) - before
            if added > 0:
                print(f"  [merge] appended {added} bars from existing cTrader data")

        df = df.sort_values("DATETIME").reset_index(drop=True)
        start_date = df["DATETIME"].iloc[0].date()
        end_date = df["DATETIME"].iloc[-1].date()
        total_bars = len(df)

        print(f"  TOTAL: {total_bars} bars  ({start_date} → {end_date})")

        if args.dry_run:
            results[code] = f"{total_bars} bars  ({start_date} → {end_date})"
            continue

        pst_df = df_to_pst_format(df, code)
        adj_path = write_adjusted_prices(pst_df, code, timeframe=TIMEFRAME)
        write_multiple_prices(pst_df, code, timeframe=TIMEFRAME)
        print(f"  Written → {adj_path}")
        results[code] = f"{total_bars} bars  ({start_date} → {end_date})"

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for code, status in results.items():
        print(f"  {code:<12} {status}")
    print()


if __name__ == "__main__":
    main()

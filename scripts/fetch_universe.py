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
from dotenv import load_dotenv

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.data.pst_writer import (
    write_adjusted_prices,
    write_multiple_prices,
    adjusted_prices_dir,
)
from src.data.yf_loader import fetch_yfinance
from src.data.quandl_loader import fetch_quandl
from src.data.fred_loader import (
    fetch_bond_price,
    fetch_ecb_bund_price,
    fetch_fred_price,
    fetch_fred_fx,
    fetch_fred_eurgbp,
    fetch_datahub_gold,
    fetch_eco3min_silver,
    splice_series,
)

UNIVERSE_CONFIG = ROOT / "config" / "universe_40yr_wf.yaml"
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


def _report(raw: pd.DataFrame) -> str:
    if raw.empty:
        return "no data"
    return f"{len(raw)} bars from {raw['DATETIME'].iloc[0].date()} to {raw['DATETIME'].iloc[-1].date()}"


def fetch_instrument(
    code: str,
    cfg: dict,
    start: str,
    use_quandl: bool,
) -> pd.DataFrame | None:
    """Fetch price data for a single instrument.

    Source priority:
      1. Quandl CHRIS  — Panama-adjusted continuous futures (requires API key)
      2. Yahoo Finance — front-month futures / cash index
      3. FRED          — bond yield → price proxy (bonds) or spot price (crude)

    For bonds and crude, FRED extends the yfinance series back to 1962/1977/1986
    using a price-level splice at the overlap point.

    Returns a DATETIME/CLOSE DataFrame, or None on failure.
    """
    best: pd.DataFrame | None = None

    # 1. Quandl CHRIS
    if use_quandl and cfg.get("quandl_dataset"):
        print(f"  [quandl] {cfg['quandl_dataset']} ... ", end="", flush=True)
        raw = fetch_quandl(cfg["quandl_dataset"], start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            best = raw[["DATETIME", "CLOSE"]]
            print(_report(best))
        else:
            print("no data")

    # 2. Yahoo Finance (use if Quandl failed or didn't go back far enough)
    yf_start = start if best is None else start
    if cfg.get("yf_ticker") and (best is None or best["DATETIME"].iloc[0].year > int(start[:4]) + 3):
        print(f"  [yfinance] {cfg['yf_ticker']} ... ", end="", flush=True)
        raw = fetch_yfinance(cfg["yf_ticker"], start=yf_start)
        if not raw.empty and "CLOSE" in raw.columns:
            yf_df = raw[["DATETIME", "CLOSE"]]
            print(_report(yf_df))
            best = yf_df if best is None else merge_series(best, yf_df)
        else:
            print("no data")

    # 3. FRED + ECB — bond price proxy (FRED monthly early, ECB daily late, then
    #    the combined yield-derived series is spliced behind Quandl/yfinance)
    if cfg.get("fred_bond"):
        print(f"  [fred] bond yield → price ({cfg['fred_bond']}) ... ", end="", flush=True)
        raw = fetch_bond_price(cfg["fred_bond"], start=start)
        fred_df = raw[["DATETIME", "CLOSE"]] if not raw.empty and "CLOSE" in raw.columns else None
        print(_report(fred_df) if fred_df is not None else "no data")

        # For BUND: layer ECB daily (2004–present) on top of FRED monthly to close the lag gap
        if cfg["fred_bond"] == "BUND":
            print(f"  [ecb] Bund daily yield → price ... ", end="", flush=True)
            ecb_raw = fetch_ecb_bund_price(start=start)
            if not ecb_raw.empty and "CLOSE" in ecb_raw.columns:
                ecb_df = ecb_raw[["DATETIME", "CLOSE"]]
                print(_report(ecb_df))
                if fred_df is not None:
                    fred_df = splice_series(early=fred_df, late=ecb_df)
                    print(f"  [splice fred+ecb] {_report(fred_df)}")
                else:
                    fred_df = ecb_df
            else:
                print("no data")

        if fred_df is not None:
            if best is None:
                best = fred_df
            else:
                best = splice_series(early=fred_df, late=best)
                print(f"  [splice] combined: {_report(best)}")


    # 3b. FRED — commodity spot / monthly price (splice with futures at overlap)
    if cfg.get("fred_price"):
        print(f"  [fred] price ({cfg['fred_price']}) ... ", end="", flush=True)
        raw = fetch_fred_price(cfg["fred_price"], start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            fred_df = raw[["DATETIME", "CLOSE"]]
            print(_report(fred_df))
            if best is None:
                best = fred_df
            else:
                best = splice_series(early=fred_df, late=best)
                print(f"  [splice] combined: {_report(best)}")
        else:
            print("no data")

    # 3c. FRED — FX spot rates (daily from 1971, splice with yfinance / cTrader)
    if cfg.get("fred_fx"):
        print(f"  [fred] FX ({cfg['fred_fx']}) ... ", end="", flush=True)
        raw = fetch_fred_fx(cfg["fred_fx"], start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            fred_df = raw[["DATETIME", "CLOSE"]]
            print(_report(fred_df))
            if best is None:
                best = fred_df
            else:
                best = splice_series(early=fred_df, late=best)
                print(f"  [splice] combined: {_report(best)}")
        else:
            print("no data")

    # 3d. FRED — EURGBP derived from EURUSD/GBPUSD (from 1999, splice with yfinance)
    if cfg.get("fred_eurgbp"):
        print(f"  [fred] EURGBP (derived) ... ", end="", flush=True)
        raw = fetch_fred_eurgbp(start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            fred_df = raw[["DATETIME", "CLOSE"]]
            print(_report(fred_df))
            if best is None:
                best = fred_df
            else:
                best = splice_series(early=fred_df, late=best)
                print(f"  [splice] combined: {_report(best)}")
        else:
            print("no data")

    # 3e. Datahub.io — gold monthly from 1833, splice with GC=F at 2000
    if cfg.get("datahub_gold"):
        print(f"  [datahub] gold monthly ... ", end="", flush=True)
        raw = fetch_datahub_gold(start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            dh_df = raw[["DATETIME", "CLOSE"]]
            print(_report(dh_df))
            if best is None:
                best = dh_df
            else:
                best = splice_series(early=dh_df, late=best)
                print(f"  [splice] combined: {_report(best)}")
        else:
            print("no data")

    # 3f. eco3min.fr — silver monthly from 1960, splice with SI=F at 2000
    if cfg.get("eco3min_silver"):
        print(f"  [eco3min] silver monthly ... ", end="", flush=True)
        raw = fetch_eco3min_silver(start=start)
        if not raw.empty and "CLOSE" in raw.columns:
            eco_df = raw[["DATETIME", "CLOSE"]]
            print(_report(eco_df))
            if best is None:
                best = eco_df
            else:
                best = splice_series(early=eco_df, late=best)
                print(f"  [splice] combined: {_report(best)}")
        else:
            print("no data")

    return best


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

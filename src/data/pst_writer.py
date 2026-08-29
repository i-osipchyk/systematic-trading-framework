"""
Writes price data in pysystemtrade's CSV format.

For CFDs there is no futures roll, so:
  - adjusted_prices = actual close prices (no roll adjustment needed)
  - multiple_prices: PRICE = CARRY = FORWARD (same series), with a fixed
    dummy contract date (29991200) since CFDs don't expire

Data is stored under data/futures/<timeframe>/ so D1 and H4 bars stay
in separate directories and never overwrite each other.

pysystemtrade date format: %Y-%m-%d %H:%M:%S
"""

from pathlib import Path

import pandas as pd

PST_DATE_FMT = "%Y-%m-%d %H:%M:%S"
DUMMY_CONTRACT = "29991200"

DATA_ROOT = Path(__file__).parents[2] / "data" / "futures"


def adjusted_prices_dir(timeframe: str | None = None) -> Path:
    """Return (and create) the adjusted-prices directory for the given timeframe.

    If timeframe is None, reads the active config's timeframe.
    """
    if timeframe is None:
        from src.backtest.config import load_timeframe
        timeframe = load_timeframe()
    d = DATA_ROOT / timeframe / "adjusted_prices_csv"
    d.mkdir(parents=True, exist_ok=True)
    return d


def multiple_prices_dir(timeframe: str | None = None) -> Path:
    """Return (and create) the multiple-prices directory for the given timeframe."""
    if timeframe is None:
        from src.backtest.config import load_timeframe
        timeframe = load_timeframe()
    d = DATA_ROOT / timeframe / "multiple_prices_csv"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_adjusted_prices(df: pd.DataFrame, instrument_code: str, timeframe: str | None = None) -> Path:
    """Write close prices as pysystemtrade adjusted prices CSV.

    Merges with any existing file so that incremental fetches never overwrite
    historical data. New bars take precedence over existing rows on the same date.

    Args:
        df: DataFrame with DATETIME and CLOSE columns.
        instrument_code: Framework instrument code (e.g. 'BTC').
        timeframe: Bar period ('D1', 'H4', etc.). Defaults to active config.

    Returns:
        Path to written file.
    """
    new_series = df.set_index("DATETIME")["CLOSE"].rename("price")
    new_series.index = pd.to_datetime(new_series.index)
    new_series.index.name = "DATETIME"

    out_path = adjusted_prices_dir(timeframe) / f"{instrument_code}.csv"
    if out_path.exists():
        existing = pd.read_csv(out_path, index_col="DATETIME", parse_dates=True)["price"]
        # Combine: existing first, new bars override on overlap, sort by date
        merged = pd.concat([existing[~existing.index.isin(new_series.index)], new_series])
        merged = merged.sort_index()
        merged.index.name = "DATETIME"
        merged.to_csv(out_path, date_format=PST_DATE_FMT, header=True)
    else:
        new_series.to_csv(out_path, date_format=PST_DATE_FMT, header=True)
    return out_path


def write_multiple_prices(df: pd.DataFrame, instrument_code: str, timeframe: str | None = None) -> Path:
    """Write multiple-prices CSV (needed for pysystemtrade's full data model).

    Merges with any existing file so incremental fetches never overwrite
    historical data. New bars take precedence over existing rows on the same date.

    For CFDs: PRICE = CARRY = FORWARD = CLOSE. All contract columns use the
    dummy date 29991200 since CFDs have no expiry.
    """
    prices = df.set_index("DATETIME")["CLOSE"]
    prices.index = pd.to_datetime(prices.index)

    new_out = pd.DataFrame(index=prices.index)
    new_out.index.name = "DATETIME"
    new_out["PRICE"] = prices
    new_out["CARRY"] = prices
    new_out["FORWARD"] = prices
    new_out["PRICE_CONTRACT"] = DUMMY_CONTRACT
    new_out["CARRY_CONTRACT"] = DUMMY_CONTRACT
    new_out["FORWARD_CONTRACT"] = DUMMY_CONTRACT

    out_path = multiple_prices_dir(timeframe) / f"{instrument_code}.csv"
    if out_path.exists():
        existing = pd.read_csv(out_path, index_col="DATETIME", parse_dates=True)
        merged = pd.concat([existing[~existing.index.isin(new_out.index)], new_out])
        merged = merged.sort_index()
        merged.index.name = "DATETIME"
        merged.to_csv(out_path, date_format=PST_DATE_FMT)
    else:
        new_out.to_csv(out_path, date_format=PST_DATE_FMT)
    return out_path


def load_adjusted_prices(instrument_code: str) -> pd.Series:
    """Read adjusted prices for the active config's timeframe.

    Normalises to one bar per weekday (Mon–Fri): removes DST-transition
    duplicate timestamps (broker server time shifts between 21:00 and 22:00 UTC
    on the same calendar date) and weekend sessions that some data sources
    include. Takes the last (most recent) bar for each calendar date.
    """
    path = adjusted_prices_dir() / f"{instrument_code}.csv"
    series = pd.read_csv(path, index_col="DATETIME", parse_dates=True)["price"]
    series.index = pd.to_datetime(series.index)
    # One price per calendar date (last bar wins for DST duplicates), weekdays only
    series = series.groupby(series.index.normalize()).last()
    series = series[series.index.dayofweek < 5]
    return series

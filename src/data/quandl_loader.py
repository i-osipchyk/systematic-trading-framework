"""Download continuous futures from Nasdaq Data Link (formerly Quandl) CHRIS dataset.

CHRIS provides Panama-method adjusted continuous futures going back 30-40 years.
Requires NASDAQ_DATA_LINK_API_KEY in environment (free account at data.nasdaq.com).

Returns data in the same DataFrame format as ctrader_client.fetch_bars():
  columns: DATETIME (str), OPEN, HIGH, LOW, CLOSE, VOLUME
  DATETIME format: '%Y-%m-%d %H:%M:%S'  (22:00:00 suffix)
"""

from __future__ import annotations

import os

import pandas as pd


def fetch_quandl(dataset: str, start: str = "1984-01-01", end: str | None = None) -> pd.DataFrame:
    """Download a CHRIS continuous futures dataset from Nasdaq Data Link.

    Args:
        dataset: Nasdaq Data Link dataset path, e.g. 'CHRIS/CME_CL1'.
        start:   Start date string 'YYYY-MM-DD'.
        end:     End date string (defaults to today).

    Returns:
        DataFrame with columns DATETIME, OPEN, HIGH, LOW, CLOSE, VOLUME.
        Empty DataFrame if unavailable or API key missing.
    """
    try:
        import nasdaqdatalink
    except ImportError:
        print("  [quandl] nasdaq-data-link not installed; skipping.")
        return pd.DataFrame()

    api_key = os.getenv("NASDAQ_DATA_LINK_API_KEY")
    if not api_key:
        print("  [quandl] NASDAQ_DATA_LINK_API_KEY not set; skipping Quandl fetch.")
        return pd.DataFrame()

    nasdaqdatalink.ApiConfig.api_key = api_key

    kwargs = {"start_date": start}
    if end:
        kwargs["end_date"] = end

    try:
        raw = nasdaqdatalink.get(dataset, **kwargs)
    except Exception as e:
        print(f"  [quandl] ERROR fetching {dataset}: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    # CHRIS column names vary by exchange.  Try several conventions.
    close_candidates = ["Last", "Settle", "Close", "Price"]
    close_col = next((c for c in close_candidates if c in raw.columns), None)
    if close_col is None:
        print(f"  [quandl] Cannot find close column in {dataset}. Columns: {list(raw.columns)}")
        return pd.DataFrame()

    rename = {
        "Open": "OPEN",
        "High": "HIGH",
        "Low": "LOW",
        close_col: "CLOSE",
        "Volume": "VOLUME",
        "Turnover": "VOLUME",
    }
    df = raw.rename(columns=rename)
    keep = [c for c in ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"] if c in df.columns]
    df = df[keep].dropna(subset=["CLOSE"]).copy()

    if df.empty:
        return pd.DataFrame()

    df.index = pd.to_datetime(df.index)
    df.index = df.index.normalize() + pd.Timedelta(hours=22)
    df.index.name = "DATETIME"

    df = df[df.index >= pd.Timestamp(start)]
    return df.reset_index()

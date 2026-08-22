"""Download daily OHLCV data from Yahoo Finance.

Returns data in the same DataFrame format as ctrader_client.fetch_bars():
  columns: DATETIME (str), OPEN, HIGH, LOW, CLOSE, VOLUME
  DATETIME format: '%Y-%m-%d %H:%M:%S'  (22:00:00 suffix, matching cTrader)
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def fetch_yfinance(ticker: str, start: str = "1984-01-01", end: str | None = None) -> pd.DataFrame:
    """Download daily bars from Yahoo Finance.

    Args:
        ticker: Yahoo Finance ticker symbol (e.g. '^GSPC', 'GC=F', 'AUDUSD=X').
        start:  Start date string 'YYYY-MM-DD'.
        end:    End date string (defaults to today).

    Returns:
        DataFrame with columns DATETIME, OPEN, HIGH, LOW, CLOSE, VOLUME.
        Empty DataFrame if the ticker is unavailable or returns no data.
    """
    try:
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, timeout=30)
    except Exception as e:
        print(f"  [yfinance] ERROR fetching {ticker}: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    # yfinance ≥0.2 returns MultiIndex columns when downloading a single ticker
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

    col_map = {"Open": "OPEN", "High": "HIGH", "Low": "LOW", "Close": "CLOSE", "Volume": "VOLUME"}
    df = raw.rename(columns=col_map)

    keep = [c for c in ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"] if c in df.columns]
    df = df[keep].dropna(subset=["CLOSE"]).copy()

    if df.empty:
        return pd.DataFrame()

    df.index = pd.to_datetime(df.index)
    # Normalise to 22:00:00 suffix to match cTrader convention
    df.index = df.index.normalize() + pd.Timedelta(hours=22)
    df.index.name = "DATETIME"

    return df.reset_index()

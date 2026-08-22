"""Download historical data from FRED (Federal Reserve Economic Data).

Used for two purposes:
  1. Bond price proxies: convert 10yr/30yr Treasury yields to approximate
     futures prices using the standard bond pricing formula (6% coupon,
     matching CME Treasury futures notional).
  2. Commodity spot prices: WTI crude (back to 1986), natural gas (back to 1997).

No API key required. FRED data is free and public.

Returns data in the same format as yf_loader and quandl_loader:
  columns: DATETIME, OPEN, HIGH, LOW, CLOSE, VOLUME
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import requests

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# FRED series IDs
SERIES = {
    "US10YR": "DGS10",       # 10-year Treasury yield, daily, from 1962
    "US30YR": "DGS30",       # 30-year Treasury yield, daily, from 1977
    "BUND_YLD": "IRLTLT01DEM156N",  # German long-term yield (monthly, from 1960)
    "SpotCrude": "DCOILWTICO",  # WTI spot price, daily, from 1986
    "NatGas": "DHHNGSP",     # Henry Hub spot, daily, from 1997
}

# Notional coupon for Treasury futures pricing (CME standard)
_TREASURY_COUPON = 6.0  # per cent per annum


def _fetch_fred(series_id: str) -> pd.Series:
    """Fetch a FRED series. Returns a daily Series with float values."""
    r = requests.get(FRED_BASE, params={"id": series_id}, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df[df["value"].astype(str) != "."]
    df["value"] = df["value"].astype(float)
    return df["value"].sort_index()


def _yield_to_price(yield_pct: float | np.ndarray, maturity: float, coupon: float = _TREASURY_COUPON) -> float | np.ndarray:
    """Convert a par yield (%) to a bond price (per $100 face value).

    Assumes semi-annual coupons, fixed maturity, 6% coupon (CME notional).
    """
    n = int(maturity * 2)         # number of semi-annual periods
    y = yield_pct / 100 / 2      # semi-annual yield
    c = coupon / 2                # semi-annual coupon
    # Avoid division by zero for zero yields
    safe_y = np.where(np.asarray(y) == 0, 1e-10, y) if isinstance(y, np.ndarray) else (y or 1e-10)
    price = c * (1 - (1 + safe_y) ** -n) / safe_y + 100 * (1 + safe_y) ** -n
    return price


def _to_ohlcv(series: pd.Series) -> pd.DataFrame:
    """Wrap a price series into the standard OHLCV DataFrame format."""
    df = pd.DataFrame(index=series.index)
    df.index = df.index.normalize() + pd.Timedelta(hours=22)
    df.index.name = "DATETIME"
    df["OPEN"] = series.values
    df["HIGH"] = series.values
    df["LOW"] = series.values
    df["CLOSE"] = series.values
    df["VOLUME"] = 0
    return df.dropna(subset=["CLOSE"]).reset_index()


def fetch_bond_price(instrument: str, start: str = "1960-01-01") -> pd.DataFrame:
    """Fetch Treasury or Bund bond price proxy from FRED yield data.

    Args:
        instrument: 'US10YR', 'US30YR', or 'BUND'.
        start: Start date string 'YYYY-MM-DD'.

    Returns:
        DataFrame with DATETIME, OPEN, HIGH, LOW, CLOSE, VOLUME.
        CLOSE is an approximate futures price derived from the yield.
    """
    maturity_map = {"US10YR": 10.0, "US30YR": 30.0, "BUND": 10.0}
    series_map = {"US10YR": "DGS10", "US30YR": "DGS30", "BUND": "IRLTLT01DEM156N"}

    if instrument not in maturity_map:
        raise ValueError(f"Unknown bond instrument: {instrument}. Choose from {list(maturity_map)}")

    fred_id = series_map[instrument]
    maturity = maturity_map[instrument]

    try:
        yields = _fetch_fred(fred_id)
    except Exception as e:
        print(f"  [fred] ERROR fetching {fred_id}: {e}")
        return pd.DataFrame()

    yields = yields[yields.index >= pd.Timestamp(start)]
    if yields.empty:
        return pd.DataFrame()

    # If data is monthly (gap between consecutive rows > 20 days), forward-fill to business days.
    # This is common for European yield data on FRED. Trend-following strategies are robust to
    # this since they operate on multi-week to multi-month windows.
    gaps = yields.index.to_series().diff().dt.days.iloc[1:]
    is_monthly = (gaps.median() > 20)
    if is_monthly:
        bday_idx = pd.bdate_range(yields.index[0], yields.index[-1])
        yields = yields.reindex(bday_idx).ffill()

    prices = pd.Series(
        _yield_to_price(yields.values, maturity),
        index=yields.index,
        name="price",
    )

    return _to_ohlcv(prices)


def fetch_fred_price(instrument: str, start: str = "1984-01-01") -> pd.DataFrame:
    """Fetch a commodity spot price series from FRED.

    Args:
        instrument: 'SpotCrude' or 'NatGas'.
        start: Start date string 'YYYY-MM-DD'.

    Returns:
        DataFrame with DATETIME, OPEN, HIGH, LOW, CLOSE, VOLUME.
    """
    if instrument not in SERIES:
        raise ValueError(f"No FRED series for {instrument}. Available: {list(SERIES)}")

    fred_id = SERIES[instrument]
    try:
        series = _fetch_fred(fred_id)
    except Exception as e:
        print(f"  [fred] ERROR fetching {fred_id}: {e}")
        return pd.DataFrame()

    series = series[series.index >= pd.Timestamp(start)]
    if series.empty:
        return pd.DataFrame()

    return _to_ohlcv(series)


def splice_series(early: pd.DataFrame, late: pd.DataFrame) -> pd.DataFrame:
    """Splice two DATETIME/CLOSE DataFrames at their overlap point.

    Uses the ratio at the overlap to scale the early series so the spliced
    result has no jump at the junction (same approach as Panama method for rolls).

    Args:
        early: DataFrame with DATETIME, CLOSE — the older, proxy series.
        late:  DataFrame with DATETIME, CLOSE — the newer, actual series.

    Returns:
        Combined DataFrame with DATETIME, CLOSE (early scaled to match late).
    """
    if early.empty:
        return late
    if late.empty:
        return early

    early = early.copy()
    late = late.copy()
    for df in (early, late):
        df["DATETIME"] = pd.to_datetime(df["DATETIME"])

    overlap_dates = set(early["DATETIME"]) & set(late["DATETIME"])
    if not overlap_dates:
        # No overlap — just concatenate; level discontinuity will exist
        combined = pd.concat([early[["DATETIME", "CLOSE"]], late[["DATETIME", "CLOSE"]]], ignore_index=True)
        combined = combined.drop_duplicates(subset="DATETIME", keep="last").sort_values("DATETIME")
        return combined.reset_index(drop=True)

    # Scale early to match late at the start of the overlap
    overlap_start = min(overlap_dates)
    early_val = early.loc[early["DATETIME"] == overlap_start, "CLOSE"].iloc[0]
    late_val = late.loc[late["DATETIME"] == overlap_start, "CLOSE"].iloc[0]
    scale = late_val / early_val if early_val != 0 else 1.0

    early_only = early[early["DATETIME"] < pd.Timestamp(overlap_start)].copy()
    early_only["CLOSE"] *= scale

    combined = pd.concat([early_only[["DATETIME", "CLOSE"]], late[["DATETIME", "CLOSE"]]], ignore_index=True)
    combined = combined.drop_duplicates(subset="DATETIME", keep="last").sort_values("DATETIME")
    return combined.reset_index(drop=True)

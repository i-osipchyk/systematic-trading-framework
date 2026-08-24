"""Download historical data from FRED (Federal Reserve Economic Data) and Datahub.io.

Sources:
  FRED     — bond price proxies (yield→price), FX spot rates, commodity spot prices
  ECB SDW  — daily German 10Y yields, no API key, no publication lag
  Datahub.io — gold monthly from 1833, no API key needed

All data is free and public (no API key required).

Returns data in the same format as yf_loader / quandl_loader:
  columns: DATETIME, OPEN, HIGH, LOW, CLOSE, VOLUME
  DATETIME uses 22:00:00 suffix to match cTrader convention
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import requests

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_TIMEOUT = 30

# ── FRED series IDs ──────────────────────────────────────────────────────────

# Bond yields (daily)
_YIELD_SERIES = {
    "US2YR":  ("DGS2",              2.0),    # 2yr T-Note yield, from 1976
    "US5YR":  ("DGS5",              5.0),    # 5yr T-Note yield, from 1962
    "US10YR": ("DGS10",             10.0),   # 10yr T-Note yield, from 1962
    "US30YR": ("DGS30",             30.0),   # 30yr T-Bond yield, from 1977
    "BUND":   ("IRLTLT01DEM156N",   10.0),   # German long-term, monthly from 1960
}

# FX rates (daily, from 1971)
# Each entry: (series_id, invert) — invert=True means series is CCY/USD, need 1/x
_FX_SERIES = {
    "AUDUSD": ("DEXUSAL", False),  # USD per AUD  → AUDUSD direct
    "USDCAD": ("DEXCAUS", False),  # CAD per USD  → USDCAD direct
    "USDJPY": ("DEXJPUS", False),  # JPY per USD  → USDJPY direct
    "GBPUSD": ("DEXUSUK", False),  # USD per GBP  → GBPUSD direct
    "EURUSD": ("DEXUSEU", False),  # USD per EUR  → EURUSD direct, from 1999
}

# Commodity spot prices
# (series_id, is_monthly)
_COMMODITY_SERIES: dict[str, tuple[str, bool]] = {
    "SpotCrude": ("DCOILWTICO",   False),  # WTI daily, from 1986
    "NatGas":    ("DHHNGSP",      False),  # Henry Hub daily, from 1997
    # Monthly commodity prices (forward-filled to business days)
    "COPPER":    ("PCOPPUSDM",    True),   # LME copper USD/metric ton, from 1992
    "Wheat":     ("PWHEAMTUSDM",  True),   # US HRW wheat USD/metric ton, from 1992
    "Corn":      ("PMAIZMTUSDM",  True),   # US corn USD/metric ton, from 1992
    "Soybeans":  ("PSOYBUSDM",    True),   # US soybeans USD/metric ton, from 1992
    "Coffee":    ("PCOFFOTMUSDM", True),   # ICO coffee cents/lb, from 1992
    "Sugar":     ("PSUGAISAUSDM", True),   # ISA sugar cents/lb, from 1992
    "Cotton":    ("PCOTTINDUSDM", True),   # Cotlook A-index cents/lb, from 1992
    "Cocoa":     ("PCOCOUSDM",    True),   # ICCO cocoa USD/metric ton, from 1992
}

# Notional coupon for Treasury futures pricing (CME standard)
_TREASURY_COUPON = 6.0  # per cent per annum


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_fred(series_id: str) -> pd.Series:
    """Fetch a FRED series. Returns a Series indexed by date."""
    r = requests.get(FRED_BASE, params={"id": series_id}, timeout=_TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df[df["value"].astype(str) != "."]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    return df["value"].sort_index()


def _to_daily(series: pd.Series) -> pd.Series:
    """Forward-fill a potentially sub-daily or monthly series to business days."""
    gaps = series.index.to_series().diff().dt.days.iloc[1:]
    if gaps.empty or gaps.median() <= 5:
        return series  # already daily-ish
    bday_idx = pd.bdate_range(series.index[0], series.index[-1])
    return series.reindex(bday_idx).ffill()


def _to_ohlcv(series: pd.Series, start: str | None = None) -> pd.DataFrame:
    """Wrap a price series into the standard OHLCV DataFrame format."""
    if start:
        series = series[series.index >= pd.Timestamp(start)]
    if series.empty:
        return pd.DataFrame()
    df = pd.DataFrame(index=series.index)
    df.index = df.index.normalize() + pd.Timedelta(hours=22)
    df.index.name = "DATETIME"
    df["OPEN"] = series.values
    df["HIGH"] = series.values
    df["LOW"] = series.values
    df["CLOSE"] = series.values
    df["VOLUME"] = 0
    return df.dropna(subset=["CLOSE"]).reset_index()


def _yield_to_price(yield_pct: np.ndarray, maturity: float, coupon: float = _TREASURY_COUPON) -> np.ndarray:
    """Convert par yields (%) to bond prices (per $100 face, semi-annual coupons)."""
    n = int(maturity * 2)
    y = np.asarray(yield_pct, dtype=float) / 100 / 2
    c = coupon / 2
    safe_y = np.where(y == 0, 1e-10, y)
    return c * (1 - (1 + safe_y) ** -n) / safe_y + 100 * (1 + safe_y) ** -n


# ECB SDW YC dataset — daily euro area AAA 10Y spot rate, no API key, current through prior business day
# Covers 2004-09-06 to present; spliced with FRED monthly (1960) for pre-2004 history
_ECB_YC_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"


def _fetch_ecb_bund_yields() -> pd.Series:
    """Fetch daily euro area AAA 10Y spot rate from ECB YC dataset."""
    r = requests.get(_ECB_YC_URL, params={"format": "csvdata"}, timeout=_TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"], errors="coerce")
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    df = df.dropna(subset=["TIME_PERIOD", "OBS_VALUE"]).set_index("TIME_PERIOD").sort_index()
    return df["OBS_VALUE"]


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_bond_price(instrument: str, start: str = "1960-01-01") -> pd.DataFrame:
    """Fetch Treasury or Bund bond price proxy from FRED yield data.

    Converts daily/monthly yield series to approximate futures prices using
    the standard bond pricing formula (6% notional coupon, CME convention).
    Monthly data (BUND) is forward-filled to business days.
    """
    if instrument not in _YIELD_SERIES:
        raise ValueError(f"Unknown bond: {instrument}. Choose from {list(_YIELD_SERIES)}")

    fred_id, maturity = _YIELD_SERIES[instrument]
    try:
        yields = _fetch_fred(fred_id)
    except Exception as e:
        print(f"  [fred] ERROR fetching {fred_id}: {e}")
        return pd.DataFrame()

    yields = _to_daily(yields)
    prices = pd.Series(_yield_to_price(yields.values, maturity), index=yields.index)
    return _to_ohlcv(prices, start=start)


def fetch_ecb_bund_price(start: str = "1984-01-01") -> pd.DataFrame:
    """Fetch euro area AAA 10Y Bund price proxy from ECB YC dataset.

    ECB publishes daily with no material lag (unlike FRED's OECD monthly series).
    Covers from 2004-09-06 to present. Use splice_series with fetch_bond_price
    (FRED monthly, from 1960) to get the full history back to 1984.
    """
    try:
        yields = _fetch_ecb_bund_yields()
    except Exception as e:
        print(f"  [ecb] ERROR fetching Bund yields: {e}")
        return pd.DataFrame()

    prices = pd.Series(_yield_to_price(yields.values, 10.0), index=yields.index)
    return _to_ohlcv(prices.dropna(), start=start)


def fetch_fred_fx(instrument: str, start: str = "1984-01-01") -> pd.DataFrame:
    """Fetch daily FX spot rates from FRED.

    Available instruments: AUDUSD (1971), USDCAD (1971), USDJPY (1971), GBPUSD (1971), EURUSD (1999).
    """
    if instrument not in _FX_SERIES:
        raise ValueError(f"No FRED FX series for {instrument}. Available: {list(_FX_SERIES)}")

    fred_id, invert = _FX_SERIES[instrument]
    try:
        series = _fetch_fred(fred_id)
    except Exception as e:
        print(f"  [fred] ERROR fetching {fred_id}: {e}")
        return pd.DataFrame()

    if invert:
        series = 1.0 / series

    return _to_ohlcv(series, start=start)


def fetch_fred_price(instrument: str, start: str = "1984-01-01") -> pd.DataFrame:
    """Fetch commodity spot prices from FRED.

    Daily series: SpotCrude (1986), NatGas (1997).
    Monthly series forward-filled to daily: COPPER, Wheat, Corn, Soybeans,
    Coffee, Sugar, Cotton, Cocoa (all from 1992).
    """
    if instrument not in _COMMODITY_SERIES:
        raise ValueError(f"No FRED price series for {instrument}. Available: {list(_COMMODITY_SERIES)}")

    fred_id, _ = _COMMODITY_SERIES[instrument]
    try:
        series = _fetch_fred(fred_id)
    except Exception as e:
        print(f"  [fred] ERROR fetching {fred_id}: {e}")
        return pd.DataFrame()

    series = _to_daily(series)
    return _to_ohlcv(series, start=start)


def _fetch_monthly_csv(url: str, label: str, start: str = "1984-01-01") -> pd.DataFrame:
    """Generic helper: fetch a two-column (date, price) monthly CSV and return OHLCV."""
    try:
        r = requests.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return pd.DataFrame()

    df = pd.read_csv(io.StringIO(r.text))
    df = df.iloc[:, :2]               # keep first two columns regardless of name
    df.columns = ["date", "price"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna()
    series = df.set_index("date")["price"].sort_index()
    series = _to_daily(series)
    return _to_ohlcv(series, start=start)


def fetch_datahub_gold(start: str = "1984-01-01") -> pd.DataFrame:
    """Fetch monthly gold prices from datahub.io (LBMA fixing, from 1833)."""
    return _fetch_monthly_csv(
        "https://datahub.io/core/gold-prices/r/monthly.csv",
        label="datahub/gold",
        start=start,
    )


def fetch_fred_eurgbp(start: str = "1984-01-01") -> pd.DataFrame:
    """Compute EURGBP = EURUSD / GBPUSD from FRED daily series.

    DEXUSEU (USD per EUR) and DEXUSUK (USD per GBP) both available from 1999-01-04.
    Aligned on their common dates before division.
    """
    try:
        eurusd = _fetch_fred("DEXUSEU")
        gbpusd = _fetch_fred("DEXUSUK")
    except Exception as e:
        print(f"  [fred] ERROR fetching EURGBP constituents: {e}")
        return pd.DataFrame()

    common = eurusd.index.intersection(gbpusd.index)
    eurgbp = eurusd.loc[common] / gbpusd.loc[common]
    return _to_ohlcv(eurgbp.dropna(), start=start)


def fetch_eco3min_silver(start: str = "1984-01-01") -> pd.DataFrame:
    """Fetch monthly silver prices from eco3min.fr (World Bank Pink Sheet, from 1960).

    Monthly data is forward-filled to business days then spliced with SI=F at 2000.
    """
    return _fetch_monthly_csv(
        "https://eco3min.fr/dataset/silver-price.csv",
        label="eco3min/silver",
        start=start,
    )


def splice_series(early: pd.DataFrame, late: pd.DataFrame) -> pd.DataFrame:
    """Splice two DATETIME/CLOSE DataFrames, scaling the early series to eliminate
    price-level discontinuity at the junction (Panama-style ratio adjustment).

    Args:
        early: older series (proxy / spot / yield-derived)
        late:  newer series (actual futures prices or higher-quality data)

    Returns:
        Combined DATETIME/CLOSE DataFrame covering the full range of both inputs.
    """
    if early is None or early.empty:
        return late
    if late is None or late.empty:
        return early

    early = early.copy()
    late = late.copy()
    for df in (early, late):
        df["DATETIME"] = pd.to_datetime(df["DATETIME"])

    # Find overlap window — use first 30 days of overlap to get a stable scale factor
    early_dates = set(early["DATETIME"])
    late_dates = set(late["DATETIME"])
    overlap = sorted(early_dates & late_dates)

    if not overlap:
        combined = pd.concat([early[["DATETIME", "CLOSE"]], late[["DATETIME", "CLOSE"]]])
        combined = combined.drop_duplicates("DATETIME", keep="last").sort_values("DATETIME")
        return combined.reset_index(drop=True)

    sample = overlap[:min(30, len(overlap))]
    early_mean = early.loc[early["DATETIME"].isin(sample), "CLOSE"].mean()
    late_mean = late.loc[late["DATETIME"].isin(sample), "CLOSE"].mean()
    scale = late_mean / early_mean if early_mean != 0 else 1.0

    early_only = early[early["DATETIME"] < pd.Timestamp(overlap[0])].copy()
    early_only["CLOSE"] *= scale

    combined = pd.concat([early_only[["DATETIME", "CLOSE"]], late[["DATETIME", "CLOSE"]]])
    combined = combined.drop_duplicates("DATETIME", keep="last").sort_values("DATETIME")
    return combined.reset_index(drop=True)

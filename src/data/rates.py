"""
Central bank policy rates, bond yields, and equity dividend yields.

All three datasets are fetched from FRED on first use and cached to
data/rates/ as CSV files. Subsequent calls within the same process use
an in-memory cache; across processes the CSV is read from disk.

Public interface (unchanged for FX carry compatibility):
    load_policy_rates(index)          -> pd.DataFrame  columns: USD EUR GBP JPY AUD CAD
    load_bond_yields(index)           -> pd.DataFrame  columns: US2YR US5YR US10YR US30YR BUND
    load_equity_dividend_yields(index)-> pd.DataFrame  columns: US500 NAS100
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# ── FRED series identifiers ───────────────────────────────────────────────────

_POLICY_RATE_SERIES: dict[str, str] = {
    "USD": "FEDFUNDS",           # Fed funds effective rate, monthly from 1954
    "GBP": "IRSTCI01GBM156N",   # UK call/interbank rate, monthly from 1978
    "JPY": "IRSTCB01JPM156N",   # Japan central bank rate, monthly from 1960
    "AUD": "IR3TBB01AUM156N",   # Australia 3m T-bill, monthly from 1968
    "CAD": "IRSTCB01CAM156N",   # Canada central bank rate, monthly from 1960
    "EUR": "IRSTCI01DEM156N",   # Germany/EUR-zone call rate, monthly from 1960 (pre+post euro)
}

_BOND_YIELD_SERIES: dict[str, str] = {
    "US2YR":  "DGS2",            # daily from 1976
    "US5YR":  "DGS5",            # daily from 1962
    "US10YR": "DGS10",           # daily from 1962
    "US30YR": "DGS30",           # daily from 1977
    "BUND":   "IRLTLT01DEM156N", # German long-term yield, monthly from 1960
}

# S&P 500 dividend yield computed from Shiller data (Yale)
# D (annual dividends/share) / P (price) * 100 → yield as %
_SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"

_CACHE_DIR = Path(__file__).parents[2] / "data" / "rates"

# ── In-process caches ─────────────────────────────────────────────────────────

_rates_cache: pd.DataFrame | None = None
_bond_yield_cache: pd.DataFrame | None = None
_div_yield_cache: pd.DataFrame | None = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_and_daily(series_id: str) -> pd.Series:
    """Fetch a FRED series and forward-fill to daily frequency."""
    from src.data.fred_loader import _fetch_fred, _to_daily as _ffill
    raw = _fetch_fred(series_id)
    return _ffill(raw)


def _to_daily(series: pd.Series) -> pd.Series:
    """Forward-fill a monthly/irregular series to business days."""
    from src.data.fred_loader import _to_daily as _ffill
    return _ffill(series)


def _load_or_fetch(
    cache_file: str,
    series_map: dict[str, str],
    label: str,
) -> pd.DataFrame:
    """Load from CSV cache or fetch from FRED; return daily DataFrame."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / cache_file

    if path.exists():
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            return df
        except Exception as e:
            print(f"  [rates] WARNING: could not read cache {path}: {e}")

    # Fetch from FRED
    print(f"  [rates] Fetching {label} from FRED...")
    columns: dict[str, pd.Series] = {}
    for col, series_id in series_map.items():
        try:
            columns[col] = _fetch_and_daily(series_id)
        except Exception as e:
            print(f"  [rates] WARNING: failed to fetch {series_id} for {col}: {e}")

    if not columns:
        print(f"  [rates] WARNING: no {label} data fetched; returning zeros.")
        return pd.DataFrame()

    df = pd.DataFrame(columns).sort_index()

    try:
        df.to_csv(path)
    except Exception as e:
        print(f"  [rates] WARNING: could not write cache {path}: {e}")

    return df


def _align(df: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Reindex and forward-fill a daily DataFrame to match *index*."""
    if df.empty:
        return pd.DataFrame(0.0, index=index, columns=df.columns if not df.empty else [])
    full_idx = df.index.union(index).sort_values()
    return df.reindex(full_idx).ffill().reindex(index).fillna(0.0)


# ── Public API ────────────────────────────────────────────────────────────────

def load_policy_rates(index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Return a DataFrame of daily central bank policy rates (annualised %).

    Columns: USD, EUR, GBP, JPY, AUD, CAD.
    If *index* is provided the result is reindexed and forward-filled to match it.
    Falls back to zeros on fetch failure so carry returns a neutral signal.
    """
    global _rates_cache
    if _rates_cache is None:
        _rates_cache = _load_or_fetch(
            "policy_rates.csv", _POLICY_RATE_SERIES, "policy rates"
        )

    if index is None:
        return _rates_cache

    if _rates_cache.empty:
        return pd.DataFrame(0.0, index=index,
                            columns=list(_POLICY_RATE_SERIES.keys()))

    return _align(_rates_cache, index)


def load_bond_yields(index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Return a DataFrame of daily government bond yields (annualised %).

    Columns: US2YR, US5YR, US10YR, US30YR, BUND.
    Forward-filled from source frequency (daily for US, monthly for BUND).
    """
    global _bond_yield_cache
    if _bond_yield_cache is None:
        _bond_yield_cache = _load_or_fetch(
            "bond_yields.csv", _BOND_YIELD_SERIES, "bond yields"
        )

    if index is None:
        return _bond_yield_cache

    if _bond_yield_cache.empty:
        return pd.DataFrame(0.0, index=index,
                            columns=list(_BOND_YIELD_SERIES.keys()))

    return _align(_bond_yield_cache, index)


def _fetch_shiller_div_yield() -> pd.Series:
    """Fetch S&P 500 dividend yield from Shiller's Yale dataset.

    Computes annual dividend yield = D / P as a percentage (e.g. 2.0 = 2%).
    Date column is decimal YYYY.MM; returned as a monthly DatetimeIndex Series.
    """
    import io
    import requests
    r = requests.get(_SHILLER_URL, timeout=30)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="Data", header=7)
    df = df[["Date", "P", "D"]].dropna(subset=["Date", "P", "D"])
    df = df[pd.to_numeric(df["Date"], errors="coerce").notna()]
    df["Date"] = pd.to_numeric(df["Date"])
    df["year"] = df["Date"].astype(int)
    df["month"] = (df["Date"] % 1 * 100).round().astype(int).clip(1, 12)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)
    )
    df["P"] = pd.to_numeric(df["P"], errors="coerce")
    df["D"] = pd.to_numeric(df["D"], errors="coerce")
    df = df.dropna(subset=["P", "D"])
    df["div_yield"] = (df["D"] / df["P"] * 100).clip(0, 20)
    return df.set_index("date")["div_yield"].sort_index()


def load_equity_dividend_yields(index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Return a DataFrame of daily equity dividend yields (annualised %).

    Columns: US500, NAS100 (both sourced from Shiller's S&P 500 dataset, D/P).
    Monthly data forward-filled to daily.
    """
    global _div_yield_cache
    if _div_yield_cache is None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / "equity_div_yields.csv"

        if path.exists():
            try:
                _div_yield_cache = pd.read_csv(path, index_col=0, parse_dates=True)
            except Exception as e:
                print(f"  [rates] WARNING: could not read cache {path}: {e}")

        if _div_yield_cache is None or _div_yield_cache.empty:
            print("  [rates] Fetching S&P 500 dividend yield from Shiller/Yale...")
            try:
                sp500_div = _fetch_shiller_div_yield()
                sp500_div = _to_daily(sp500_div)
                _div_yield_cache = pd.DataFrame({"US500": sp500_div, "NAS100": sp500_div})
                _div_yield_cache.to_csv(path)
            except Exception as e:
                print(f"  [rates] WARNING: failed to fetch Shiller dividend yield: {e}")
                _div_yield_cache = pd.DataFrame()

    if index is None:
        return _div_yield_cache if _div_yield_cache is not None else pd.DataFrame()

    if _div_yield_cache is None or _div_yield_cache.empty:
        return pd.DataFrame(0.0, index=index, columns=["US500", "NAS100"])

    return _align(_div_yield_cache, index)


def clear_caches() -> None:
    """Reset in-process caches (useful for testing)."""
    global _rates_cache, _bond_yield_cache, _div_yield_cache
    _rates_cache = None
    _bond_yield_cache = None
    _div_yield_cache = None

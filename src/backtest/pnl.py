import pandas as pd


def gross_pnl(
    positions: pd.Series,
    prices: pd.Series,
    pointsize: float,
) -> pd.Series:
    """Daily gross P&L in instrument native currency.

    Position held at end of day t generates P&L on day t+1's price move.
    """
    return (positions.shift(1) * prices.diff() * pointsize).rename("gross_pnl")


def transaction_costs(
    positions: pd.Series,
    spread_cost: float,
    pointsize: float,
) -> pd.Series:
    """Daily round-trip transaction costs in instrument native currency.

    Charged whenever the position changes. Always non-negative.
    """
    return (positions.diff().abs() * spread_cost * pointsize).rename("costs")


def to_usd(
    pnl_native: pd.Series,
    currency: str,
    eurusd_prices: pd.Series,
    eurgbp_prices: pd.Series,
    usdjpy_prices: pd.Series | None = None,
    usdcad_prices: pd.Series | None = None,
) -> pd.Series:
    """Convert instrument P&L to USD.

    USD  → identity
    EUR  → pnl * EURUSD
    GBP  → pnl * (EURUSD / EURGBP)   (synthetic GBPUSD)
    JPY  → pnl / USDJPY
    CAD  → pnl / USDCAD
    HKD  → pnl / 7.78   (HKD peg since 1983)
    """
    if currency == "USD":
        return pnl_native.rename("pnl_usd")

    if currency == "EUR":
        fx = eurusd_prices.reindex(pnl_native.index, method="ffill")
        return (pnl_native * fx).rename("pnl_usd")

    if currency == "GBP":
        eurusd = eurusd_prices.reindex(pnl_native.index, method="ffill")
        eurgbp = eurgbp_prices.reindex(pnl_native.index, method="ffill")
        gbpusd = eurusd / eurgbp
        return (pnl_native * gbpusd).rename("pnl_usd")

    if currency == "JPY":
        if usdjpy_prices is None:
            raise ValueError("usdjpy_prices required for JPY currency conversion")
        usdjpy = usdjpy_prices.reindex(pnl_native.index, method="ffill")
        return (pnl_native / usdjpy).rename("pnl_usd")

    if currency == "CAD":
        if usdcad_prices is None or usdcad_prices.empty:
            return pnl_native.rename("pnl_usd")
        usdcad = usdcad_prices.reindex(pnl_native.index, method="ffill")
        return (pnl_native / usdcad).rename("pnl_usd")

    if currency == "HKD":
        return (pnl_native / 7.78).rename("pnl_usd")

    raise ValueError(f"Unknown currency: {currency}")

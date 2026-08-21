from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.backtest.config import InstrumentConfig, load_instrument_configs, traded_instruments as _traded
from src.backtest.idm import compute_idm
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import calibrate_fdm, combined_forecast
from src.rules.vol import daily_vol

def _default_instruments() -> list[str]:
    return _traded(load_instrument_configs())


INSTRUMENTS = _default_instruments()


@dataclass
class InstrumentResult:
    code: str
    positions: pd.Series
    gross_pnl_usd: pd.Series
    costs_usd: pd.Series
    net_pnl_usd: pd.Series
    fdm: float


@dataclass
class BacktestResult:
    is_pnl: pd.Series
    oos_pnl: pd.Series
    idm: float
    fdms: dict[str, float]
    instrument_results: dict[str, InstrumentResult]
    split_date: datetime
    capital: float


def _fx_rate_to_usd(
    currency: str,
    eurusd_prices: pd.Series,
    eurgbp_prices: pd.Series,
    index: pd.Index,
    usdjpy_prices: pd.Series | None = None,
) -> pd.Series | float:
    """Return a series (or scalar) that converts 1 native-currency unit → USD."""
    if currency == "USD":
        return 1.0
    if currency == "EUR":
        return eurusd_prices.reindex(index, method="ffill").bfill()
    if currency == "GBP":
        gbpusd = (eurusd_prices / eurgbp_prices).reindex(index, method="ffill").bfill()
        return gbpusd
    if currency == "JPY":
        if usdjpy_prices is None:
            raise ValueError("usdjpy_prices required for JPY currency")
        return (1 / usdjpy_prices).reindex(index, method="ffill").bfill()
    raise ValueError(f"Unknown currency: {currency}")


def run_instrument(
    code: str,
    cfg: InstrumentConfig,
    prices: pd.Series,
    split_date: datetime,
    eurusd_prices: pd.Series,
    eurgbp_prices: pd.Series,
    capital: float = 10_000.0,
    vol_target: float = 0.20,
    idm: float = 1.0,
    fdm: float | None = None,
    usdjpy_prices: pd.Series | None = None,
    ewmac_scalars: dict[tuple[int, int], float] | None = None,
    mr_scalars: dict[int, float] | None = None,
    rule_weights: dict[str, float] | None = None,
) -> InstrumentResult:
    """Run a single-instrument backtest over the full price history.

    FDM is calibrated on IS data if not supplied (pass 1).
    Positions and P&L span the full series; IS/OOS slicing is the caller's job.

    Args:
        ewmac_scalars: Override scalars for EWMAC rules, passed to combined_forecast().
        mr_scalars:    Override scalars for MR rules, passed to combined_forecast().
        rule_weights:  Per-rule combination weights, passed to combined_forecast()
                       and calibrate_fdm().
    """
    is_prices, _ = split_series(prices, split_date)

    # ── FDM calibration (IS only, pass 1) ────────────────────────────────────
    if fdm is None:
        vol_is = daily_vol(is_prices)
        fc_is = combined_forecast(
            is_prices, vol_is, fdm=1.0,
            ewmac_scalars=ewmac_scalars,
            mr_scalars=mr_scalars,
            rule_weights=rule_weights,
        )
        rule_cols = [c for c in fc_is.columns
                     if c not in ("trend_combined", "mr_combined", "combined")]
        fdm = calibrate_fdm(fc_is[rule_cols], rule_weights=rule_weights)

    # ── Full-series computation ───────────────────────────────────────────────
    vol = daily_vol(prices)
    fc = combined_forecast(
        prices, vol, fdm=fdm,
        ewmac_scalars=ewmac_scalars,
        mr_scalars=mr_scalars,
        rule_weights=rule_weights,
    )
    fx = _fx_rate_to_usd(cfg.currency, eurusd_prices, eurgbp_prices, prices.index,
                         usdjpy_prices=usdjpy_prices)

    positions = compute_positions(
        prices=prices,
        vol=vol,
        forecast=fc["combined"],
        pointsize=cfg.pointsize,
        capital=capital,
        vol_target=vol_target,
        idm=idm,
        fx_rate_to_usd=fx,
        instrument_weight=cfg.weight,
    )

    gpnl = gross_pnl(positions, prices, cfg.pointsize)
    costs = transaction_costs(positions, cfg.spread_cost, cfg.pointsize)

    gpnl_usd = to_usd(gpnl, cfg.currency, eurusd_prices, eurgbp_prices, usdjpy_prices)
    costs_usd = to_usd(costs, cfg.currency, eurusd_prices, eurgbp_prices, usdjpy_prices)
    net_pnl_usd = (gpnl_usd - costs_usd).rename("net_pnl_usd")

    return InstrumentResult(
        code=code,
        positions=positions,
        gross_pnl_usd=gpnl_usd,
        costs_usd=costs_usd,
        net_pnl_usd=net_pnl_usd,
        fdm=fdm,
    )


def run_portfolio(
    instruments: list[str] = INSTRUMENTS,
    split_date: datetime | None = None,
    capital: float = 10_000.0,
    vol_target: float = 0.20,
    calibrated_fdms: dict[str, float] | None = None,
    calibrated_idm: float | None = None,
    ewmac_scalars: dict[tuple[int, int], float] | None = None,
    mr_scalars: dict[int, float] | None = None,
    rule_weights: dict[str, float] | None = None,
) -> BacktestResult:
    """Two-pass portfolio backtest.

    Pass 1: IDM=1, calibrate FDMs from IS data, build instrument return
            correlations → compute IDM.
    Pass 2: Rerun with calibrated IDM and cached FDMs.

    Args:
        calibrated_fdms: If provided, skip FDM calibration in pass 1 and use
                         these FDMs directly. Pass 1 still runs to build IS returns
                         for IDM computation unless calibrated_idm is also given.
        calibrated_idm:  If provided, skip IDM computation and use this value.
                         If both calibrated_fdms and calibrated_idm are given,
                         pass 1 is skipped entirely.
        ewmac_scalars:   Override scalars for EWMAC rules, passed to run_instrument().
        mr_scalars:      Override scalars for MR rules, passed to run_instrument().
        rule_weights:    Per-rule combination weights, passed to run_instrument().
    """
    if split_date is None:
        split_date = compute_split_date()

    cfgs = load_instrument_configs()

    # FX series needed for currency conversion throughout
    eurusd_prices = load_adjusted_prices("EURUSD")
    eurgbp_prices = load_adjusted_prices("EURGBP")
    usdjpy_prices = load_adjusted_prices("USDJPY")

    all_prices = {}
    for code in instruments:
        if code not in cfgs:
            continue
        try:
            all_prices[code] = load_adjusted_prices(code)
        except FileNotFoundError:
            print(f"  WARNING: no data for {code}, skipping.")

    # Determine if we can skip pass 1 entirely
    skip_pass1 = (calibrated_fdms is not None) and (calibrated_idm is not None)

    if skip_pass1:
        print("Pass 1: skipped (calibrated FDMs and IDM provided).")
        fdms = calibrated_fdms
        idm = calibrated_idm
        pass1 = {}
    else:
        # ── Pass 1: IDM = 1.0, calibrate FDMs (or use provided FDMs) ─────────
        print("Pass 1: calibrating FDMs and IDM...")
        pass1: dict[str, InstrumentResult] = {}
        for code in instruments:
            if code not in all_prices:
                print(f"  WARNING: no data for {code}, skipping.")
                continue
            print(f"  {code}", end=" ", flush=True)

            # Use provided FDM if available, else calibrate
            pre_fdm = calibrated_fdms.get(code) if calibrated_fdms is not None else None

            pass1[code] = run_instrument(
                code=code,
                cfg=cfgs[code],
                prices=all_prices[code],
                split_date=split_date,
                eurusd_prices=eurusd_prices,
                eurgbp_prices=eurgbp_prices,
                capital=capital,
                vol_target=vol_target,
                idm=1.0,
                fdm=pre_fdm,
                usdjpy_prices=usdjpy_prices,
                ewmac_scalars=ewmac_scalars,
                mr_scalars=mr_scalars,
                rule_weights=rule_weights,
            )
        print()

        # Build IS return correlations for IDM (or use provided IDM)
        is_returns = pd.DataFrame({
            code: res.net_pnl_usd[res.net_pnl_usd.index < split_date] / capital
            for code, res in pass1.items()
        })
        weights = np.array([cfgs[code].weight for code in pass1])

        if calibrated_idm is not None:
            idm = calibrated_idm
            print(f"  IDM = {idm:.3f} (provided, skipping computation)\n")
        else:
            idm = compute_idm(is_returns, weights=weights)
            print(f"  IDM = {idm:.3f}\n")

        fdms = {code: res.fdm for code, res in pass1.items()}

    # ── Pass 2: calibrated IDM, reuse FDMs ──────────────────────────────────
    print("Pass 2: running with calibrated IDM...")
    pass2: dict[str, InstrumentResult] = {}
    for code in instruments:
        if code not in all_prices:
            continue
        print(f"  {code}", end=" ", flush=True)
        pass2[code] = run_instrument(
            code=code,
            cfg=cfgs[code],
            prices=all_prices[code],
            split_date=split_date,
            eurusd_prices=eurusd_prices,
            eurgbp_prices=eurgbp_prices,
            capital=capital,
            vol_target=vol_target,
            idm=idm,
            fdm=fdms.get(code),
            usdjpy_prices=usdjpy_prices,
            ewmac_scalars=ewmac_scalars,
            mr_scalars=mr_scalars,
            rule_weights=rule_weights,
        )
    print("\n")

    # ── Aggregate portfolio P&L ──────────────────────────────────────────────
    all_net = pd.DataFrame({
        code: res.net_pnl_usd for code, res in pass2.items()
    })
    portfolio_pnl = all_net.sum(axis=1)

    is_pnl = portfolio_pnl[portfolio_pnl.index < split_date]
    oos_pnl = portfolio_pnl[portfolio_pnl.index >= split_date]

    return BacktestResult(
        is_pnl=is_pnl,
        oos_pnl=oos_pnl,
        idm=idm,
        fdms=fdms,
        instrument_results=pass2,
        split_date=split_date,
        capital=capital,
    )

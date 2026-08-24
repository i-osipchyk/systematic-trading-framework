"""
Walk-forward calibration pipeline.

Expanding-window walk-forward: min_is_years IS → oos_years OOS per fold,
growing the IS window by one OOS period each fold.

User inputs collected once upfront:
  - Step 02: forecast weights (family + individual)
  - Step 06: instrument weights (group + individual)

Auto-calibrated per fold on IS data only:
  - Step 01: rule scalars
  - Step 03: per-instrument FDM
  - Vol target: Kelly geometric mean (10% floor when IS SR ≤ 0)
  - Step 07: IDM

OOS slices are concatenated into a single honest equity curve.

Usage:
    uv run python calibrate/wf_pipeline.py
    uv run python calibrate/wf_pipeline.py --config config/default.yaml
    uv run python calibrate/wf_pipeline.py --min-is-years 3 --oos-years 1
    uv run python calibrate/wf_pipeline.py --resume systems/default/wf_run_X
    uv run python calibrate/wf_pipeline.py --resume systems/default/wf_run_X --from-fold 3
    uv run python calibrate/wf_pipeline.py --verbose
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import shutil
import sys
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parents[1]))

import src.backtest.config as config_mod

from src.backtest.config import (
    load_end_date,
    load_instrument_configs,
    required_fx_helpers,
    set_config,
    traded_instruments,
)
from src.backtest.engine import _fx_rate_to_usd, run_portfolio
from src.backtest.metrics import performance_report, sharpe_ratio
from src.backtest.pnl import gross_pnl, to_usd, transaction_costs
from src.backtest.sizing import compute_positions
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import split_series
from src.rules.combine import combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

STEP_LINE = "─" * 60
VOL_FLOOR = 0.15
FIXED_VOL_FOR_MEASUREMENT = 0.20


@dataclass
class FoldResult:
    fold: int
    is_start: datetime
    is_end: datetime
    oos_end: datetime
    is_sharpe: float       # net IS Sharpe (Kelly input)
    gross_is_sr: float     # gross IS Sharpe
    vol_target: float
    idm: float
    oos_pnl: pd.Series     # net OOS PnL
    gross_oos_pnl: pd.Series


@contextlib.contextmanager
def _suppress_stdout():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _import_step(module_name: str):
    root = Path(__file__).parents[1]
    file_path = root / (module_name.replace(".", "/") + ".py")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _common_data_window(instrument_codes: list[str]) -> tuple[datetime, datetime]:
    starts, ends = [], []
    for code in instrument_codes:
        try:
            s = load_adjusted_prices(code)
            starts.append(s.index.min())
            ends.append(s.index.max())
        except FileNotFoundError:
            pass
    if not starts:
        raise RuntimeError("No instrument data found.")
    return min(starts), min(ends)


MIN_PARTIAL_OOS_DAYS = 90


def _compute_fold_dates(
    instruments: list[str],
    min_is_years: int,
    oos_years: int,
) -> list[tuple[datetime, datetime, datetime]]:
    """Return [(is_start, is_end, oos_end), ...] for each expanding-window fold.

    Full folds have oos_end = is_end + oos_years. If the next fold's is_end falls
    within the data window but the full OOS period does not fit, a partial final
    fold is added provided at least MIN_PARTIAL_OOS_DAYS of OOS data are available.
    """
    common_start, common_end = _common_data_window(instruments)
    cfg_end = load_end_date()
    if cfg_end is not None and cfg_end < common_end:
        common_end = cfg_end
    folds = []
    fold = 0
    while True:
        is_years = min_is_years + fold * oos_years
        is_end = common_start + timedelta(days=365.25 * is_years)
        oos_end = is_end + timedelta(days=365.25 * oos_years)
        if oos_end > common_end:
            # Add a partial final fold if enough OOS data exists
            oos_available = (common_end - is_end).days
            if is_end < common_end and oos_available >= MIN_PARTIAL_OOS_DAYS:
                folds.append((common_start, is_end, common_end))
            break
        folds.append((common_start, is_end, oos_end))
        fold += 1
    return folds


def _compute_vol_target_auto(
    instruments: list[str],
    family_scalars: dict,
    rule_weights: dict,
    fdm_data: dict,
    instrument_weights_raw: dict[str, float],
    is_end: datetime,
    capital: float,
) -> tuple[float, float]:
    """Kelly geomean vol target on IS data. Returns (is_sharpe, vol_target)."""
    cfgs = load_instrument_configs()
    n = len(instruments)

    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices_map = {code: load_adjusted_prices(code) for code in fx_helper_codes}
    for _fx in ("EURUSD", "EURGBP", "USDJPY", "USDCAD"):
        if _fx in instruments and _fx not in fx_prices_map:
            fx_prices_map[_fx] = load_adjusted_prices(_fx)
    eurusd = fx_prices_map.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices_map.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices_map.get("USDJPY", pd.Series(dtype=float))
    usdcad = fx_prices_map.get("USDCAD", pd.Series(dtype=float))

    all_pnl: dict[str, pd.Series] = {}

    for code in instruments:
        if code not in cfgs:
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue

        is_prices, _ = split_series(prices, is_end)
        if len(is_prices) < 20:
            continue

        vol_is = daily_vol(is_prices)
        cfg = cfgs[code]
        fdm = float(fdm_data.get(code, 1.0))
        inst_weight = instrument_weights_raw.get(code, 1.0 / n)

        fc_is = combined_forecast(
            is_prices, vol_is, fdm=fdm,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
            instrument_code=code,
        )
        fx = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, is_prices.index,
                             usdjpy_prices=usdjpy, usdcad_prices=usdcad)
        pos = compute_positions(
            prices=is_prices, vol=vol_is, forecast=fc_is["combined"],
            pointsize=cfg.pointsize, capital=capital,
            vol_target=FIXED_VOL_FOR_MEASUREMENT,
            idm=1.0, fx_rate_to_usd=fx,
            instrument_weight=inst_weight,
        )
        gpnl = gross_pnl(pos, is_prices, cfg.pointsize)
        costs = transaction_costs(pos, cfg.spread_cost, cfg.pointsize)
        gpnl_usd = to_usd(gpnl, cfg.currency, eurusd, eurgbp, usdjpy, usdcad_prices=usdcad)
        costs_usd = to_usd(costs, cfg.currency, eurusd, eurgbp, usdjpy, usdcad_prices=usdcad)
        all_pnl[code] = gpnl_usd - costs_usd

    portfolio_pnl = pd.DataFrame(all_pnl).sum(axis=1)
    is_sharpe = sharpe_ratio(portfolio_pnl, capital)

    if is_sharpe <= 0:
        return is_sharpe, VOL_FLOOR

    realistic_sr = is_sharpe * 0.75
    full_kelly = realistic_sr
    half_kelly = realistic_sr / 2.0
    vol_target = float(np.clip(np.sqrt(full_kelly * half_kelly), 0.15, 0.40))
    return is_sharpe, vol_target


def _run_user_setup(setup_dir: Path) -> None:
    """Collect structural parameters once, organized by build phase."""
    print(f"\n  {STEP_LINE}")
    print(f"  Walk-forward setup: structural parameters (collected once)")
    print(f"  {STEP_LINE}\n")

    step01 = _import_step("calibrate.step3a_scalars")
    step02 = _import_step("calibrate.step3d_forecast_weights")
    step03 = _import_step("calibrate.step3d_fdm")
    step04 = _import_step("calibrate.step3c_cost_filter")
    step06 = _import_step("calibrate.step4a_instrument_weights")
    step07 = _import_step("calibrate.step4b_idm")

    # ── Step 3: Rule correlations, trading speed, forecast weights ───────────
    print(f"  Step 3 — Scalars, cost filter, forecast weights, FDM (IS data)")
    print(f"  {STEP_LINE}")

    print("  Step 3a: Rule scalars...")
    step01.main(state_dir=setup_dir)

    print(f"\n  Step 3c: Turnover and standardised cost ceiling")
    step04.main(state_dir=setup_dir)

    print(f"\n  Step 3d: Forecast weights")
    step02.main(state_dir=setup_dir)

    print(f"\n  Step 3d: FDM (initial, full IS window)")
    step03.main(state_dir=setup_dir)

    # ── Step 4: Instrument weights ────────────────────────────────────────────
    print(f"\n  Step 4 — Instrument weights, IDM (IS data)")
    print(f"  {STEP_LINE}")

    print(f"  Step 4a: Instrument weights")
    step06.main(state_dir=setup_dir)

    print(f"\n  Step 4b: IDM (initial, full IS window)")
    step07.main(state_dir=setup_dir)

    print(f"\n  Setup complete. Parameters saved to {setup_dir}/\n")


def _run_fold(
    fold_num: int,
    is_start: datetime,
    is_end: datetime,
    oos_end: datetime,
    setup_dir: Path,
    fold_dir: Path,
    instruments: list[str],
    capital: float,
    verbose: bool,
) -> FoldResult:
    fold_dir.mkdir(parents=True, exist_ok=True)

    # Copy locked structural params from setup
    for fname in [
        "step3d_family_weights.yaml", "step3d_forecast_weights.yaml",
        "step4a_group_weights.yaml", "step4a_instrument_weights.yaml",
    ]:
        src = setup_dir / fname
        if src.exists():
            shutil.copy2(src, fold_dir / fname)

    weights_data = st.load("step3d_forecast_weights.yaml", state_dir=fold_dir)
    inst_weights_data = st.load("step4a_instrument_weights.yaml", state_dir=fold_dir)
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in weights_data["forecast_weights"].items()
    }
    instrument_weights_raw: dict[str, float] = {
        k: float(v) for k, v in inst_weights_data["instrument_weights"].items()
    }

    def ctx():
        return contextlib.nullcontext() if verbose else _suppress_stdout()

    # Phase 2: rule scalars and FDM (re-calibrated on this fold's IS window)
    print(f"    [P2] Rule scalars...", end="", flush=True)
    step01 = _import_step("calibrate.step3a_scalars")
    with ctx():
        step01.main(state_dir=fold_dir, split_date=is_end)
    scalars_data = st.load("step3a_scalars.yaml", state_dir=fold_dir)
    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)
    print(" done")

    print(f"    [P2] FDM...", end="", flush=True)
    step03 = _import_step("calibrate.step3d_fdm")
    with ctx():
        step03.main(state_dir=fold_dir, split_date=is_end)
    fdm_data = st.load("step3d_fdm.yaml", state_dir=fold_dir)
    calibrated_fdms = {k: float(v) for k, v in fdm_data.items()}
    print(" done")

    # Phase 3: IDM (re-calibrated on this fold's IS window)
    print(f"    [P3] IDM...", end="", flush=True)
    step07 = _import_step("calibrate.step4b_idm")
    with ctx():
        step07.main(state_dir=fold_dir, split_date=is_end)
    idm_data = st.load("step4b_idm.yaml", state_dir=fold_dir)
    calibrated_idm = float(idm_data["idm"])
    print(f" {calibrated_idm:.3f}")

    # Phase 5: vol target (IS SR → 0.75 OOS discount → Kelly geomean; 15% floor when IS SR ≤ 0)
    print(f"    [P5] Vol target...", end="", flush=True)
    is_sharpe, vol_target = _compute_vol_target_auto(
        instruments, family_scalars, rule_weights, fdm_data,
        instrument_weights_raw, is_end, capital,
    )
    floor_msg = " [floor]" if is_sharpe <= 0 else ""
    print(f" IS SR={is_sharpe:.2f}  vol_target={vol_target:.0%}{floor_msg}")
    st.save("step5_vol_target.yaml", {
        "vol_target": round(vol_target, 4),
        "is_sharpe": round(is_sharpe, 4),
    }, state_dir=fold_dir)

    # Phase 6: backtest (IS + OOS) with fixed parameters
    cfgs = load_instrument_configs()
    patched_cfgs = {
        code: replace(cfg, weight=instrument_weights_raw.get(code, cfg.weight))
        for code, cfg in cfgs.items()
    }
    original_load = config_mod.load_instrument_configs
    config_mod.load_instrument_configs = lambda: patched_cfgs

    try:
        print(f"    [P6] Backtest...", end="", flush=True)
        with ctx():
            result = run_portfolio(
                instruments=instruments,
                split_date=is_end,
                capital=capital,
                vol_target=vol_target,
                calibrated_fdms=calibrated_fdms,
                calibrated_idm=calibrated_idm,
                family_scalars=family_scalars,
                rule_weights=rule_weights,
            )
    finally:
        config_mod.load_instrument_configs = original_load

    # Slice to this fold's OOS window only
    oos_pnl = result.oos_pnl[result.oos_pnl.index < oos_end]

    # Gross portfolio PnL (sum across instruments)
    gross_df = pd.DataFrame({
        code: ir.gross_pnl_usd
        for code, ir in result.instrument_results.items()
    })
    gross_portfolio = gross_df.sum(axis=1)
    gross_is_pnl = gross_portfolio[gross_portfolio.index < is_end]
    gross_oos_pnl = gross_portfolio[
        (gross_portfolio.index >= is_end) & (gross_portfolio.index < oos_end)
    ]
    gross_is_sr = sharpe_ratio(gross_is_pnl, capital)
    print(" done")

    return FoldResult(
        fold=fold_num,
        is_start=is_start,
        is_end=is_end,
        oos_end=oos_end,
        is_sharpe=is_sharpe,
        gross_is_sr=gross_is_sr,
        vol_target=vol_target,
        idm=calibrated_idm,
        oos_pnl=oos_pnl,
        gross_oos_pnl=gross_oos_pnl,
    )


def _print_wf_summary(
    fold_results: list[FoldResult],
    all_oos_pnl: pd.Series,
    capital: float,
) -> None:
    print(f"\n  {'='*90}")
    print(f"  Walk-forward results")
    print(f"  {'='*90}\n")

    hdr = (
        f"  {'Fold':>4}  {'IS start':>10}  {'IS end':>10}  {'OOS end':>10}"
        f"  {'gSR IS':>7}  {'SR IS':>6}  {'VT':>5}  {'IDM':>5}"
        f"  {'gSR OOS':>8}  {'SR OOS':>7}  {'OOS Ret':>8}  {'OOS DD':>8}"
    )
    print(hdr)
    print(f"  {'─'*len(hdr.rstrip())}")

    for fr in fold_results:
        net_m = performance_report(fr.oos_pnl, capital)
        gross_m = performance_report(fr.gross_oos_pnl, capital)
        oos_days = (fr.oos_end - fr.is_end).days
        partial_tag = "*" if oos_days < 330 else " "
        print(
            f"  {fr.fold:>4}{partial_tag} {fr.is_start.date()!s:>10}  {fr.is_end.date()!s:>10}"
            f"  {fr.oos_end.date()!s:>10}"
            f"  {fr.gross_is_sr:>7.2f}  {fr.is_sharpe:>6.2f}  {fr.vol_target:>4.0%}  {fr.idm:>5.3f}"
            f"  {gross_m['sharpe']:>8.2f}  {net_m['sharpe']:>7.2f}"
            f"  {net_m['ann_return']:>7.1%}  {net_m['max_drawdown']:>7.1%}"
        )

    # Aggregate OOS
    all_gross_oos = pd.concat(
        [fr.gross_oos_pnl for fr in fold_results if not fr.gross_oos_pnl.empty]
    ).sort_index()

    n_bars = len(all_oos_pnl.dropna())
    n_years = n_bars / 256
    agg_net = performance_report(all_oos_pnl, capital)
    agg_gross = performance_report(all_gross_oos, capital) if not all_gross_oos.empty else {}
    has_partial = any((fr.oos_end - fr.is_end).days < 330 for fr in fold_results)

    print(f"\n  {'─'*60}")
    if has_partial:
        print(f"  * partial fold (OOS window < 1yr, annualised stats extrapolated)")
    print(f"  Aggregate OOS  ({n_bars} bars / {n_years:.1f} years)")
    print(f"  {'':20} {'Gross':>8}  {'Net':>8}")
    print(f"  {'Sharpe':<20} {agg_gross.get('sharpe', float('nan')):>8.2f}  {agg_net['sharpe']:>8.2f}")
    print(f"  {'Ann return':<20} {agg_gross.get('ann_return', float('nan')):>7.1%}   {agg_net['ann_return']:>7.1%}")
    print(f"  {'Max drawdown':<20} {agg_gross.get('max_drawdown', float('nan')):>7.1%}   {agg_net['max_drawdown']:>7.1%}")
    print(f"  {'─'*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward calibration pipeline")
    parser.add_argument("--config", type=str, default="config/default.yaml")
    parser.add_argument("--min-is-years", type=int, default=2,
                        help="Minimum IS window in years (default: 2)")
    parser.add_argument("--oos-years", type=int, default=1,
                        help="OOS window per fold in years (default: 1)")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume an existing WF run directory")
    parser.add_argument("--from-fold", type=int, default=1,
                        help="Skip folds before N and load their cached results (1-indexed)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show full output from each calibration step")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    config_path = root / args.config
    if not config_path.exists():
        print(f"  ERROR: config not found: {config_path}")
        sys.exit(1)
    set_config(config_path)

    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)

    # Determine WF run directory
    if args.resume:
        wf_dir = Path(args.resume)
        if not wf_dir.exists():
            print(f"  ERROR: resume path not found: {wf_dir}")
            sys.exit(1)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        wf_dir = root / "systems" / config_path.stem / f"wf_run_{ts}"
        wf_dir.mkdir(parents=True, exist_ok=True)

    setup_dir = wf_dir / "setup"
    setup_dir.mkdir(exist_ok=True)

    # Generate fold schedule
    fold_dates = _compute_fold_dates(instruments, args.min_is_years, args.oos_years)
    if not fold_dates:
        print(f"  ERROR: not enough data for a single fold "
              f"(need ≥{args.min_is_years + args.oos_years} years).")
        sys.exit(1)

    common_start, common_end = _common_data_window(instruments)
    cfg_end = load_end_date()
    if cfg_end is not None and cfg_end < common_end:
        common_end = cfg_end

    print(f"\n  {'='*60}")
    print(f"  Walk-forward pipeline")
    print(f"  {'='*60}")
    print(f"  Config      : {config_path}")
    print(f"  WF dir      : {wf_dir}/")
    print(f"  Data window : {common_start.date()} → {common_end.date()}"
          + (f"  [capped by end_date]" if cfg_end is not None else ""))
    print(f"  IS window   : expanding, starting at {args.min_is_years}yr")
    print(f"  OOS window  : {args.oos_years}yr per fold")
    print(f"  Folds       : {len(fold_dates)}")
    print(f"  Capital     : ${args.capital:,.0f}")
    print()
    full_oos_days = int(365.25 * args.oos_years)
    for i, (is_start, is_end, oos_end) in enumerate(fold_dates, 1):
        is_yrs = args.min_is_years + (i - 1) * args.oos_years
        partial = (oos_end - is_end).days < full_oos_days
        partial_tag = "  [partial]" if partial else ""
        print(f"    Fold {i:2d} ({is_yrs}yr IS): "
              f"IS [{is_start.date()} → {is_end.date()}]  "
              f"OOS [{is_end.date()} → {oos_end.date()}]{partial_tag}")
    print(f"  {'='*60}\n")

    # User setup (once; skipped if already done)
    setup_complete = (
        (setup_dir / "step3d_forecast_weights.yaml").exists() and
        (setup_dir / "step4a_instrument_weights.yaml").exists() and
        (setup_dir / "step3c_turnover.yaml").exists()
    )
    if not setup_complete:
        _run_user_setup(setup_dir)
    else:
        print(f"  Setup already done (weights found in {setup_dir.name}/).")
        print(f"  To redo setup, delete {setup_dir}/ and rerun.\n")

    # Run folds
    fold_results: list[FoldResult] = []

    for i, (is_start, is_end, oos_end) in enumerate(fold_dates, 1):
        fold_dir = wf_dir / f"fold_{i:02d}"

        # Load cached fold if skipping
        if i < args.from_fold:
            oos_file = fold_dir / "oos_pnl.csv"
            meta_file = fold_dir / "fold_meta.yaml"
            gross_oos_file = fold_dir / "gross_oos_pnl.csv"
            if oos_file.exists() and meta_file.exists():
                with open(meta_file) as f:
                    meta = yaml.safe_load(f)
                oos_pnl = pd.read_csv(
                    oos_file, index_col=0, parse_dates=True
                ).squeeze("columns")
                gross_oos_pnl = (
                    pd.read_csv(gross_oos_file, index_col=0, parse_dates=True
                                ).squeeze("columns")
                    if gross_oos_file.exists()
                    else pd.Series(dtype=float)
                )
                fold_results.append(FoldResult(
                    fold=i, is_start=is_start, is_end=is_end, oos_end=oos_end,
                    is_sharpe=meta["is_sharpe"],
                    gross_is_sr=meta.get("gross_is_sr", float("nan")),
                    vol_target=meta["vol_target"],
                    idm=meta["idm"],
                    oos_pnl=oos_pnl,
                    gross_oos_pnl=gross_oos_pnl,
                ))
                print(f"  Fold {i:2d}: loaded from cache.")
            else:
                print(f"  Fold {i:2d}: skipped (no cache found; results will be incomplete).")
            continue

        is_yrs = args.min_is_years + (i - 1) * args.oos_years
        oos_days = (oos_end - is_end).days
        partial = oos_days < full_oos_days
        oos_label = f"~{oos_days // 30}mo [partial]" if partial else f"{args.oos_years}yr"
        print(f"\n  {'='*60}")
        print(f"  Fold {i}/{len(fold_dates)}  —  {is_yrs}yr IS  /  {oos_label} OOS")
        print(f"  IS  : {is_start.date()} → {is_end.date()}")
        print(f"  OOS : {is_end.date()} → {oos_end.date()}")
        print(f"  {'='*60}")

        try:
            fr = _run_fold(
                fold_num=i,
                is_start=is_start,
                is_end=is_end,
                oos_end=oos_end,
                setup_dir=setup_dir,
                fold_dir=fold_dir,
                instruments=instruments,
                capital=args.capital,
                verbose=args.verbose,
            )
        except KeyboardInterrupt:
            print(f"\n  Fold {i} aborted.")
            sys.exit(1)
        except Exception:
            print(f"\n  Fold {i} FAILED:")
            traceback.print_exc()
            sys.exit(1)

        # Persist for resume
        fr.oos_pnl.to_frame("net_pnl_usd").to_csv(fold_dir / "oos_pnl.csv")
        fr.gross_oos_pnl.to_frame("gross_pnl_usd").to_csv(fold_dir / "gross_oos_pnl.csv")
        with open(fold_dir / "fold_meta.yaml", "w") as f:
            yaml.dump({
                "fold": fr.fold,
                "is_start": str(fr.is_start.date()),
                "is_end": str(fr.is_end.date()),
                "oos_end": str(fr.oos_end.date()),
                "is_sharpe": round(fr.is_sharpe, 4),
                "gross_is_sr": round(fr.gross_is_sr, 4),
                "vol_target": round(fr.vol_target, 4),
                "idm": round(fr.idm, 4),
            }, f, default_flow_style=False)

        fold_results.append(fr)

        m = performance_report(fr.oos_pnl, args.capital)
        print(f"  → OOS: SR={m['sharpe']:.2f}  Ret={m['ann_return']:.1%}  MaxDD={m['max_drawdown']:.1%}")

    if not fold_results:
        print("  No fold results to aggregate.")
        return

    all_oos_pnl = pd.concat([fr.oos_pnl for fr in fold_results]).sort_index()
    _print_wf_summary(fold_results, all_oos_pnl, args.capital)

    all_oos_pnl.to_frame("net_pnl_usd").to_csv(wf_dir / "aggregate_oos_pnl.csv")
    print(f"  Aggregate OOS PnL → {wf_dir}/aggregate_oos_pnl.csv")
    print(f"  WF run directory  → {wf_dir}/\n")


if __name__ == "__main__":
    main()

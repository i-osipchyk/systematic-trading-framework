"""
Step 3: Rule calibration — scalars, correlations, cost filter, forecast weights.

Sub-steps run in sequence:
  3a: IS-calibrated scalars (mean absolute forecast → 10, pooled across instruments)
  3b: Pairwise rule forecast correlations (pooled across instruments)
  3c: IS turnover per rule; per-instrument cost-danger flags
  3d: Forecast weights template written to run directory for editing

Outputs written to config/:
  step3.yaml  (sections: scalars, turnover, forecast_weights, fdm)

Outputs written to results/:
  step3_report.md  — markdown report with all tables

Usage:
    uv run python calibrate/step3_rules.py
    uv run python calibrate/step3_rules.py --system systems/universe_v4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import (
    load_bars_per_year, load_capital, load_instrument_configs, load_rules_config, set_config,
    traded_instruments, required_fx_helpers,
)
from src.backtest.engine import _fx_rate_to_usd
from src.backtest.sizing import compute_positions
from src.calibration import state as st
from src.data.pst_writer import load_adjusted_prices
from src.data.splits import compute_split_date, split_series
from src.rules.combine import calibrate_fdm, combined_forecast
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol

COST_BUDGET = 0.13   # Carver: turnover × max_standardised_cost ≤ 0.13


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rule_names_from_scalars(scalars_data: dict) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for block, raw in scalars_data.items():
        handler = REGISTRY.get(block)
        if handler is None or not raw:
            continue
        parsed = handler.parse_scalars(raw)
        for v in parsed:
            name = handler.rule_name(v)
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _roundtrips_per_year(positions: pd.Series, bars_per_year: int) -> float:
    daily_trades = positions.diff().abs()
    mean_pos = positions.abs().mean()
    if mean_pos == 0:
        return 0.0
    n_years = len(positions.dropna()) / bars_per_year
    return float(daily_trades.sum() / 2 / mean_pos / n_years) if n_years > 0 else 0.0


# ── Pass 1: Scalars ───────────────────────────────────────────────────────────

def _compute_scalars(
    instruments: list[str],
    rules: dict,
    split_date,
) -> dict:
    scalars_out: dict[str, dict] = {}

    for block_name, block_cfg in rules.items():
        if block_name == "seasonality":
            continue
        handler = REGISTRY.get(block_name)
        if handler is None:
            continue
        variants = handler.variants_from_cfg(block_cfg)
        if not variants:
            continue

        maf_by_variant: dict = {v: [] for v in variants}
        for code in instruments:
            try:
                prices = load_adjusted_prices(code)
            except FileNotFoundError:
                continue
            is_prices, _ = split_series(prices, split_date)
            if len(is_prices) < 20:
                continue
            vol = daily_vol(is_prices)
            for variant in variants:
                raw = handler.compute_one_raw(is_prices, variant, vol, instrument_code=code)
                maf = float(np.nanmean(np.abs(raw)))
                maf_by_variant[variant].append(maf)

        block_scalars: dict = {}
        for variant in variants:
            mafs = [m for m in maf_by_variant[variant] if m > 0.0 and not np.isnan(m)]
            if mafs:
                block_scalars[variant] = round(10.0 / float(np.nanmean(mafs)), 4)
        if block_scalars:
            scalars_out[block_name] = handler.dump_scalars(block_scalars)

    if "seasonality" in rules:
        from src.rules.seasonality import fit_seasonality
        seasonal_cfgs = rules["seasonality"].get("instruments", [])
        seasonal_models: dict[str, dict] = {}
        for code in instruments:
            if code not in seasonal_cfgs:
                continue
            try:
                prices = load_adjusted_prices(code)
            except FileNotFoundError:
                continue
            is_prices, _ = split_series(prices, split_date)
            if len(is_prices) < 512:
                continue
            month_means = fit_seasonality(is_prices)
            seasonal_models[code] = {str(k): v for k, v in month_means.items()}
        if seasonal_models:
            scalars_out["seasonality"] = seasonal_models

    return scalars_out


# ── Pass 2: Correlations + Turnover ──────────────────────────────────────────

def _compute_corr_and_turnover(
    instruments: list[str],
    cfgs,
    scalars_data: dict,
    split_date,
    bars_per_year: int,
    fx_prices: dict,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, dict[str, float]], dict[str, float]]:
    """
    Returns:
        corr_matrix        : pooled pairwise correlation DataFrame
        pooled_turnover    : {rule_name: avg_roundtrips_per_year}
        per_inst_turnover  : {rule_name: {instrument: roundtrips_per_year}}
        mean_daily_vol     : {instrument: mean_daily_vol_in_price_units}
    """
    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)

    seen_names: set[str] = set()
    all_rule_names: list[str] = []
    for block, scalars in family_scalars.items():
        handler = REGISTRY[block]
        for v in scalars:
            name = handler.rule_name(v)
            if name not in seen_names:
                seen_names.add(name)
                all_rule_names.append(name)

    eurusd = fx_prices.get("EURUSD", pd.Series(dtype=float))
    eurgbp = fx_prices.get("EURGBP", pd.Series(dtype=float))
    usdjpy = fx_prices.get("USDJPY", pd.Series(dtype=float))
    usdcad = fx_prices.get("USDCAD", pd.Series(dtype=float))

    per_inst_turnover: dict[str, dict[str, float]] = {r: {} for r in all_rule_names}
    mean_daily_vol: dict[str, float] = {}
    forecasts_by_instrument: dict[str, pd.DataFrame] = {}

    for code in instruments:
        if code not in cfgs:
            continue
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) < 20:
            continue
        vol_is = daily_vol(is_prices)
        mean_daily_vol[code] = float((vol_is * is_prices).mean()) * (bars_per_year ** 0.5)  # annual vol in price units
        cfg = cfgs[code]

        fx = _fx_rate_to_usd(cfg.currency, eurusd, eurgbp, is_prices.index,
                             usdjpy_prices=usdjpy, usdcad_prices=usdcad)

        fc_cols: dict[str, pd.Series] = {}
        for block, scalars in family_scalars.items():
            handler = REGISTRY[block]

            if block == "seasonality":
                fc_df = handler.compute_all(is_prices, vol_is, scalars, instrument_code=code)
                if "SEASONALITY" in fc_df.columns:
                    forecast = fc_df["SEASONALITY"].clip(-20, 20)
                    fc_cols["SEASONALITY"] = forecast
                    pos = compute_positions(
                        prices=is_prices, vol=vol_is, forecast=forecast,
                        pointsize=cfg.pointsize, capital=load_capital(),
                        vol_target=0.15, idm=1.0, fx_rate_to_usd=fx,
                        instrument_weight=1.0,
                    )
                    per_inst_turnover["SEASONALITY"][code] = _roundtrips_per_year(pos, bars_per_year)
                continue

            for variant, scalar in scalars.items():
                rule_name = handler.rule_name(variant)
                raw = handler.compute_one_raw(is_prices, variant, vol_is, instrument_code=code)
                forecast = (raw * scalar).clip(-20, 20)
                fc_cols[rule_name] = forecast
                pos = compute_positions(
                    prices=is_prices, vol=vol_is, forecast=forecast,
                    pointsize=cfg.pointsize, capital=load_capital(),
                    vol_target=0.15, idm=1.0, fx_rate_to_usd=fx,
                    instrument_weight=1.0,
                )
                per_inst_turnover[rule_name][code] = _roundtrips_per_year(pos, bars_per_year)

        if fc_cols:
            forecasts_by_instrument[code] = pd.DataFrame(fc_cols)

    pooled_turnover = {
        rule: float(np.mean(list(by_inst.values()))) if by_inst else 0.0
        for rule, by_inst in per_inst_turnover.items()
    }

    corr_matrix = _pooled_correlation(forecasts_by_instrument, all_rule_names)

    return corr_matrix, pooled_turnover, per_inst_turnover, mean_daily_vol


def _pooled_correlation(
    forecasts_by_instrument: dict[str, pd.DataFrame],
    all_rules: list[str],
) -> pd.DataFrame:
    n = len(all_rules)
    idx = {r: i for i, r in enumerate(all_rules)}
    sum_corr = np.zeros((n, n))
    count = np.zeros((n, n))

    for fc in forecasts_by_instrument.values():
        rule_cols = [c for c in all_rules if c in fc.columns]
        if len(rule_cols) < 2:
            continue
        clean = fc[rule_cols].dropna()
        active = [c for c in rule_cols if clean[c].std() > 1e-6]
        if len(active) < 2:
            continue
        corr = clean[active].corr()
        for r1 in active:
            for r2 in active:
                i, j = idx[r1], idx[r2]
                sum_corr[i, j] += corr.loc[r1, r2]
                count[i, j] += 1

    pooled = np.where(count > 0, sum_corr / count, np.nan)
    return pd.DataFrame(pooled, index=all_rules, columns=all_rules)


# ── Cost danger flags ─────────────────────────────────────────────────────────

def _dangerous_instruments(
    rule: str,
    per_inst_turnover: dict[str, dict[str, float]],
    cfgs,
    mean_daily_vol: dict[str, float],
    pooled_tv: float,
) -> list[str]:
    """Instruments whose spread/annual_vol exceeds the ceiling implied by the pooled turnover.

    Uses pooled turnover (same basis as the 'Max Std Cost' ceiling column) so that
    a slower rule always flags a subset of what a faster rule flags.
    """
    if pooled_tv <= 0:
        return []
    ceiling = COST_BUDGET / pooled_tv
    dangerous: list[str] = []
    for code in per_inst_turnover.get(rule, {}):
        if code not in cfgs or code not in mean_daily_vol:
            continue
        dvol = mean_daily_vol[code]
        if dvol == 0:
            continue
        if cfgs[code].spread_cost / dvol > ceiling:
            dangerous.append(code)
    return dangerous


# ── Forecast weights template ─────────────────────────────────────────────────

def _derive_weights(scalars_data: dict, rules_cfg: dict) -> dict[str, float]:
    """Equal weight per family, equal weight per rule within family. Sums to exactly 1."""
    family_to_rules: dict[str, list[str]] = {}
    for block, raw in scalars_data.items():
        handler = REGISTRY.get(block)
        if handler is None or not raw:
            continue
        parsed = handler.parse_scalars(raw)
        seen: set[str] = set()
        names: list[str] = []
        for v in parsed:
            name = handler.rule_name(v)
            if name not in seen:
                seen.add(name)
                names.append(name)
        if names:
            family_to_rules[block] = names

    n_families = len(family_to_rules)
    if n_families == 0:
        return {}

    per_family = 1.0 / n_families
    weights: dict[str, float] = {}
    running = 0.0
    entries = list(family_to_rules.items())
    for fi, (family, rules) in enumerate(entries):
        per_rule = per_family / len(rules) if rules else 0.0
        for ri, rule in enumerate(rules):
            is_last = (fi == len(entries) - 1) and (ri == len(rules) - 1)
            w = round(1.0 - running, 6) if is_last else round(per_rule, 6)
            weights[rule] = w
            running += w
    return weights


def _write_weights_template(
    scalars_data: dict,
    rules_cfg: dict,
    weights: dict[str, float],
    state_dir,
) -> Path:
    family_to_rules: dict[str, list[str]] = {}
    for block, raw in scalars_data.items():
        handler = REGISTRY.get(block)
        if handler is None or not raw:
            continue
        parsed = handler.parse_scalars(raw)
        seen: set[str] = set()
        names: list[str] = []
        for v in parsed:
            name = handler.rule_name(v)
            if name not in seen:
                seen.add(name)
                names.append(name)
        if names:
            family_to_rules[block] = names

    n_families = len(family_to_rules)
    per_family = 1.0 / n_families if n_families else 0.0

    lines = [
        "# Forecast weights — edit before Step 4.",
        "# Constraint: must sum to 1.0 (±0.005).",
        "#",
        "# Generated with equal weight per family and per rule within each family.",
        "# Adjust down rules with high within-family correlation (> 0.80).",
        "# Set to 0 any rule that is too expensive for most instruments.",
        "#",
        f"# {n_families} families, {per_family:.4f} each:",
    ]
    for family, rules in family_to_rules.items():
        n = len(rules)
        per_rule = per_family / n if n else 0.0
        lines.append(f"#   {family} ({n} rules): {per_rule:.6f} per rule")

    if st.has_section("step3.yaml", "forecast_weights", state_dir=state_dir):
        print("  Forecast weights section already exists in step3.yaml — skipping template.")
        return st.path("step3.yaml", state_dir=state_dir)

    st.save_section("step3.yaml", "forecast_weights", weights, state_dir=state_dir)
    return st.path("step3.yaml", state_dir=state_dir)


# ── Printing helpers ──────────────────────────────────────────────────────────

def _fmt_corr_table_text(corr: pd.DataFrame) -> list[str]:
    rules = list(corr.index)
    if not rules:
        return ["  (no rules computed — check that price data covers the IS window)"]
    label_w = max(len(r) for r in rules)
    col_w = 7
    lines = []
    header = f"  {'':>{label_w}}" + "".join(f"  {r[:col_w]:>{col_w}}" for r in rules)
    lines.append(header)
    for r1 in rules:
        row = f"  {r1:>{label_w}}"
        for r2 in rules:
            v = corr.loc[r1, r2]
            row += f"  {v:>{col_w}.3f}" if not np.isnan(v) else f"  {'n/a':>{col_w}}"
        lines.append(row)
    return lines


def _fmt_corr_table_md(corr: pd.DataFrame) -> list[str]:
    rules = list(corr.index)
    lines = []
    header = "| |" + "|".join(f" {r} " for r in rules) + "|"
    sep = "|---|" + "|".join("---:" for _ in rules) + "|"
    lines += [header, sep]
    for r1 in rules:
        cells = []
        for r2 in rules:
            v = corr.loc[r1, r2]
            cells.append(f" {v:.3f} " if not np.isnan(v) else " n/a ")
        lines.append(f"| **{r1}** |" + "|".join(cells) + "|")
    return lines


# ── Markdown report ───────────────────────────────────────────────────────────

def _write_report(
    report_path: Path,
    scalar_rows: list[tuple],
    corr: pd.DataFrame,
    cost_rows: list[tuple],
    weights: dict[str, float],
    n_instruments: int = 0,
) -> None:
    lines: list[str] = ["# Step 3 Rule Calibration Report", ""]

    # Scalars
    lines += ["## Scalars", ""]
    lines += ["| Rule | Raw MAF | Scalar |", "|------|---------|--------|"]
    for rule, maf, scalar in scalar_rows:
        lines.append(f"| {rule} | {maf:.3f} | {scalar:.2f} |")
    lines.append("")

    # Correlation matrix
    lines += ["## Correlation Matrix", ""]
    lines += _fmt_corr_table_md(corr)
    lines.append("")

    # Cost filter
    lines += ["## Cost Filter", ""]
    lines += [
        "| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |",
        "|------|-----------------|-------------|----------------------------------|",
    ]
    n_inst = n_instruments or len(cost_rows)
    for rule, tv, ceiling, dangerous in cost_rows:
        ceil_str = f"{ceiling:.4f}" if ceiling < 999 else "∞"
        if not dangerous:
            dangerous_str = "—"
        elif len(dangerous) >= n_inst:
            dangerous_str = "all (rule too fast)"
        elif len(dangerous) > n_inst // 2:
            dangerous_str = f"{len(dangerous)}/{n_inst} — " + ", ".join(dangerous[:5]) + "…"
        else:
            dangerous_str = ", ".join(dangerous)
        lines.append(f"| {rule} | {tv:.1f} | {ceil_str} | {dangerous_str} |")
    lines.append("")

    # Forecast weights
    lines += ["## Forecast Weights Template", ""]
    lines += ["| Rule | Weight |", "|------|--------|"]
    for rule, w in weights.items():
        lines.append(f"| {rule} | {w:.6f} |")
    lines.append("")

    report_path.write_text("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────

def main(state_dir=None, split_date=None, report_dir=None) -> dict:
    if report_dir is None:
        report_dir = state_dir
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules = load_rules_config()
    bars_per_year = load_bars_per_year()

    if split_date is None:
        split_date = compute_split_date(instruments)
    print(f"  IS window end : {split_date.date()}")
    print(f"  Instruments   : {len(instruments)}")
    print(f"  Rule families : {list(rules.keys())}\n")

    # ── 3a: Scalars ───────────────────────────────────────────────────────────
    print("  [3a] Computing scalars...")
    scalars_data = _compute_scalars(instruments, rules, split_date)
    st.save_section("step3.yaml", "scalars", scalars_data, state_dir=state_dir)

    scalar_rows: list[tuple] = []
    for block, raw in scalars_data.items():
        handler = REGISTRY.get(block)
        if handler is None or not raw:
            continue
        if block == "seasonality":
            for code, month_vals in raw.items():
                max_abs = max(abs(v) for v in month_vals.values()) or 1.0
                implied_scalar = round(10.0 / max_abs, 3)
                scalar_rows.append((f"SEASONALITY_{code}", round(max_abs, 4), implied_scalar))
        else:
            parsed = handler.parse_scalars(raw)
            for variant, scalar in parsed.items():
                rule_name = handler.rule_name(variant)
                raw_maf = round(10.0 / scalar, 4) if scalar != 0 else 0.0
                scalar_rows.append((rule_name, raw_maf, scalar))

    # ── 3b+3c: Correlations + Turnover ────────────────────────────────────────
    print("  [3b+3c] Computing correlations and turnover...")

    fx_helper_codes = required_fx_helpers(cfgs)
    fx_prices: dict[str, pd.Series] = {}
    for fx in set(fx_helper_codes) | {"EURUSD", "EURGBP", "USDJPY", "USDCAD"}:
        try:
            fx_prices[fx] = load_adjusted_prices(fx)
        except FileNotFoundError:
            pass

    corr, pooled_turnover, per_inst_turnover, mean_daily_vol = _compute_corr_and_turnover(
        instruments, cfgs, scalars_data, split_date, bars_per_year, fx_prices,
    )

    st.save_section("step3.yaml", "turnover",
                    {k: round(v, 2) for k, v in pooled_turnover.items()},
                    state_dir=state_dir)

    cost_rows: list[tuple] = []
    all_rule_names = _rule_names_from_scalars(scalars_data)
    for rule in all_rule_names:
        tv = pooled_turnover.get(rule, 0.0)
        ceiling = COST_BUDGET / tv if tv > 0 else float("inf")
        dangerous = _dangerous_instruments(rule, per_inst_turnover, cfgs, mean_daily_vol, tv)
        cost_rows.append((rule, tv, ceiling, dangerous))

    # ── 3d: Forecast weights template ─────────────────────────────────────────
    weights = _derive_weights(scalars_data, rules)
    weights_path = _write_weights_template(scalars_data, rules, weights, state_dir)

    # ── Print tables ──────────────────────────────────────────────────────────
    SEP = "─" * 70

    print(f"\n  {SEP}")
    print("  SCALARS  (target mean absolute forecast = 10)")
    print(f"  {SEP}")
    col_w = max(len(r) for r, _, _ in scalar_rows) + 2 if scalar_rows else 20
    print(f"  {'Rule':<{col_w}} {'Raw MAF':>9}  {'Scalar':>8}")
    print(f"  {'─' * (col_w + 22)}")
    for rule, maf, scalar in scalar_rows:
        print(f"  {rule:<{col_w}} {maf:>9.4f}  {scalar:>8.2f}")

    print(f"\n  {SEP}")
    print("  CORRELATION MATRIX  (IS forecasts, pooled across instruments)")
    print(f"  {SEP}")
    for line in _fmt_corr_table_text(corr):
        print(line)

    print(f"\n  {SEP}")
    print(f"  COST FILTER  (budget: turnover × spread/vol ≤ {COST_BUDGET})")
    print(f"  {SEP}")
    cw = max(len(r) for r, *_ in cost_rows) + 2 if cost_rows else 20
    print(f"  {'Rule':<{cw}} {'Turnover':>10}  {'Max Std Cost':>13}  Expensive Instruments")
    print(f"  {'─' * (cw + 50)}")
    n_inst = len(instruments)
    for rule, tv, ceiling, dangerous in cost_rows:
        ceil_str = f"{ceiling:.4f}" if ceiling < 999 else "∞"
        if not dangerous:
            inst_str = "—"
        elif len(dangerous) >= n_inst:
            inst_str = "all (rule too fast for cost budget)"
        elif len(dangerous) > n_inst // 2:
            inst_str = f"{len(dangerous)}/{n_inst} — " + ", ".join(dangerous[:5]) + "…"
        else:
            inst_str = ", ".join(dangerous)
        print(f"  {rule:<{cw}} {tv:>10.1f}  {ceil_str:>13}  {inst_str}")

    print(f"\n  {SEP}")
    print("  FORECAST WEIGHTS  (equal-weight template)")
    print(f"  {SEP}")
    ww = max(len(r) for r in weights) + 2 if weights else 20
    print(f"  {'Rule':<{ww}} {'Weight':>8}")
    print(f"  {'─' * (ww + 12)}")
    for rule, w in weights.items():
        print(f"  {rule:<{ww}} {w:>8.4f}")

    # ── Markdown report ────────────────────────────────────────────────────────
    report_path = st.path("step3_report.md", state_dir=report_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report(report_path, scalar_rows, corr, cost_rows, weights, n_instruments=len(instruments))

    # ── Summary ────────────────────────────────────────────────────────────────
    step3_path = st.path("step3.yaml", state_dir=state_dir)
    print(f"\n  Saved: {step3_path}  (sections: scalars, turnover, forecast_weights)")
    print(f"  Saved: {report_path}")

    print(f"\n  ACTION: review the tables above, then edit forecast_weights in:")
    print(f"    {step3_path}")
    print(f"  Adjust weights for correlated or expensive rules, then press Enter...")

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        print("\n  Aborted.")
        sys.exit(1)

    # ── 3e: FDM (automatic, runs after user confirms weights) ──────────────────
    print("  [3e] Computing FDM from confirmed weights...")
    rule_weights: dict[str, float] = {
        k: float(v) for k, v in st.load_section("step3.yaml", "forecast_weights", state_dir=state_dir).items()
    }
    family_scalars = st.parse_family_scalars(scalars_data, REGISTRY)

    fdms: dict[str, float] = {}
    for code in instruments:
        try:
            prices = load_adjusted_prices(code)
        except FileNotFoundError:
            continue
        is_prices, _ = split_series(prices, split_date)
        if len(is_prices) < 20:
            continue
        vol_is = daily_vol(is_prices)
        fc_is = combined_forecast(
            is_prices, vol_is, fdm=1.0,
            family_scalars=family_scalars,
            rule_weights=rule_weights,
            instrument_code=code,
        )
        rule_cols = [c for c in fc_is.columns if c != "combined"]
        fdms[code] = calibrate_fdm(fc_is[rule_cols], rule_weights=rule_weights)

    st.save_section("step3.yaml", "fdm",
                    {code: round(fdm, 4) for code, fdm in fdms.items()},
                    state_dir=state_dir)

    fw = max(len(c) for c in fdms) + 2 if fdms else 14
    print(f"\n  {'Instrument':<{fw}} {'FDM':>6}")
    print(f"  {'─' * (fw + 8)}")
    for code, fdm in fdms.items():
        print(f"  {code:<{fw}} {fdm:>6.3f}")
    print(f"\n  Saved: {step3_path}  (sections: scalars, turnover, forecast_weights, fdm)")

    return {
        "state": str(step3_path),
        "report": str(report_path),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 3: Rule calibration")
    parser.add_argument("--system", type=str, default="systems/universe_v4",
                        metavar="PATH", help="System directory (default: systems/universe_v4)")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    system_dir = root / args.system
    set_config(system_dir / "config")
    main(state_dir=system_dir / "config", report_dir=system_dir / "results")

"""
Correlation analysis across instruments and rules over the dev period.

Outputs:
  1. Instrument return correlations
  2. Rule forecast correlations (pooled across instruments)
  3. Per-instrument: rule vs rule correlation summary
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtest.config import set_config, load_instrument_configs, load_rules_config, traded_instruments
from src.data.pst_writer import load_adjusted_prices
from src.rules.registry import REGISTRY
from src.rules.vol import daily_vol
from src.rules.combine import combined_forecast

CONFIG = "config/dev_2011_2018_xau.yaml"
# Use full dev window for correlation analysis
START = "2011-01-01"
END   = "2018-01-01"


def fmt_corr_matrix(df: pd.DataFrame, title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")
    cols = df.columns.tolist()
    w = max(len(c) for c in cols)
    header = f"  {' ' * w}" + "".join(f"  {c[:6]:>6}" for c in cols)
    print(header)
    print(f"  {'─' * (len(header) - 2)}")
    for row in cols:
        line = f"  {row:<{w}}"
        for col in cols:
            v = df.loc[row, col]
            if row == col:
                line += f"  {'─':>6}"
            else:
                line += f"  {v:>6.2f}"
        print(line)


def main() -> None:
    set_config(CONFIG)
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules = load_rules_config()

    # ── 1. Instrument return correlations ────────────────────────────────────
    ret_dict: dict[str, pd.Series] = {}
    for code in instruments:
        p = load_adjusted_prices(code)[START:END]
        ret_dict[code] = p.pct_change().dropna()

    ret_df = pd.DataFrame(ret_dict).dropna()
    inst_corr = ret_df.corr().round(2)
    fmt_corr_matrix(inst_corr, "Instrument return correlations (2011–2018)")

    # ── 2. Rule forecast correlations — pooled across instruments ────────────
    # Collect per-instrument forecast DataFrames, then average correlations
    all_rule_corrs: list[pd.DataFrame] = []
    for code in instruments:
        p = load_adjusted_prices(code)[START:END]
        vol = daily_vol(p)
        family_scalars = {block: None for block in rules}
        fc = combined_forecast(p, vol, fdm=1.0, family_scalars=family_scalars)
        rule_cols = [c for c in fc.columns if c != "combined"]
        fc_rules = fc[rule_cols].dropna()
        if len(fc_rules) > 30:
            all_rule_corrs.append(fc_rules.corr())

    if all_rule_corrs:
        pooled_rule_corr = pd.concat(all_rule_corrs).groupby(level=0).mean().round(2)
        fmt_corr_matrix(pooled_rule_corr, "Rule forecast correlations — pooled across instruments")

    # ── 3. Family-level summary: avg intra-family and inter-family corr ──────
    families: dict[str, list[str]] = {}
    for block_name, block_cfg in rules.items():
        handler = REGISTRY.get(block_name)
        if handler is None:
            continue
        variants = handler.variants_from_cfg(block_cfg)
        names = [handler.rule_name(v) for v in variants]
        families[block_name] = names

    if all_rule_corrs and len(pooled_rule_corr) > 0:
        print(f"\n{'═' * 60}")
        print("  Family-level average correlations (pooled)")
        print(f"{'═' * 60}")
        family_names = list(families.keys())
        w = max(len(n) for n in family_names)
        header = f"  {' ' * w}" + "".join(f"  {n[:8]:>8}" for n in family_names)
        print(header)
        print(f"  {'─' * (len(header) - 2)}")
        for fa in family_names:
            line = f"  {fa:<{w}}"
            for fb in family_names:
                rows_a = [r for r in families[fa] if r in pooled_rule_corr.index]
                cols_b = [c for c in families[fb] if c in pooled_rule_corr.columns]
                if not rows_a or not cols_b:
                    line += f"  {'n/a':>8}"
                    continue
                sub = pooled_rule_corr.loc[rows_a, cols_b]
                if fa == fb:
                    # intra: average of off-diagonal
                    mask = np.ones(sub.shape, dtype=bool)
                    np.fill_diagonal(mask, False)
                    vals = sub.values[mask]
                else:
                    vals = sub.values.flatten()
                avg = float(np.nanmean(vals)) if len(vals) > 0 else float("nan")
                line += f"  {avg:>8.2f}"
            print(line)

    # ── 4. Cross-instrument correlation for each rule family ─────────────────
    print(f"\n{'═' * 60}")
    print("  Cross-instrument correlation per rule family")
    print("  (avg corr of same rule applied to different instrument pairs)")
    print(f"{'═' * 60}")
    for block_name, block_cfg in rules.items():
        handler = REGISTRY.get(block_name)
        if handler is None:
            continue
        variants = handler.variants_from_cfg(block_cfg)
        for variant in variants:
            rule_name = handler.rule_name(variant)
            series_by_inst: dict[str, pd.Series] = {}
            for code in instruments:
                p = load_adjusted_prices(code)[START:END]
                vol = daily_vol(p)
                raw = handler.compute_one_raw(p, variant, vol)
                series_by_inst[code] = raw
            df_v = pd.DataFrame(series_by_inst).dropna()
            if df_v.shape[1] < 2 or len(df_v) < 30:
                continue
            c = df_v.corr().values
            mask = np.triu(np.ones_like(c, dtype=bool), k=1)
            avg_cross = float(np.nanmean(c[mask]))
            print(f"  {rule_name:<20}  avg cross-instrument corr: {avg_cross:+.3f}")


if __name__ == "__main__":
    main()

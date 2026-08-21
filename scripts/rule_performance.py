"""
Per-rule Sharpe attribution over the dev period.

For each rule, computes: forecast × next-day return, annualised Sharpe,
hit-rate, and avg forecast magnitude. Pooled across instruments.

Shows both individual rules and family-level aggregates.
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

CONFIG  = "config/dev_2011_2018_no_metals.yaml"
START   = "2011-01-01"
END     = "2018-01-01"
BARS_PA = 256


def rule_sharpe(fc: pd.Series, ret: pd.Series) -> tuple[float, float, float]:
    """Return (sharpe, hit_rate, mean_abs_fc) for one rule on one instrument."""
    aligned = pd.concat([fc, ret], axis=1).dropna()
    if len(aligned) < 30:
        return float("nan"), float("nan"), float("nan")
    f, r = aligned.iloc[:, 0], aligned.iloc[:, 1]
    pnl = f * r
    sr = float(pnl.mean() / pnl.std() * np.sqrt(BARS_PA)) if pnl.std() > 0 else 0.0
    hit = float((pnl > 0).mean())
    maf = float(f.abs().mean())
    return sr, hit, maf


def main() -> None:
    set_config(CONFIG)
    cfgs = load_instrument_configs()
    instruments = traded_instruments(cfgs)
    rules = load_rules_config()

    # family membership
    families: dict[str, str] = {}
    for block_name, block_cfg in rules.items():
        handler = REGISTRY.get(block_name)
        if handler is None:
            continue
        for v in handler.variants_from_cfg(block_cfg):
            families[handler.rule_name(v)] = block_name

    # collect per-rule metrics across instruments
    records: list[dict] = []
    for code in instruments:
        p = load_adjusted_prices(code)[START:END]
        ret = p.pct_change().shift(-1)  # next-bar return
        vol = daily_vol(p)

        for block_name, block_cfg in rules.items():
            handler = REGISTRY.get(block_name)
            if handler is None:
                continue
            for variant in handler.variants_from_cfg(block_cfg):
                rname = handler.rule_name(variant)
                raw = handler.compute_one_raw(p, variant, vol)
                fc  = raw.clip(-20, 20)
                sr, hit, maf = rule_sharpe(fc, ret)
                records.append({
                    "rule": rname,
                    "family": block_name,
                    "instrument": code,
                    "sharpe": sr,
                    "hit_rate": hit,
                    "mean_abs_fc": maf,
                })

    df = pd.DataFrame(records)

    # ── Per-rule summary (pooled across instruments) ─────────────────────────
    rule_agg = (
        df.groupby(["family", "rule"])
        .agg(sharpe=("sharpe", "mean"), hit=("hit_rate", "mean"), maf=("mean_abs_fc", "mean"))
        .reset_index()
        .sort_values("sharpe", ascending=False)
    )

    print(f"\n{'═' * 65}")
    print("  Per-rule Sharpe attribution  (pooled across 7 instruments, 2011-2018)")
    print(f"{'═' * 65}")
    print(f"  {'Rule':<20} {'Family':<12} {'SR':>6}  {'Hit%':>5}  {'Avg|fc|':>7}")
    print(f"  {'─' * 55}")
    for _, row in rule_agg.iterrows():
        print(f"  {row['rule']:<20} {row['family']:<12} "
              f"{row['sharpe']:>6.2f}  {row['hit']:>5.1%}  {row['maf']:>7.2f}")

    # ── Family summary ───────────────────────────────────────────────────────
    fam_agg = (
        df.groupby("family")
        .agg(sharpe=("sharpe", "mean"), hit=("hit_rate", "mean"))
        .sort_values("sharpe", ascending=False)
    )
    print(f"\n{'═' * 40}")
    print("  Family averages")
    print(f"{'═' * 40}")
    print(f"  {'Family':<15} {'SR':>6}  {'Hit%':>5}")
    print(f"  {'─' * 30}")
    for fam, row in fam_agg.iterrows():
        print(f"  {fam:<15} {row['sharpe']:>6.2f}  {row['hit']:>5.1%}")

    # ── Per-instrument breakdown per family ──────────────────────────────────
    print(f"\n{'═' * 65}")
    print("  Per-instrument × family Sharpe")
    print(f"{'═' * 65}")
    pivot = (
        df.groupby(["instrument", "family"])["sharpe"]
        .mean()
        .unstack("family")
        .round(2)
    )
    families_ordered = list(fam_agg.index)
    pivot = pivot[families_ordered]
    pivot["TOTAL"] = pivot.mean(axis=1).round(2)
    pivot = pivot.sort_values("TOTAL", ascending=False)

    col_w = max(len(c) for c in pivot.columns) + 2
    header = f"  {'Instrument':<12}" + "".join(f"  {c:>{col_w}}" for c in pivot.columns)
    print(header)
    print(f"  {'─' * (len(header) - 2)}")
    for inst, row in pivot.iterrows():
        line = f"  {inst:<12}"
        for c in pivot.columns:
            v = row[c]
            line += f"  {v:>{col_w}.2f}"
        print(line)


if __name__ == "__main__":
    main()

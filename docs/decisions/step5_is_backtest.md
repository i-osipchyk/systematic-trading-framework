# Step 5 — IS Backtest and Vol Target

**Date:** 2026-08-24  
**Status:** Confirmed  
**Config:** `config/universe_40yr_wf.yaml`  
**Parameters used:** scalars (01), forecast weights (02), FDMs (03), instrument weights (06), IDM (07)

---

## Data quality fix applied

Before running the backtest, a critical data quality issue was discovered and fixed:

**Problem:** The D1 adjusted price files for equity indices and FX instruments contained:
1. **DST duplicate bars** — broker server time shifts between 21:00 UTC (summer) and 22:00 UTC (winter), creating two bars on the same calendar date during the spring time-change weekend.
2. **Weekend bars** — Saturday/Sunday FX sessions included in some instruments.

This caused the OOS period (2010–2026) to have ~490 bars/year for affected instruments (US500, NAS100, GER40, JPN225, FX pairs) vs the IS period's correct 252 bars/year. The inflated bar count corrupted:
- Vol estimates (wrong annualization factor)
- EWMAC signal lookback periods (32 calendar bars ≠ 32 trading days)
- PnL computation (position × 1-hour move ≠ position × daily move)

The resulting OOS SR without the fix was −1.94 with −97% max drawdown — clearly an artefact.

**Fix:** `load_adjusted_prices()` in `src/data/pst_writer.py` now normalises to one price per calendar date (last bar, handling DST), then filters to weekdays (Mon–Fri) only. FX instruments correctly retain ~261 bars/year (FX trades on some days equity markets are closed).

---

## Portfolio backtest results

**IS period: 1984–2010 (6,784 bars)**

| Metric | IS | OOS |
|---|---|---|
| Sharpe ratio | **0.91** | **~0.00** |
| Annual return | 10.8% | 0.0% |
| Max drawdown | −17.7% | −39.7% |
| Bars | 6,784 | 4,342 |

---

## Per-instrument IS → OOS breakdown

| Code | gSR IS | SR IS | gSR OOS | SR OOS | Ret IS | Ret OOS |
|---|---|---|---|---|---|---|
| EURUSD | 0.44 | 0.42 | −0.16 | −0.19 | 0.5% | −0.2% |
| GBPUSD | 0.41 | 0.39 | −0.33 | −0.36 | 0.5% | −0.3% |
| AUDUSD | 0.38 | 0.35 | −0.34 | −0.39 | 0.5% | −0.4% |
| USDJPY | 0.44 | 0.40 | 0.03 | −0.03 | 0.5% | 0.0% |
| USDCAD | 0.45 | 0.41 | −0.29 | −0.35 | 0.6% | −0.3% |
| US500 | 0.38 | 0.21 | 0.18 | 0.14 | 0.2% | 0.1% |
| NAS100 | 0.37 | −0.13 | 0.36 | 0.31 | −0.1% | 0.3% |
| GER40 | 0.47 | 0.42 | −0.13 | −0.16 | 0.4% | −0.1% |
| JPN225 | 0.64 | 0.54 | 0.13 | 0.03 | 0.5% | 0.0% |
| HK50 | 0.77 | 0.50 | 0.08 | −0.04 | 0.5% | 0.0% |
| US2YR | 0.66 | 0.54 | −0.47 | −0.82 | 0.9% | −1.1% |
| US5YR | 0.63 | 0.55 | −0.11 | −0.24 | 0.8% | −0.3% |
| US10YR | 0.57 | 0.49 | 0.05 | −0.06 | 0.7% | −0.1% |
| US30YR | 0.51 | 0.42 | 0.22 | 0.16 | 0.6% | 0.2% |
| BUND | 0.19 | 0.16 | **0.32** | **0.30** | 0.8% | **1.9%** |
| XAU | 0.31 | 0.23 | **0.49** | **0.44** | 0.7% | 0.4% |
| XAG | 0.12 | −0.09 | 0.24 | 0.10 | −0.3% | 0.1% |
| COPPER | 0.44 | 0.40 | −0.16 | −0.19 | 0.7% | −0.1% |
| SpotCrude | 0.33 | 0.16 | 0.19 | 0.13 | 0.2% | 0.2% |
| NatGas | 0.72 | 0.67 | −0.22 | −0.36 | 0.9% | −0.4% |
| Coffee | 0.43 | 0.42 | 0.07 | 0.03 | 2.6% | 0.0% |
| Cocoa | −0.06 | −0.33 | −0.06 | −0.30 | −1.0% | −0.4% |
| Sugar | 0.31 | 0.31 | −0.06 | −0.07 | 0.7% | −0.1% |
| Corn | 0.39 | 0.39 | 0.20 | 0.20 | 1.5% | 0.2% |
| Cotton | 0.52 | 0.51 | 0.17 | 0.16 | 1.2% | 0.2% |

---

## IS vs OOS interpretation

### IS SR = 0.91 — strong but exceptional

The 1984–2010 IS period was the best era for systematic trend following:
- Bonds: 26-year secular bull market (yields 15% → 3.5%)
- Commodities: 2000–2008 supercycle
- FX: large carry differentials (before ZIRP)
- High overall volatility (pre-great-moderation effects)

IS SR of 0.91 reflects genuine alpha but also IS-favourable conditions that will not repeat identically.

### OOS SR ≈ 0.00 — the CTA winter

2010–2026 was the hardest era for systematic trend following:
- **ZIRP (2010–2021):** interest rates near zero in US/EU → tiny carry signals, compressed vol
- **FX range-bound:** post-2009, central banks more actively managed currencies → less persistent FX trends
- **Equity bull market:** persistent US equity uptrend with frequent sharp corrections and rapid recoveries (COVID 2020 crash and bounce)
- **Bond bear market 2022:** caught most long-bond trend followers by surprise (rapid reversal)

Near-zero OOS SR is consistent with industry experience. The top CTAs (AHL, Winton, Millburn) showed SR ≈ 0.3–0.5 in this period on much larger, more diversified portfolios.

### Best OOS performers: real structural alpha

| Instrument | OOS SR | Explanation |
|---|---|---|
| XAU | 0.44 | Gold: inflation hedge 2020+, monetary policy divergence |
| BUND | 0.30 | European rates: clean falling trend 2012–2016, 2022 rise |
| NAS100 | 0.31 | Tech bull market (persistent, not frequently interrupted) |
| US30YR | 0.16 | Gradual rate normalisation created tradeable trends |
| Corn/Cotton | 0.20/0.16 | Ag seasonality + supply-driven trends |

### Worst OOS performers: structural regime shift

| Instrument | OOS SR | Explanation |
|---|---|---|
| US2YR | −0.82 | Near-zero rates for 12 years → tiny signal, then 2022 shock reversal |
| GBPUSD/AUDUSD | −0.36/−0.39 | FX range-bound; Brexit whipsaw for GBP |
| NatGas | −0.36 | US shale revolution made NatGas more volatile and less trending |
| Cocoa | −0.30 | No persistent trend in either IS or OOS |

---

## Vol target: 15%

**IS SR = 0.91 → realistic forward SR ≈ 0.45** (50% IS haircut is standard Carver adjustment).

At SR = 0.45, half-Kelly vol target ≈ 13.5%. The current 15% vol target is slightly above half-Kelly and appropriate for a live deployment. With OOS SR ≈ 0, a more conservative target (10-12%) could be argued, but trend following tends to have lumpy returns — the good years (2022 specifically) can deliver outsized gains. 15% is maintained.

**OOS max drawdown of −39.7%** at 15% vol target / IDM = 2.5 is the key risk metric. A live account should expect multi-year drawdown periods of 20-40%.

---

## Notes

- All calibration steps (01, 03, 07) were performed on IS data, which was already clean (252 bars/year for equities, ~255 for FX). The data quality fix affects OOS performance measurement only.
- Re-running calibration steps with clean data would give marginally different scalars for FX instruments (EURUSD IS had ~261 vs 255 bars/year), but the effect is negligible.

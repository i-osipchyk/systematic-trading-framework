# Build v3 — Step 3: Forecast Scalars, Correlations, Cost Filter, Weights, FDM

**Date:** 2026-08-25
**Status:** Complete
**Config:** `config/universe_v3.yaml`
**State files:** `calibrate/state/step3a_scalars.yaml`, `step3c_turnover.yaml`, `step3d_forecast_weights.yaml`, `step3d_fdm.yaml`

---

## Step 3a — Forecast scalars

IS pooled mean absolute forecast (MAF) and resulting scalars, computed on IS data (pre-2010-01-01), pooled across 23 instruments:

| Rule | Raw MAF | Scalar |
|---|---|---|
| EWMAC_4_16 | 1.011 | 9.89 |
| EWMAC_8_32 | 1.563 | 6.40 |
| EWMAC_16_64 | 2.434 | 4.11 |
| EWMAC_32_128 | 3.774 | 2.65 |
| EWMAC_64_256 | 5.484 | 1.82 |

Seasonality: fitted per-instrument (monthly mean returns scaled to MAF = 10). All 23 instruments calibrated. Raw seasonal MAF ranged from 0.27 (XAU) to 0.60 (SpotCrude, US5YR) — all instruments show some monthly variation in IS data.

**Candidates also calibrated but later pruned (Step 3b):** EWMAC_2_8 (scalar 14.97), BREAKOUT_20/50/100/200 (scalars 11.47–15.86), TSMOM_63/126/252 (scalars 114.96–52.59). Note: TSMOM scalars are very large because raw price returns are a tiny fraction of vol-normalised EWMAC values — the rule is not inherently more reliable despite the large scalar.

---

## Step 3b — Rule correlation matrix and pruning

Pooled IS forecast correlation matrix (23 instruments). Key results:

**Trend vs. Seasonality:** 0.02–0.15 — orthogonal. Seasonality confirmed as a genuinely independent family.

**Trend within-family:** Adjacent EWMAC speeds 0.86–0.88; EWMAC_4_16 ↔ EWMAC_64_256 = 0.18. The timescale spread within EWMAC alone provides all within-trend diversification.

**Breakout vs. matched EWMAC:** 0.88–0.90 — above the 0.80 structural redundancy threshold at every timescale. Dropped.

**TSMOM vs. matched EWMAC:** 0.84–0.85 — also above threshold at matched timescales. Dropped.

**EWMAC_2_8 vs. EWMAC_4_16:** 0.87 — redundant with its neighbour. Dropped (also fails cost, see below).

**Final rule set:** EWMAC_4_16, EWMAC_8_32, EWMAC_16_64, EWMAC_32_128, EWMAC_64_256, SEASONALITY.

---

## Step 3c — Cost filter

IS turnover pooled across 23 instruments and cost ceilings (0.13 / turnover):

| Rule | Turnover (rt/yr) | Max std cost |
|---|---|---|
| EWMAC_4_16 | 23.7 | 0.0055 |
| EWMAC_8_32 | 12.7 | 0.0102 |
| EWMAC_16_64 | 9.7 | 0.0135 |
| EWMAC_32_128 | 8.2 | 0.0159 |
| EWMAC_64_256 | 7.5 | 0.0172 |
| SEASONALITY | 9.9 | 0.0131 |

**EWMAC_4_16 (ceiling 0.0055):** Tight. High-cost instruments — Cocoa (spread 5.0 on 10pt contract) and XAG (spread 0.02 on 5000pt) — may fail this ceiling. Uniform weights are kept; per-instrument cost check recommended at Step 4.

**EWMAC_8_32 and slower:** All 23 instruments expected to pass the ceiling.

**Seasonality (ceiling 0.0131):** All instruments pass.

**Pruned candidates (for reference):** EWMAC_2_8 turnover 47.8 → ceiling 0.0027 — near-impossible to clear for any instrument. Confirms EWMAC_2_8 exclusion.

---

## Step 3d — Forecast weights and FDM

**Forecast weights (uniform across all 23 instruments):**

| Rule | Weight |
|---|---|
| EWMAC_4_16 | 10% |
| EWMAC_8_32 | 10% |
| EWMAC_16_64 | 10% |
| EWMAC_32_128 | 10% |
| EWMAC_64_256 | 10% |
| SEASONALITY | 50% |

Family split: Trend 50% / Seasonality 50%. Seasonality gets equal budget to the entire trend family, reflecting its orthogonality (0.02–0.15 cross-family correlation) and universal coverage.

**Per-instrument FDM:**

| Instrument | FDM | | Instrument | FDM |
|---|---|---|---|---|
| US500 | 1.484 | | SpotCrude | 1.472 |
| NAS100 | 1.518 | | Gasoline | 1.396 |
| GER40 | 1.466 | | Coffee | 1.504 |
| JPN225 | 1.449 | | Cocoa | 1.518 |
| HK50 | 1.496 | | Sugar | 1.502 |
| UK100 | 1.526 | | Corn | 1.436 |
| US2YR | 1.451 | | Cotton | 1.496 |
| US5YR | 1.444 | | Soybeans | 1.453 |
| US10YR | 1.457 | | Wheat | 1.484 |
| US30YR | 1.464 | | XAU | 1.497 |
| BUND | 1.446 | | XAG | 1.536 |
| COPPER | 1.489 | | | |

FDMs cluster in a narrow 1.40–1.54 range — a direct consequence of the uniform rule set. All instruments have the same six rules; the slight variation reflects instrument-specific correlation between their EWMAC signals and seasonality.

Gasoline (1.40) is lowest — its seasonal demand pattern (driving season) partially overlaps with crude trending behaviour. XAG (1.54) is highest — silver's seasonal signal is more independent from its trend signal.

No FDM exceeds 2.5 (Carver's cap). All values uncapped.

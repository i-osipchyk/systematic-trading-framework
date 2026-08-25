# Step 2 — Rule Selection

**Date:** 2026-08-25
**Status:** Confirmed — final rule set after Step 3b correlation analysis
**Config:** `config/universe_v2.yaml`

---

## Discipline

Start broad, prune by structural redundancy — never by performance.

Drop a rule family only if:
- Its correlation with another family exceeds ~0.8 across the portfolio (structural redundancy)
- No instrument in the universe survives the Step 3c cost filter

Do not drop based on backtested SR. Rules with similar SR but lower inter-family correlation add more portfolio value in combination than rules with better SR but high correlation.

Final weights and pruning decisions come from the Step 3b correlation matrix — not from this step.

---

## Rule families

### Trend family — EWMAC, Breakout, TSMOM

All three express the same underlying hypothesis (price momentum persists) but via structurally different algorithms:

**EWMAC** (exponentially-weighted crossover): vol-normalised, exponentially weighted, responds continuously to new price information. The slow EMA effectively integrates all past prices with exponential decay.

**Breakout** (Donchian channel): position of current price within the N-day high-low channel. Normalised by channel width (not vol). More binary — rapidly moves to ±1 when a new N-day high/low is made. Responds to price level extremes, not to the shape of the price path.

**TSMOM** (time-series momentum): raw N-bar total return, unweighted and not vol-normalised. Captures the cumulative directional drift over the lookback period. Unlike EWMAC, equally weights all returns in the window; unlike Breakout, is sensitive to the magnitude of moves, not just their position in the range.

Expected within-trend correlations: 0.5–0.75 between EWMAC and Breakout or TSMOM at similar timescales; higher within the same algorithm family. All three form one trend meta-family. Step 3b will determine whether they are sufficiently decorrelated within the family to warrant separate sub-family weights, or whether EWMAC alone captures the signal adequately.

**Mean reversion excluded:** at the same timescale as trend rules, MR correlation with trend is approximately −0.9 — cancellation, not diversification. Excluded from the candidate set.

### Carry family

Interest-rate or term-structure differential signal. Structurally orthogonal to price momentum (0.0–0.2 cross-family correlation empirically). Applied selectively:

| Instruments | Carry signal | Notes |
|---|---|---|
| FX (5 pairs) | Policy rate differential between currency legs | Clean signal; rates data in data/rates/policy_rates.csv |
| Bonds (5 instruments) | Yield-to-maturity / roll-down carry | Clean signal; data/rates/bond_yields.csv |
| Energy, Ags | Calendar spread (backwardation/contango) | Usable but noisier |
| Equities (6) | Dividend yield minus funding rate | Weak, marginal; excluded |
| Metals (3) | Lease rate / storage cost | Hard to measure for CFDs; excluded |

**Carry is not applied to equities or metals.**

### Seasonality family

Calendar-driven signal, decorrelated from trend and carry by construction (no price information, no rate information). Applied only where documented supply/demand cycles exist:

- **Ags (7 instruments):** planting/harvest calendar effects. Corn, Soybeans, and Wheat have US crop-year cycles; Coffee, Cocoa, and Sugar have tropical harvest cycles; Cotton has US planting cycle.
- **Energy (2 instruments):** seasonal demand patterns (Gasoline: driving season; SpotCrude: winter heating + driving season).

Not applied to FX, bonds, equities, or metals (no structural calendar driver).

---

## Candidate rule set for Step 3

### Trend sub-candidates

| Rule | Lookback / speed | Approx timescale |
|---|---|---|
| EWMAC_2_8 | fast | 1–2 weeks |
| EWMAC_4_16 | fast | 2–4 weeks |
| EWMAC_8_32 | fast-medium | 4–8 weeks |
| EWMAC_16_64 | medium | 2–4 months |
| EWMAC_32_128 | medium-slow | 4–6 months |
| EWMAC_64_256 | slow | 6–12 months |
| BREAKOUT_20 | ~1 month | matches EWMAC_4_16 timescale |
| BREAKOUT_50 | ~2.5 months | between EWMAC_8_32 and EWMAC_16_64 |
| BREAKOUT_100 | ~5 months | between EWMAC_16_64 and EWMAC_32_128 |
| BREAKOUT_200 | ~10 months | matches EWMAC_64_256 timescale |
| TSMOM_63 | 3 months | matches EWMAC_16_64 |
| TSMOM_126 | 6 months | between EWMAC_32_128 and EWMAC_64_256 |
| TSMOM_252 | 12 months | matches EWMAC_64_256 |

**Design notes:**
- Very fast Breakout/TSMOM variants (sub-20 bars) excluded: high turnover fails cost filter for most instruments; signal too noisy.
- The slow end (TSMOM_252, BREAKOUT_200, EWMAC_64_256) represents three algorithms at the same ~12-month timescale. Step 3b will show their mutual correlation — if all three are 0.85+, one or two can be dropped without loss.
- EWMAC_2_8 and EWMAC_4_16 have no Breakout/TSMOM equivalents at that timescale — they are unique in the candidate set.

### Carry

Single carry rule per applicable instrument. Step 3a calibrates the scalar; Step 3b includes carry in the correlation matrix.

### Seasonality

Single seasonality rule per applicable instrument (instrument-specific monthly scalars calibrated in Step 3a).

---

## Per-instrument-type weight structure (for Step 3d)

Different weight vectors are assigned by instrument type. Carry and seasonality receive nonzero weight only where applicable. FDM corrects for within-group correlation per instrument.

| Instrument type | Instruments | Rule families |
|---|---|---|
| Equities | US500, NAS100, GER40, JPN225, HK50, UK100 | Trend only |
| Metals | XAU, XAG, COPPER | Trend only |
| FX | AUDUSD, GBPUSD, USDCAD, USDJPY, EURUSD | Trend + Carry |
| Bonds | US2YR, US5YR, US10YR, US30YR, BUND | Trend + Carry |
| Energy | SpotCrude, Gasoline | Trend + Seasonality |
| Ags | Coffee, Cocoa, Sugar, Corn, Soybeans, Wheat, Cotton | Trend + Seasonality |

Starting top-level family split for two-family instruments: 50% Trend / 50% Carry or Seasonality. Step 3b may revise this based on measured cross-family correlations.

Within-trend weights and which trend sub-candidates to keep are determined entirely by Step 3b.

---

## Step 3b outcome — Breakout and TSMOM dropped

Pooled IS forecast correlation matrix (29 instruments, IS to 2010-01-01):

- EWMAC_N ↔ BREAKOUT at matched timescale: **0.85–0.90** — structurally redundant
- EWMAC_N ↔ TSMOM at matched timescale: **0.85–0.86** — structurally redundant
- EWMAC_2_8 ↔ EWMAC_64_256: **0.10** — the timescale spread within EWMAC alone provides all within-trend diversification needed

Breakout and TSMOM were dropped. Adding them would triple the complexity of the trend family for near-zero additional diversification benefit. The 6 EWMAC speeds span the full timescale range independently.

Carry: corr with trend = −0.04 to +0.08 (orthogonal). Seasonality: corr with trend = −0.04 to +0.18 (orthogonal). Both retained.

## Final rule set

- **Trend**: EWMAC_4_16, EWMAC_8_32, EWMAC_16_64, EWMAC_32_128, EWMAC_64_256 (EWMAC_2_8 dropped: corr 0.87 with EWMAC_4_16; fails cost ceiling for 11/27 instruments)
- **Carry**: FX (5) and Bonds (5) only
- **Seasonality**: Ags (7) and Energy (2) only

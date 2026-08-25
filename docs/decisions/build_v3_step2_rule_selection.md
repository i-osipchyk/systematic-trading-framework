# Build v3 — Step 2: Rule Selection

**Date:** 2026-08-25
**Status:** Candidate set confirmed — Step 3b correlation analysis pending
**Config:** `config/universe_v3.yaml`

---

## Discipline

Start broad, prune by structural redundancy — never by performance.

Drop a rule family only if:
- Its correlation with another family exceeds ~0.8 across the portfolio (structural redundancy)
- No instrument in the universe survives the Step 3c cost filter

Do not drop based on backtested SR. Rules with similar SR but lower inter-family correlation add more portfolio value in combination than rules with better SR but high correlation.

Final weights and within-family pruning decisions come from the Step 3b correlation matrix — not from this step.

---

## Design principle: uniform rule set

v3 applies the same two rule families to every instrument — Trend + Seasonality. No per-instrument-type switching. This makes the system fully consistent: the IS monthly scalars determine where seasonal signal exists; instruments with no genuine seasonal pattern produce near-zero scalars and the rule contributes negligibly after FDM adjustment. The data decides, not the designer.

Carry is excluded entirely from this build. Bond carry was the only remaining carry host after FX was removed from the universe. With a single asset class left, carry becomes a more concentrated bet than a diversifying family. Excluding it keeps the rule set clean and symmetric.

---

## Rule families

### Trend family — EWMAC, Breakout, TSMOM

All three express the same underlying hypothesis (price momentum persists) via structurally different algorithms:

**EWMAC** (exponentially-weighted crossover): vol-normalised, exponentially weighted, responds continuously to new price information. The slow EMA integrates all past prices with exponential decay.

**Breakout** (Donchian channel): position of current price within the N-day high-low channel. Normalised by channel width, not vol. More binary — moves rapidly to ±1 when a new N-day high/low is made. Responds to price level extremes, not to the shape of the price path.

**TSMOM** (time-series momentum): raw N-bar total return, unweighted and not vol-normalised. Captures cumulative directional drift over the lookback period. Unlike EWMAC, equally weights all returns in the window; unlike Breakout, is sensitive to move magnitude, not just position in the range.

Expected within-trend correlations: 0.5–0.75 between EWMAC and Breakout or TSMOM at similar timescales. All three form one trend meta-family. Step 3b will determine whether they are sufficiently decorrelated to warrant separate sub-family weights, or whether EWMAC alone captures the trend signal adequately.

**Mean reversion excluded:** at the same timescale as trend rules, MR correlation with trend is approximately −0.9 — cancellation, not diversification.

### Seasonality family

Calendar-driven signal, decorrelated from trend by construction (uses no price information). Applied uniformly to all 23 instruments.

Documented seasonal patterns by asset class:
- **Ags**: planting/harvest calendar effects (Corn/Soybeans/Wheat US crop-year; Coffee/Cocoa/Sugar tropical harvest cycles; Cotton US planting cycle)
- **Energy**: seasonal demand (Gasoline: driving season; SpotCrude: winter heating + driving season)
- **Equities**: Halloween effect (Nov–Apr outperformance), January effect, tax-year variation by index geography
- **Metals**: Gold — Indian wedding season, Chinese New Year demand; Copper — construction cycle (spring pickup, winter slowdown); Silver — industrial demand cycle
- **Bonds**: issuance-driven supply seasonality, tax-loss effects (signal expected to be weak; scalars will reflect this)

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

Very fast Breakout/TSMOM variants (sub-20 bars) excluded: high turnover fails cost filter for most instruments. The slow end (TSMOM_252, BREAKOUT_200, EWMAC_64_256) represents three algorithms at the same ~12-month timescale — Step 3b will determine if they are sufficiently decorrelated to keep all three.

### Seasonality

Single seasonality rule per instrument — instrument-specific monthly scalars calibrated at Step 3a (per-month IS mean return, scaled to mean absolute = 10).

---

## Per-instrument weight structure (for Step 3d)

Uniform across all 23 instruments: **Trend + Seasonality**.

Starting top-level family split: 50% Trend / 50% Seasonality. Step 3b will revise based on measured cross-family correlations. Within-trend weights and which trend sub-candidates to retain are determined entirely by Step 3b.

---

## Step 3b outcome

Pooled IS forecast correlation matrix (23 instruments, IS to 2010-01-01):

**Within-trend correlations at matched timescales:**

| Rule pair | Corr |
|---|---|
| EWMAC_2_8 ↔ EWMAC_4_16 | 0.87 |
| EWMAC_4_16 ↔ BREAKOUT_20 | 0.89 |
| EWMAC_8_32 ↔ BREAKOUT_50 | 0.90 |
| EWMAC_16_64 ↔ BREAKOUT_100 | 0.90 |
| EWMAC_32_128 ↔ BREAKOUT_200 | 0.89 |
| EWMAC_16_64 ↔ TSMOM_63 | 0.85 |
| EWMAC_32_128 ↔ TSMOM_126 | 0.85 |
| EWMAC_64_256 ↔ TSMOM_252 | 0.84 |

**Timescale spread within EWMAC:**

| Rule pair | Corr |
|---|---|
| EWMAC_4_16 ↔ EWMAC_64_256 | 0.18 |

Adjacent EWMAC speeds: 0.86–0.88. The full timescale range (4_16 to 64_256) spans from 0.18 to nearly 0, providing all the within-trend diversification needed.

**Seasonality ↔ trend (across all speeds):** 0.02–0.15 — genuinely orthogonal.

**Pruning decisions:**

- **EWMAC_2_8 dropped:** 0.87 corr with EWMAC_4_16 (above 0.80 threshold); IS turnover 47.8 rt/yr gives cost ceiling 0.0027 — unusably tight for almost all instruments.
- **Breakout dropped:** 0.88–0.90 corr with matched EWMAC at every timescale — structurally redundant across the board.
- **TSMOM dropped:** 0.84–0.85 corr with matched EWMAC — also above 0.80 threshold. Lower than Breakout but still redundant; adding all three at 8% each of the 50% Trend budget would not produce meaningful diversification.
- **Seasonality retained:** 0.02–0.15 corr with all trend rules — orthogonal signal confirmed.

## Final rule set

- **Trend**: EWMAC_4_16, EWMAC_8_32, EWMAC_16_64, EWMAC_32_128, EWMAC_64_256
- **Seasonality**: all 23 instruments (universal)
- **Forecast weights**: 10% per EWMAC speed, 50% Seasonality

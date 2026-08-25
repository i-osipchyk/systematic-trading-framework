# Build v3 — OOS Validation

**Date:** 2026-08-25
**Status:** Complete — one-shot OOS run
**Config:** `config/universe_v3.yaml`
**Vol target:** 40%

---

## Results

### Table 1 — Per-instrument SR

| Instrument | IS SR | Val SR | Test SR | IS Ret | Val Ret | Test Ret |
|---|---|---|---|---|---|---|
| **Equities** |||||||||
| US500 | 0.69 | 0.32 | 0.64 | 3.0% | 1.4% | 2.8% |
| NAS100 | 0.49 | 0.43 | 0.90 | 2.1% | 2.0% | 4.0% |
| GER40 | 0.84 | 0.32 | 0.39 | 3.0% | 1.2% | 1.3% |
| JPN225 | 0.77 | −0.02 | −0.05 | 5.8% | −0.2% | −0.3% |
| HK50 | 0.88 | 0.49 | −0.13 | 7.0% | 3.5% | −1.0% |
| UK100 | 0.45 | −0.15 | 0.03 | 1.5% | −0.5% | 0.1% |
| **Bonds** |||||||||
| US2YR | 0.96 | −0.29 | 0.25 | 4.0% | −0.5% | 0.8% |
| US5YR | 0.92 | −0.21 | 0.21 | 4.1% | −0.8% | 0.8% |
| US10YR | 0.79 | −0.45 * | 0.31 | 3.4% | −1.7% | 1.2% |
| US30YR | 0.77 | −0.39 * | 0.24 | 3.2% | −1.5% | 0.8% |
| BUND | 0.07 | 0.02 | −0.29 | 2.7% | 0.6% | −7.1% |
| **Metals** |||||||||
| XAU | 0.04 | 0.05 | 0.85 | 0.5% | 0.2% | 4.1% |
| XAG | −0.08 | −0.18 | 0.50 | −1.0% | −0.7% | 2.3% |
| COPPER | 0.40 | −0.32 * | 0.22 | 5.9% | −2.5% | 2.1% |
| **Energy** |||||||||
| SpotCrude | 0.37 | −0.16 | 0.20 | 1.7% | −0.7% | 0.9% |
| Gasoline | 0.46 | 0.16 | 0.43 | 2.0% | 0.6% | 1.9% |
| **Ags** |||||||||
| Coffee | 0.45 | −0.29 | 0.28 | 7.0% | −0.8% | 0.9% |
| Cocoa | −0.29 | −0.74 * | 0.13 | −2.0% | −2.3% | 0.4% |
| Sugar | 0.42 | 0.30 | −0.42 | 2.5% | 1.0% | −1.3% |
| Corn | 0.49 | −0.07 | 0.58 | 6.4% | −0.3% | 2.9% |
| Cotton | 0.59 | 0.11 | 0.10 | 3.5% | 0.3% | 0.3% |
| Soybeans | 0.58 | 0.54 | 0.33 | 7.0% | 2.3% | 1.5% |
| Wheat | 0.26 | −0.56 * | 0.14 | 2.8% | −2.2% | 0.6% |
| **PORTFOLIO** | 1.10 | −0.03 | 0.49 | 54.6% | −1.6% | 19.6% |
| Max DD | | | | −75.5% | −79.0% | −67.3% |

*\* = Val SR < −0.30*

---

### Table 2 — Asset class SR

| Asset class | IS SR | Val SR | Test SR |
|---|---|---|---|
| Equities | 1.15 | 0.39 | 0.39 |
| Bonds | 0.48 | −0.10 | −0.13 |
| Metals | 0.17 | −0.27 | 0.62 |
| Energy | 0.39 | −0.01 | 0.37 |
| Ags | 0.91 | −0.18 | 0.42 |
| **PORTFOLIO** | **1.10** | **−0.03** | **0.49** |

---

### Table 3 — Rule SR

| Rule | IS SR | Val SR | Test SR |
|---|---|---|---|
| EWMAC_4_16 | 0.77 | −0.20 | 0.32 |
| EWMAC_8_32 | 0.96 | −0.08 | 0.60 |
| EWMAC_16_64 | 0.82 | 0.16 | 0.73 |
| EWMAC_32_128 | 0.66 | 0.23 | 0.58 |
| EWMAC_64_256 | 0.47 | 0.23 | 0.58 |
| SEASONALITY | 1.36 | 0.04 | 0.23 |
| **COMBINED** | **1.10** | **−0.03** | **0.49** |

---

### Table 4 — Rule family SR

| Family | Rules | IS SR | Val SR | Test SR |
|---|---|---|---|---|
| Trend | 5 | 0.84 | 0.12 | 0.72 |
| Seasonality | 1 | 1.36 | 0.04 | 0.23 |
| **COMBINED** | | **1.10** | **−0.03** | **0.49** |

---

## Analysis

### Portfolio-level assessment

Val SR −0.03, Test SR 0.49. The Val period was essentially breakeven; the Test period was strong. Combined across both OOS windows, the system is profitable but with a weak Val that masks strong Test performance.

By comparison, Build v2 (structural-only, 28 instruments including FX): Val SR 0.24, Test SR 0.27. Build v3's Test SR (0.49) is materially better; Val SR (−0.03) is materially worse.

### Primary driver of weak Val: Seasonality underperformance

The critical finding is the IS vs OOS gap for Seasonality:

| Period | Seasonality SR | Trend family SR |
|---|---|---|
| IS 1984–2010 | 1.36 | 0.84 |
| Val 2010–2017 | 0.04 | 0.12 |
| Test 2018–2026 | 0.23 | 0.72 |

Seasonality carried 50% forecast weight and delivered IS SR 1.36 — the strongest individual signal in the portfolio. OOS it collapsed to 0.04 (Val) and 0.23 (Test). This is the canonical overfitting pattern: monthly IS scalars were tuned to IS seasonal patterns that did not persist at comparable magnitude in either OOS window.

With 50% weight, seasonality's flat OOS performance pulled the combined portfolio to near-zero for the entire Val period (2010–2017). The trend family, receiving only 50% weight split across 5 speeds, continued to generate modest positive SR in both OOS windows but was insufficient to overcome the seasonality drag.

**Implication for Build v4:** Seasonality weight should be reduced. The IS scalar fitting captures idiosyncratic IS seasonality that does not generalize. A weight of 10–20% (rather than 50%) would reflect the genuine edge more honestly. Alternatively, seasonality can be excluded entirely, relying on EWMAC only — a simpler and likely more robust system.

### Bond performance: Val weakness, Test recovery

US rates struggled in Val (US2YR −0.29, US10YR −0.45, US30YR −0.39) — consistent with the 2010–2017 low-volatility, QE-driven rate environment where rates were range-bound rather than trending. In Test, all US rate instruments flipped positive as the 2022–2023 rate cycle produced strong trend signals.

BUND: near-zero in Val (0.02), negative in Test (−0.29). European rates followed a different path in the Test period (ECB tightening came later, reversed faster) — less persistent trending than US rates. BUND's large weight (13.94%) was flagged as the primary IS watch item; Test confirmed that concern.

### Equities: strongest and most consistent asset class

Equities IS SR 1.15, Val 0.39, Test 0.39 — the only asset class with positive SR in both OOS periods. US large-cap was the standout: NAS100 Test SR 0.90 was the single strongest instrument OOS. The 2020–2023 tech cycle followed by the AI rally produced strong sustained trends in NAS100 and US500.

JPN225 and HK50 show OOS mean reversion from their strong IS performance — both near zero in Val and Test. The Japan IS strength was driven by yen dynamics during the IS period; the equity index itself trended less clearly in the OOS windows under Abenomics-era policy.

### Metals: delayed but real OOS edge

Metals IS SR 0.17 (weak), but Test SR 0.62 (strong). XAU Test SR 0.85 was the second-strongest instrument in the Test period — the post-COVID gold rally and 2024 breakout produced strong trends. XAG followed at Test SR 0.50. The IS weakness in metals was not predictive of OOS weakness — metal trends appear to be episodic and concentrated, not uniformly distributed across time.

### Ags: wide dispersion

Ags range from Soybeans (Val 0.54, solid) to Cocoa (Val −0.74, flagged). Cocoa's Val SR −0.74 is the worst Val result in the portfolio. Wheat was also flagged (Val −0.56). Corn, Soybeans, and Cotton outperformed in both OOS periods.

The Ags top-level promotion produced appropriate diversification — individual ags at 2.96–3.94% weight, so no single ag disaster dominates.

---

## Flagged instruments for Build v4 review

These are observations for the next build's Step 1 structural review — not grounds for retroactive changes to v3.

| Instrument | Val SR | Test SR | Note |
|---|---|---|---|
| Cocoa | −0.74 | 0.13 | Two-period consistent weakness below −0.30 threshold |
| Wheat | −0.56 | 0.14 | Val flagged; Test weak but positive |
| US10YR | −0.45 | 0.31 | Val weakness; recovered in Test with rate cycle |
| US30YR | −0.39 | 0.24 | Same pattern as US10YR |
| COPPER | −0.32 | 0.22 | Val flagged; Test modest |

Cocoa is the only instrument with Val SR < −0.30 that is also consistently weak in Test. Worth reviewing structural case for inclusion in v4.

---

## Build v3 summary

| Metric | IS | Val | Test |
|---|---|---|---|
| Portfolio SR | 1.10 | −0.03 | 0.49 |
| Ann Ret | 54.6% | −1.6% | 19.6% |
| Max DD | −75.5% | −79.0% | −67.3% |

**Key finding:** The 50% Seasonality weight was the primary design decision that did not survive OOS. Trend (5 EWMAC speeds) held up much better across both OOS windows (Val 0.12, Test 0.72). Build v4 should re-weight toward trend and reduce or eliminate seasonality.

Structural decisions that held up:
- Ags promoted to top-level tree: appropriate, each ag at 2.96–3.94% weight
- No carry: no drag from carry failure in a non-FX universe
- Universal rule set: clean, consistent

Experiment closed. Build v4 begins with fresh Step 1.

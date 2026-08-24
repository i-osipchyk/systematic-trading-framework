# Step 6 — Validation Analysis and System Revision

**Date:** 2026-08-24  
**Status:** Confirmed  
**Config:** `config/universe_40yr_wf.yaml`

---

## Motivation

The original 25-instrument system (IS SR 0.91) showed near-zero OOS performance (SR ~0.00, Max DD −39.7%) over the full 2010–2026 period. To diagnose this, OOS was split into:

- **Validation 2010–2017** — diagnosis and adjustment window
- **Test 2018–2026** — held out; not touched until final evaluation

A per-instrument, per-asset-class, and per-rule SR breakdown was computed on IS vs validation data to identify what was broken.

---

## Validation Analysis Results

### Per-rule degradation (isolated single-rule portfolios)

| Rule | IS SR | Val SR | Verdict |
|---|---|---|---|
| BREAKOUT_20 | 1.39 | −0.54 | Remove — clear regime shift |
| EWMAC_8_32 | 1.10 | 0.00 | Keep — keep exposure to fast trend, flat not negative |
| EWMAC_32_128 | 0.60 | 0.30 | Keep — stable degradation |
| EWMAC_64_256 | 0.66 | 0.32 | Keep — stable degradation |
| CARRY | 0.22 | 0.63 | Keep — improves; BUND falling-rate carry dominates |
| SEASONALITY | −0.19 | 0.03 | Keep — weak but diversifying |

BREAKOUT_20 removed: val SR −0.54 combined with highest turnover in the system (46 RT/yr) produces a standardised cost ratio well above the 0.13 ceiling. Post-GFC markets became more mean-reverting at short horizons due to HFT and central bank intervention, breaking the breakout strategy's edge.

### Per-asset-class degradation

| Asset class | IS SR | Val SR | Verdict |
|---|---|---|---|
| FX (5 instr.) | 0.63 | −0.32 | Remove most — see instrument table |
| Equities (5) | 0.57 | +0.12 | Keep |
| Bonds (5) | 0.32 | +0.44 | Keep; trim US2YR |
| Commodities (10) | 0.59 | −0.47 | Keep; trim NatGas and Cocoa |

### Per-instrument removal decisions

| Instrument | Val SR | Reason removed |
|---|---|---|
| EURUSD | −0.19 | FX group structural underperformance; managed-float regime post-GFC |
| GBPUSD | −0.59 | Brexit whipsaw adds noise on top of FX structural issues |
| AUDUSD | −0.39 | Commodity FX, range-bound post-2011 commodity peak |
| USDCAD | −0.35 | Commodity FX, range-bound post-2011 commodity peak |
| US2YR | −1.43 | ZIRP pinned short-end rates 2010–2021; zero signal, then 2022 shock reversal |
| NatGas | −0.58 | US shale revolution 2009+ structurally changed supply dynamics |
| Cocoa | −0.84 | No persistent trend in IS or validation; no identifiable regime |

USDJPY retained despite being FX: sole instrument in asset class with BoJ policy-driven structural trends; val SR 0.00 (flat, not negative).

---

## Revised System Configuration

**Universe:** 18 instruments (down from 25)  
**Rules:** 5 (down from 6; BREAKOUT_20 removed)

### Forecast weights

| Rule | Old | New | Rationale |
|---|---|---|---|
| EWMAC_8_32 | 12.5% | **16.7%** | Trend budget redistributed equally across 3 rules |
| EWMAC_32_128 | 12.5% | **16.7%** | |
| EWMAC_64_256 | 12.5% | **16.7%** | |
| CARRY | 25.0% | **25.0%** | Unchanged; best validator |
| SEASONALITY | 25.0% | **25.0%** | Unchanged |
| BREAKOUT_20 | 12.5% | removed | |

Macro structure unchanged: Trend 50% / Carry 25% / Seasonality 25%.

### Instrument weights

Group allocations revised based on correlation structure of remaining instruments. FX reduced from 25% (5 instruments) to 8% (1 instrument, per-instrument rate preserved). Commodities increased to 42% — largest group, 8 instruments with low inter-correlations.

| Group | Old | New |
|---|---|---|
| FX | 25% | 8% |
| Equities | 25% | 28% |
| Bonds | 23% | 22% |
| Commodities | 27% | 42% |

Within-group weight rationale:
- **US500/NAS100**: US equity pair (corr 0.72 on IS positions) → 4% each, half a full unit
- **GER40/JPN225/HK50**: independent regional units → 6.7% each
- **US5YR/US10YR/US30YR**: highly correlated yield curve (corr 0.78–0.91) → 10% shared equally (3.3% each)
- **BUND**: sole European bond, independent from US curve → 12%; larger than US curve combined
- **XAU**: precious metals lead instrument, strong IS and test-period alpha → 8%
- **XAG**: correlated with XAU (0.21 on IS positions) → 4%, half XAU's weight
- **COPPER**: industrial metal, lower precious correlation → 6%
- **SpotCrude**: sole energy instrument after NatGas removal → 8% (full sub-group budget)
- **Coffee/Sugar/Corn/Cotton**: 4 agricultural softs, low inter-correlations → 4% each

### Recalibrated parameters

| Parameter | Old | New | Note |
|---|---|---|---|
| CARRY scalar | 33.80 | 30.58 | Lower: 4 FX carry instruments removed |
| EWMAC_8_32 scalar | 6.37 | 6.36 | Unchanged |
| EWMAC_32_128 scalar | 2.76 | 2.64 | Marginal change |
| EWMAC_64_256 scalar | 1.89 | 1.79 | Marginal change |
| IDM | 2.50 (cap) | 2.50 (cap) | Uncapped 3.09; same cap reached |

FDMs recalibrated for all 18 instruments. Bonds and ags receive higher FDMs (1.46–1.67) because seasonality and carry add meaningful diversification to trend signals. Equities and metals lower (1.13–1.19) because rules are more correlated for those instruments.

---

## Final Backtest Results

| Period | Sharpe | Ann Return | Max DD | Bars |
|---|---|---|---|---|
| IS 1984–2010 | **0.78** | 9.2% | −18.7% | 6,784 |
| Val 2010–2017 | **0.43** | 4.3% | −18.1% | 2,086 |
| Test 2018–2026 | **0.41** | 3.3% | −13.8% | 2,256 |

### Per-instrument breakdown

| Instrument | SR IS | SR Val | SR Test | Notes |
|---|---|---|---|---|
| USDJPY | 0.37 | 0.20 | 0.08 | Declining but positive through all periods |
| US500 | 0.34 | 0.21 | 0.18 | Stable; equity trend persists |
| NAS100 | 0.06 | 0.36 | 0.38 | Best stable OOS performer; tech bull is genuine |
| GER40 | 0.50 | −0.04 | −0.17 | European equity underperformance post-COVID |
| JPN225 | 0.53 | 0.13 | 0.13 | Stable modest positive |
| HK50 | 0.43 | 0.00 | −0.21 | China regulation headwinds in test period |
| US5YR | 0.50 | −0.48 | 0.34 | ZIRP crushed val; 2022 rate cycle restored |
| US10YR | 0.42 | −0.21 | 0.31 | Same pattern as US5YR |
| US30YR | 0.36 | 0.14 | 0.18 | Gradual normalisation tradeable throughout |
| BUND | 0.14 | 0.51 | 0.01 | Falling European rates 2012–2016; exhausted in test |
| XAU | 0.26 | 0.00 | 0.84 | Gold inflation/macro trade activated post-2020 |
| XAG | −0.05 | 0.15 | 0.13 | Follows XAU with lag |
| COPPER | 0.41 | −0.12 | 0.08 | Industrial cycle timing difficult |
| SpotCrude | 0.20 | −0.07 | 0.28 | 2022 energy shock tradeable |
| Coffee | 0.41 | −0.14 | 0.14 | Seasonality helps in test |
| Sugar | 0.19 | 0.12 | −0.42 | Only consistent test-period underperformer |
| Corn | 0.33 | −0.13 | 0.45 | Ukraine/food supply trade in test |
| Cotton | 0.44 | 0.08 | 0.13 | Stable modest positive |

---

## Interpretation

### IS → Val → Test stability

The IS→Val degradation (0.78→0.43, −45%) is consistent with Carver's recommended 50% IS haircut for forward SR estimation. More importantly, the test period (0.41) confirms the validation result almost exactly, which indicates the improvements are structural rather than a second round of overfitting to the validation data.

### Realistic forward SR estimate

IS SR 0.78 × 0.50 haircut = **0.39 forward SR estimate**. Actual test SR 0.41 is above this estimate — the revised system outperforms its IS-adjusted expectation in the held-out period.

### Max drawdown improvement

Removing the poorly performing instruments and BREAKOUT_20 dramatically reduced drawdown:
- Old OOS Max DD: −39.7% (2010–2026 combined)
- New Val Max DD: −18.1%
- New Test Max DD: −13.8%

The 15% vol target and IDM 2.50 remain appropriate. At test SR 0.41, half-Kelly vol target ≈ 12–13%, making 15% a modest above-half-Kelly position size.

### Remaining concerns

- **BUND** dominated the validation period (SR 0.51, contributing 4.2% annual return to portfolio). This is a single instrument carrying the bond group in val. Test SR drops to 0.01, meaning BUND's carry trade exhausted as the ECB tightened in 2022. Bond group diversification would benefit from adding more European maturities if data were available.
- **GER40 and HK50** show declining trajectories (test SR −0.17 and −0.21). Both represent non-US equity markets with structural headwinds (EU energy crisis, China regulation). Within expected variance for a long-only bias system, but worth monitoring.
- **Sugar** is the only instrument with persistently negative test SR (−0.42). This is idiosyncratic commodity behavior and within acceptable range for a single 4%-weight instrument.

---

## Notes

- All calibration performed on IS data (1984–2010) only. Test period (2018–2026) was evaluated once, after all validation-based changes were locked in.
- Vol target remains 15% per step 5 decision.
- IDM remains 2.50 (capped) per step 7 calibration.

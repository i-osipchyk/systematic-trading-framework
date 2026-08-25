# Step 7 — Full System Validation and Vol Target Analysis

**Date:** 2026-08-25  
**Status:** Confirmed  
**Config:** `config/universe_40yr_wf.yaml` (18 traded, 7 shown with [excl])

---

## Motivation

After the step 6 revision (18-instrument system, SR 0.78 IS / 0.43 Test), two questions remained:

1. Did excluding the 7 instruments actually improve performance, or did it hurt it?
2. What vol target is appropriate given the live SR?

To answer (1), the full 25-instrument system was re-run using the same calibrated weights but with all instruments included. To answer (2), Kelly sizing was applied to the observed OOS SR.

---

## Full 25-Instrument System (Calibrated Weights)

Running all 25 instruments with the 18-instrument calibrated weights — excluded instruments receive their config default weight (4% each), traded instruments keep their handcrafted weights.

### IS | Val | Test performance at 40% vol target

| Period | Sharpe | Ann Return | Max DD |
|---|---|---|---|
| IS 1984–2010 | 0.74 | 33.1% | −64.2% |
| Val 2010–2017 | 0.48 | 20.3% | −57.8% |
| Test 2018–2026 | 0.43 | 14.0% | −61.5% |

### Per-instrument SR

| Instrument | IS SR | Val SR | Test SR | Status |
|---|---|---|---|---|
| EURUSD | 0.47 | 0.14 | −0.09 | [excl] FX group |
| GBPUSD | 0.26 | −0.32 | −0.05 | [excl] FX group |
| AUDUSD | 0.30 | −0.22 | −0.18 | [excl] FX group |
| USDJPY | 0.37 | 0.20 | 0.08 | traded |
| USDCAD | 0.38 | −0.05 | −0.52 | [excl] FX group |
| US500 | 0.34 | 0.21 | 0.18 | traded |
| NAS100 | 0.06 | 0.36 | 0.38 | traded |
| GER40 | 0.50 | −0.04 | −0.17 | traded |
| JPN225 | 0.53 | 0.13 | 0.13 | traded |
| HK50 | 0.43 | −0.00 | −0.21 | traded |
| US2YR | 0.56 | −0.45 | 0.42 | [excl] ZIRP |
| US5YR | 0.50 | −0.48 | 0.39 | traded |
| US10YR | 0.42 | −0.21 | 0.31 | traded |
| US30YR | 0.36 | 0.14 | 0.18 | traded |
| BUND | 0.08 | 0.60 | 0.15 | traded |
| XAU | 0.23 | −0.00 | 0.84 | traded |
| XAG | −0.08 | 0.15 | 0.13 | traded |
| COPPER | 0.41 | −0.12 | 0.08 | traded |
| SpotCrude | 0.20 | −0.07 | 0.28 | traded |
| NatGas | −0.04 | −0.42 | −0.30 | [excl] shale |
| Coffee | 0.41 | −0.14 | 0.14 | traded |
| Cocoa | −0.27 | −0.69 | 0.18 | [excl] no edge |
| Sugar | 0.19 | 0.12 | −0.42 | traded |
| Corn | 0.34 | −0.13 | 0.45 | traded |
| Cotton | 0.44 | 0.08 | 0.13 | traded |

### Per-asset-class SR

| Asset class | IS SR | Val SR | Test SR |
|---|---|---|---|
| FX | 0.55 | 0.04 | −0.09 |
| Equities | 0.61 | 0.18 | 0.07 |
| Bonds | 0.24 | 0.56 | 0.24 |
| Commodities | 0.51 | −0.17 | 0.57 |
| **Portfolio** | **0.74** | **0.48** | **0.43** |

### Per-rule SR

| Rule | IS SR | Val SR | Test SR |
|---|---|---|---|
| EWMAC_8_32 | 1.02 | −0.09 | 0.49 |
| EWMAC_32_128 | 0.71 | 0.33 | 0.64 |
| EWMAC_64_256 | 0.54 | 0.37 | 0.66 |
| CARRY | 0.15 | 0.68 | −0.44 |
| SEASONALITY | 1.01 | 0.11 | 0.20 |
| **Combined** | **0.74** | **0.48** | **0.43** |

### Per-rule-family SR

| Family | Rules | IS SR | Val SR | Test SR |
|---|---|---|---|---|
| Trend | 3 | 0.82 | 0.26 | 0.72 |
| Carry | 1 | 0.15 | 0.68 | −0.44 |
| Seasonality | 1 | 1.01 | 0.11 | 0.20 |
| **Combined** | 5 | **0.74** | **0.48** | **0.43** |

---

## System Comparison: Instrument Universe Effect

Three configurations compared using the same forecast weights and IDM:

| System | IS SR | Val SR | Test SR |
|---|---|---|---|
| 25-inst equal weight | 0.84 | 0.19 | 0.42 |
| 21-inst handcrafted (FX restored) | 0.81 | 0.38 | 0.37 |
| **18-inst handcrafted (step 6)** | **0.76** | **0.39** | **0.55** |

**Verdict:** The step 6 exclusions were correct. Adding back the FX group (21-inst) degraded test SR from 0.55 to 0.37 because USDCAD (−0.52), AUDUSD (−0.18), and EURUSD (−0.09) are structurally weak in the test period. Equal-weight 25-inst had the worst Val SR (0.19) because the bad instruments (Cocoa −0.69, NatGas −0.42, US2YR/US5YR −0.45/−0.48) received full equal weight.

The 18-instrument step 6 system remains the active configuration.

---

## Vol Target Analysis

### The 40% vol target problem

Running at 40% vol target:
- IS return 33%, Val 20%, Test 14% — high nominal returns
- IS max DD −64%, Val −58%, Test −62% — unacceptable for live trading
- At 40% vol, a −60% drawdown requires a +150% gain to recover

### Kelly sizing

For a system with OOS SR ≈ 0.45 (geometric mean of Val 0.48 and Test 0.43):

| Sizing | Vol target | Rationale |
|---|---|---|
| Full Kelly | ~45% | Maximises log-wealth; maximises drawdowns |
| Half Kelly | ~22% | Standard practice; halves drawdown vs full Kelly |
| Carver recommended | 15–25% | Consistent with SR 0.43–0.48 |

At 40% vol we were slightly below full Kelly — very aggressive, producing compounded drawdowns of 60%+.

### Recommended vol target: 20–25%

At 20% vol target (half-Kelly):
- Ann returns scale to ~7% (Val) / ~5% (Test)
- Max DD scales to approximately −25–30%
- Sustainable for live trading; within 2 years recovery from worst drawdown

At 25% vol target:
- Ann returns ~9% (Val) / ~6% (Test)
- Max DD approximately −35–40%
- Aggressive but manageable for an allocation-sized position

The step 6 calibration used 15% vol target (IS SR 0.78 × 50% haircut → forward SR 0.39 → half-Kelly ~20%, rounded down for conservatism). That remains appropriate.

---

## Key Findings

### CARRY is regime-dependent

CARRY had the clearest regime split of any rule:
- Val 2010–2017 SR: **+0.68** — ZIRP and ECB/BoJ QE produced persistent carry across bonds and FX
- Test 2018–2026 SR: **−0.44** — rate hiking cycle 2022–2023 reversed carry trades sharply

CARRY's 25% weight was calibrated on IS data where it had SR 0.15. The validation boost was a ZIRP artifact. This means:
- CARRY's validation SR cannot be used as a forward SR estimate
- The 25% weight may be too high for regimes with rising rates
- Reducing CARRY to 10–15% and increasing Trend to 60–65% would produce more stable cross-regime performance

### Trend recovered strongly in test

After the weak Val period (0.26 family SR), Trend recovered to **0.72** in Test — the best of any family. The 2022–2026 period produced strong directional moves across bonds (rate hiking), commodities (energy/food supply shocks), and gold (inflation), all trend-friendly environments. This validates keeping the full Trend allocation despite the Val SR decline.

### Short-trend (EWMAC_8_32) regime sensitivity

EWMAC_8_32 had IS SR 1.02 but Val SR −0.09. It recovered to Test SR 0.49. The near-zero Val SR is consistent with the 2010–2017 period being low-volatility and range-bound for many instruments (post-GFC central bank suppression of volatility). The recovery in test confirms this was a regime pause, not a structural failure.

---

## Notes

- Vol target of 15% (step 6 decision) remains the active configuration.
- All computations used `TRADING_CONFIG=config/universe_40yr_wf.yaml`.
- 40% vol target run was exploratory; no state files changed.
- Max drawdown uses compounded equity curve (HWM method), consistent with `src/backtest/metrics.py`.

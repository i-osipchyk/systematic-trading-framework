# Build v2 — Findings and Post-Mortem

**Date:** 2026-08-25
**Config:** `config/universe_v2.yaml`
**Status:** Experiment closed. Findings documented for next cycle.

---

## What this build was

A complete fresh rebuild following `system-build-steps.md` strictly, with one explicit objective: apply the structural-only pruning discipline throughout. No instrument or rule was excluded based on OOS or IS performance. Every decision was made on structural grounds (correlation, cost, economic rationale) using IS data only.

This was a direct response to Build v1, which had pruned instruments and rules based on val-period SR — a contaminated OOS.

---

## Final parameters

| Parameter | Value |
|---|---|
| Config | `universe_v2.yaml` |
| Instruments | 28 (see Step 1 doc) |
| Rules | EWMAC_4_16/8_32/16_64/32_128/64_256 + CARRY + SEASONALITY |
| Forecast weights | 5 × 10% EWMAC, 25% Carry, 25% Seasonality |
| Vol target | 20% |
| IDM | 2.5 (capped) |

Instrument weights: correlation-based hierarchical handcrafting (see `step4a_instrument_weights.yaml`). Top-level split nearly equal across FX/Equities/Bonds/Commodities (~25% each). Key adjustments: USDJPY outsized (9.2%, negatively correlated with other FX), BUND manually trimmed from 13% → 6%, each ag +1%.

---

## Performance results

| Period | SR | Ann Ret | Max DD |
|---|---|---|---|
| IS 1984–2010 | 0.94 | 13.6% | −23.4% |
| Val 2010–2017 | 0.24 | 3.1% | −26.7% |
| Test 2018–2026 | 0.27 | 3.0% | −24.2% |

OOS SR ~26% of IS SR. Both OOS periods solidly positive.

### Rule family OOS performance

| Family | IS SR | Val SR | Test SR |
|---|---|---|---|
| Trend (5 EWMAC speeds) | 1.09 | 0.09 | 0.45 |
| Carry | 0.18 | 0.61 | −0.41 |
| Seasonality | 1.21 | 0.25 | 0.61 |

- Fast trend (EWMAC_4_16) nearly worthless OOS (val −0.21, test −0.00). Slower speeds all positive.
- Seasonality is the most consistent rule across all three periods.
- Carry is countercyclical to trend: strong in the ZIRP val period, weak in the post-2018 test.

### Asset class OOS performance

| Class | IS SR | Val SR | Test SR |
|---|---|---|---|
| FX | 0.58 | −0.04 | −0.19 |
| Equities | 0.51 | −0.03 | −0.04 |
| Bonds | 0.43 | +0.49 | +0.30 |
| Metals | 0.22 | −0.06 | +0.35 |
| Energy | 0.16 | +0.02 | +0.35 |
| Ags | 0.76 | −0.40 | +0.23 |

- Bonds are the primary OOS diversifier. FX and ags had strong IS but faded OOS.
- Energy and metals both recovered in the test period.

---

## Build v2 vs Build v1 — the selection-bias lesson

Build v1 excluded AUDUSD, GBPUSD, USDCAD, EURUSD, US2YR, and Cocoa based on their val-period SR. The result was artificially strong OOS numbers.

| | IS SR | Val SR | Test SR |
|---|---|---|---|
| Build v1 (18 instruments, OOS-pruned) | 0.78 | **0.43** | **0.41** |
| Build v2 (28 instruments, structural only) | 0.94 | **0.24** | **0.27** |

Build v1's higher OOS SR was a mirage: by selecting instruments based on val data and then validating on val data, the test was contaminated. Build v2's 0.24/0.27 is an unbiased estimate — OOS data was never touched during calibration.

The correct interpretation: a structural trend-following system on this universe earns roughly SR 0.25 in OOS, not 0.40+.

---

## Problem instruments identified

These are observations from the locked OOS validation — not grounds for retrospective exclusion, but inputs for the next cycle's IS-only structural review.

| Instrument | IS SR | Val SR | Note |
|---|---|---|---|
| UK100 | −0.01 | −0.89 | No IS evidence of trend edge. Worst OOS drag. |
| Cocoa | −0.29 | −0.87 | Negative IS SR over 18yr IS window. Structural question. |
| XAG | −0.09 | +0.16 | Marginally negative IS. Cost filter fails for fast rules. |
| EWMAC_4_16 | +0.96 IS | −0.21 val | Fast trend: high IS SR doesn't hold OOS. |

UK100 is the cleanest case: IS SR essentially zero means there is no IS evidence that FTSE trends are exploitable with this rule set. That is a structural argument (insufficient IS signal), not a performance argument based on OOS.

Cocoa has a genuine negative IS SR over 18 years. Again structural — if the IS hypothesis test fails, the instrument shouldn't be in the universe regardless of OOS.

---

## What to do differently in the next cycle

1. **IS SR threshold as a structural filter.** Carver does not use IS SR as a filter, but a 20+ year IS SR below zero is weak evidence that the rule has any edge on that instrument. Consider adding a structural IS SR floor (e.g. SR > −0.20 over full IS window) as a legitimate IS-only gate — not performance-based pruning, but a minimum evidence bar.

2. **EWMAC_4_16 cost vs. benefit.** Val and test SR near zero with moderately high turnover. Either raise the cost filter threshold or accept that the fastest speed adds more cost than diversification benefit OOS.

3. **Carry weight for bonds.** BUND val SR of +0.68 was largely carry-driven (ECB rate structure, roll-down carry on the Bund). Consider whether the 25% carry weight is too low given carry's OOS performance vs. trend in the ZIRP period.

4. **Ag group weight.** Ags had the strongest IS SR (0.76) of any asset class but val SR of −0.40. The IS SR may reflect a regime (2000s commodity supercycle) that partially reversed. Consider whether the ag budget is appropriately sized given the IS-window composition.

5. **Soybeans and Wheat are worth keeping.** Both held up OOS better than the legacy ags (Cocoa, Coffee). Soybeans: val +0.27, test +0.29 — the most consistent ag instrument. Wheat: val −0.56 (drought-related spike reversal), test −0.16 — weaker but non-structural.

---

## State files (archived, not active)

All state files for this build are in `calibrate/state/`. They remain on disk as a reference but are not the active live config.

- `step3a_scalars.yaml` — forecast scalars
- `step3d_forecast_weights.yaml` — 7-rule weight vector
- `step3d_fdm.yaml` — per-instrument FDM
- `step4a_instrument_weights.yaml` — 28-instrument weights
- `step4b_idm.yaml` — IDM = 2.5
- `step5_vol_target.yaml` — vol target = 20%

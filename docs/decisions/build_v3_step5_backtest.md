# Build v3 — Step 5: IS Backtest and Volatility Target

**Date:** 2026-08-25
**Status:** Complete — all parameters locked
**Config:** `config/universe_v3.yaml`
**State files:** `calibrate/state/step5_vol_target.yaml`

---

## IS portfolio performance

| Period | SR | Ann Ret | Max DD | Bars |
|---|---|---|---|---|
| IS 1984–2010 | 1.25 | 59.0% | −61.7% | 6,784 |

*At 40% vol target. SR is scale-invariant — identical at any vol target.*

---

## Kelly analysis

IS SR = 1.25. Applying 0.75 IS-to-OOS discount:

| Metric | Value |
|---|---|
| Realistic SR (×0.75) | 0.94 |
| Full Kelly vol target | 94% |
| Half Kelly vol target | 47% |
| Suggested (geometric mean, capped) | 40% |

**Vol target selected: 40%**

Rationale: trend-following return distributions have positive skew, which supports targeting above half-Kelly. The suggested geometric-mean level (40%) is the appropriate anchor. The IS SR of 1.25 across 23 instruments spanning four genuinely uncorrelated asset classes is robust — not inflated by concentrated factor bets. No performance-based pruning was applied at any step, so the IS SR carries a clean estimate.

At 40% vol target the IS max DD is −61.7%. OOS drawdowns will be larger — this vol target implies tolerance for drawdowns in the 50–80% range in stress periods. Appropriate only with capital that can sustain those drawdowns without forced liquidation.

---

## Per-instrument IS breakdown

| Instrument | SR | Ann Ret | Max DD | TV |
|---|---|---|---|---|
| US500 | 0.69 | 3.9% | −9.2% | 9.9 |
| NAS100 | 0.49 | 2.8% | −14.7% | 9.9 |
| GER40 | 0.84 | 4.4% | −7.5% | 11.6 |
| JPN225 | 0.77 | 4.0% | −8.6% | 11.6 |
| HK50 | 0.88 | 4.9% | −8.2% | 13.1 |
| UK100 | 0.45 | 2.1% | −6.0% | 12.1 |
| US2YR | 0.96 | 5.0% | −8.6% | 10.6 |
| US5YR | 0.92 | 5.1% | −9.0% | 11.4 |
| US10YR | 0.79 | 4.3% | −8.7% | 11.4 |
| US30YR | 0.77 | 4.0% | −10.3% | 12.6 |
| BUND | 0.07 | 0.8% | −29.6% | 9.0 |
| XAU | 0.04 | 0.5% | −67.3% | 11.7 |
| XAG | −0.08 | −1.2% | −73.0% | 13.1 |
| COPPER | 0.40 | 3.3% | −29.2% | 11.3 |
| SpotCrude | 0.37 | 1.8% | −9.8% | 12.9 |
| Gasoline | 0.46 | 2.2% | −7.5% | 13.1 |
| Coffee | 0.45 | 10.3% | −14.8% | 13.9 |
| Cocoa | −0.29 | −3.0% | −65.0% | 12.6 |
| Sugar | 0.42 | 3.7% | −18.0% | 11.3 |
| Corn | 0.49 | 7.1% | −36.6% | 12.0 |
| Cotton | 0.59 | 5.2% | −14.7% | 13.1 |
| Soybeans | 0.58 | 7.7% | −16.8% | 11.3 |
| Wheat | 0.26 | 3.1% | −28.6% | 13.0 |

*SR = post-cost Sharpe. TV = IS roundtrips per year. Ann Ret and Max DD at 40% vol target.*

### Observations (IS-only — not grounds for exclusion)

**Strong IS contributors:** US bonds (SR 0.77–0.96), HK50 (0.88), GER40 (0.84), JPN225 (0.77). The US yield curve is the clearest IS trend signal in the portfolio.

**Weak IS contributors:**
- **BUND (SR 0.07, weight 13.94%):** Near-zero IS trend edge despite the highest single-instrument weight. German rates were more stable than US rates across the IS window (ECB convergence dynamics, post-reunification policy). BUND's large weight is justified by its structural independence from US rates (corr 0.034–0.049) — independence means decorrelation, not guaranteed trend returns. This is the most significant watch item for OOS validation.
- **XAU (SR 0.04), XAG (SR −0.08):** Gold and silver show minimal IS trend edge under the EWMAC+Seasonality rule set across this IS period. Both above the −0.5 structural exclusion threshold; no action required.
- **Cocoa (SR −0.29):** Negative IS SR, above −0.5 threshold. No exclusion; this is an IS data point for the next cycle's review, not grounds for retrospective action.

All per-instrument IS SRs are above the −0.5 structural exclusion threshold. No mandatory changes.

---

## Turnover cross-check

Per-instrument IS turnover (roundtrips/year) falls in the 9.0–13.9 range — consistent with the Step 3c estimates (EWMAC_4_16: 23.7; EWMAC_8_32: 12.7; SEASONALITY: 9.9) weighted by the 10/10/10/10/10/50 forecast allocation. Portfolio-level effective turnover is dominated by the slower EWMAC speeds and seasonality.

---

## Final locked system parameters

| Parameter | Value |
|---|---|
| Config | `config/universe_v3.yaml` |
| Instruments | 23 (equities 6, bonds 5, financial commodities 6, ags 7) |
| Rules | EWMAC_4_16/8_32/16_64/32_128/64_256 + Seasonality |
| Forecast weights | 10% × 5 EWMAC + 50% Seasonality (uniform, all instruments) |
| Vol target | **40%** |
| IDM | 2.5 (capped) |

Instrument weights and FDMs: see `calibrate/state/step4a_instrument_weights.yaml` and `step3d_fdm.yaml`.

**All five steps complete. Parameters are locked. Do not adjust based on OOS results — run `oos_validation.py` once as the one-shot validation.**

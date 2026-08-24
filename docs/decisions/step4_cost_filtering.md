# Step 4 — Cost Filtering

**Date:** 2026-08-24  
**Status:** Complete  
**Calibrated file:** `calibrate/state/04_turnover.yaml`  
**IS window:** 1984–2010, 25 instruments

---

## Method

Carver's standardised cost ceiling: a rule should be excluded for an instrument if its standardised trading cost exceeds **0.13 / turnover**.

- Turnover = roundtrips per year (position change / 2 / mean_abs_position / years)
- Standardised cost = (half_spread + commission) / (daily_vol × pointsize)
- Threshold: if standardised_cost > 0.13 / turnover → drop that rule for that instrument

Turnover is pooled across all instruments (mean of per-instrument estimates). The cost ceiling is a per-instrument test applied individually.

---

## Per-rule turnover and cost ceilings

| Rule | RT/yr | Max std cost |
|---|---|---|
| EWMAC_8_32 | 13.5 | 0.0096 |
| EWMAC_32_128 | 8.4 | 0.0155 |
| EWMAC_64_256 | 7.6 | 0.0171 |
| BREAKOUT_20 | 46.2 | **0.0028** |
| CARRY | 4.0 | 0.0329 |
| SEASONALITY | 3.0 | 0.0428 |

---

## Key finding: BREAKOUT_20

BREAKOUT_20 is the most expensive rule at 46.2 RT/yr, giving a cost ceiling of only 0.0028. This means it can only be used for instruments where the standardised cost is below 0.28% of a daily vol unit — broadly, only the most liquid instruments (major FX, stock indices, front-month energy).

All other rules have ceilings of 0.0096–0.0428 and will pass for essentially every instrument in this universe.

**Instruments where BREAKOUT_20 is likely excluded:**

Less liquid ags (Coffee, Cocoa, Cotton) and potentially XAG and NatGas (depending on spread and vol). These instruments have wider bid-ask spreads relative to their daily moves.

**No rules are excluded globally** — even BREAKOUT_20 has genuine value for liquid instruments (major FX, indices).

---

## Combined instrument turnover

| Instrument | RT/yr | Instrument | RT/yr |
|---|---|---|---|
| SpotCrude | 21.6 | NatGas | 24.4 |
| NAS100 | 19.1 | GBPUSD | 19.0 |
| EURUSD | 18.9 | GER40 | 18.5 |
| HK50 | 17.3 | US30YR | 17.7 |
| JPN225 | 17.0 | US500 | 16.9 |
| Coffee | 16.8 | USDCAD | 16.0 |
| US10YR | 16.6 | USDJPY | 16.3 |
| Cotton | 15.7 | AUDUSD | 15.8 |
| US5YR | 15.4 | Cocoa | 15.2 |
| Sugar | 14.4 | Corn | 14.8 |
| COPPER | 12.7 | US2YR | 13.6 |
| BUND | 12.1 | XAU | 11.2 |
| XAG | 9.0 | | |

**Portfolio weighted average: 16.2 RT/yr**

Energy (NatGas 24.4, SpotCrude 21.6) has the highest combined turnover — driven by the BREAKOUT_20 component. XAG (9.0) and BUND (12.1) are the slowest-trading instruments — driven by low-volatility, trend-dominated signals.

---

## Implication for live trading (Pepperstone CFDs)

For this portfolio's live implementation, the key check is whether BREAKOUT_20 should be excluded per-instrument. A reasonable heuristic:

- **Include BREAKOUT_20:** Major FX (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD), stock indices (US500, NAS100, GER40, JPN225, HK50), BUND, SpotCrude
- **Evaluate case-by-case:** US bond curve (US2YR/US5YR/US10YR/US30YR), XAU, COPPER, NatGas
- **Likely exclude BREAKOUT_20:** Coffee, Cocoa, Sugar, Corn, Cotton, XAG

No forecast weight adjustment is made now; the live trading layer can zero out a rule per instrument when standardised cost data from Pepperstone is confirmed.

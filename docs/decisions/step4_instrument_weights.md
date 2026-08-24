# Step 4 — Instrument Weights

**Date:** 2026-08-24  
**Status:** Confirmed  
**Files:** `calibrate/state/06_group_weights.yaml`, `calibrate/state/06_instrument_weights.yaml`

---

## Method

Carver's hierarchical handcrafting: equal weight between independent risk factors at every level of the tree. Within a correlated sub-pair, the pair shares the weight of a single unit (rather than each member getting its own unit weight). This avoids running a full portfolio optimisation, which would overfit the IS correlation matrix.

**Assumption:** equal expected Sharpe ratio across all instruments. Insufficient historical evidence to assert one instrument is structurally better than another.

---

## Hierarchy and final weights

```
Portfolio (100%)
│
├── FX (25.00%) — 3 independent units
│   ├── European FX: EURUSD + GBPUSD  (IS corr ~0.75)  4.17% each
│   ├── Commodity FX: AUDUSD + USDCAD (IS corr ~0.60)  4.17% each
│   └── USDJPY (sole JPY/safe-haven unit)               8.32%
│
├── Equities (25.01%) — 4 independent units
│   ├── US equities: US500 + NAS100   (IS corr ~0.90)  3.13% each
│   ├── GER40                                            6.25%
│   ├── JPN225                                           6.25%
│   └── HK50                                             6.25%
│
├── Bonds (23.37%) — 2 units, reduced from 25%
│   ├── US curve: US2YR/US5YR/US10YR/US30YR (all highly correlated) 3.13% each
│   └── BUND (sole European rates unit)                             10.85%
│
└── Commodities (26.67%) — 3 sub-groups, increased from 25%
    ├── Metals (8.33%)
    │   ├── Precious: XAU + XAG  (IS corr ~0.75)  2.08% each
    │   └── COPPER (industrial demand driver)       4.17%
    ├── Energy (8.33%)
    │   ├── SpotCrude                               4.17%
    │   └── NatGas                                  4.17%
    └── Ags (10.00%) — increased from 8.33%
        ├── Coffee    2.00%
        ├── Cocoa     2.00%
        ├── Sugar     2.00%
        ├── Corn      2.00%
        └── Cotton    2.00%
```

Total: 100.05% (within ±0.5% tolerance).

---

## Key decisions

### Bond group reduced (25% → 23.37%), commodities increased (25% → 26.67%)

The strict hierarchical approach gives BUND 12.5% — the full weight of the European bond factor — while each agricultural instrument gets only 1.67%. This 7.5× disparity was judged too large given that the 5 ag instruments (Coffee, Cocoa, Sugar, Corn, Cotton) are structurally diverse (different geographies, different demand cycles) and represent a more genuinely diversified sub-group than BUND alone.

Adjustment: BUND loses 5 × 0.33pp = 1.65pp (BUND: 12.5% → 10.85%). That weight is reallocated to the commodity group and distributed equally across the 5 ag instruments (each: 1.67% → 2.0%). Metals and energy are unchanged.

This is a modest tilt rather than a structural overhaul — BUND still receives more weight than any individual instrument in the portfolio, consistent with its role as the sole European rates factor.

### USDJPY at 8.32% (full sub-group weight)

JPY is the only currency in the portfolio with a safe-haven/risk-off dynamic (decouples from EUR pairs during stress, independent monetary policy). There is no sibling instrument to share its sub-group weight.

### US500/NAS100 at 3.13% each

US500 and NAS100 are ~0.90 correlated — effectively one US equity bet split across two instruments. The pair shares the 6.25% weight of a single equity unit. GER40, JPN225, HK50 each get their own full unit (different central bank, different economic cycle).

### US bond curve: equal weight across 4 maturities

US2YR, US5YR, US10YR, US30YR are all highly correlated within the US rate cycle, sharing the 12.5% US-curve allocation. Equal weight within the curve is used rather than duration-weighting — the backtest uses price series for all four and the correlation structure during IS data already captures the within-curve behaviour. Carver uses the same approach (multiple maturities, equal weight within the group).

### Precious metals: XAU/XAG share one unit

XAU and XAG are ~0.75 correlated (same monetary-store-of-value driver). The pair shares 4.17%, giving COPPER (industrial demand, IS corr with XAU ~0.25–0.35) the full second unit at 4.17%.

---

## Group totals

| Group | Weight | Instruments | Change from equal 25% |
|---|---|---|---|
| FX | 25.00% | 5 | — |
| Equities | 25.01% | 5 | — |
| Bonds | 23.37% | 5 | −1.63pp (BUND reduction) |
| Commodities | 26.67% | 10 | +1.67pp (ags increase) |

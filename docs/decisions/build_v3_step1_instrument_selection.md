# Build v3 — Step 1: Instrument Selection

**Date:** 2026-08-25
**Status:** Confirmed
**Config:** `config/universe_v3.yaml` (23 instruments, IS 1984–2010)

---

## Discipline

Start broad, prune by structure only — never by performance. All selection work uses IS data only.

---

## Scope decision

**FX excluded in its entirety.** This experiment covers equities, bonds, and commodities only. Not a structural exclusion — all five FX pairs (EURUSD, GBPUSD, AUDUSD, USDJPY, USDCAD) are structurally valid trend instruments; they are simply outside the scope of this build.

---

## Starting universe

v2 universe (28 instruments) minus FX (5) = 23 instruments.

---

## Structural filters applied

### 1. No IS history → exclude

| Instrument | Reason |
|---|---|
| BTC, ETH | History starts 2017; zero IS bars |
| US30, USOIL | History starts 2017; zero IS bars |

### 2. Redundant construct → exclude

| Instrument | Reason |
|---|---|
| USDX | Moot — FX removed from scope |
| EURGBP | Moot — FX removed from scope |

### 3. Structural regime break → exclude

| Instrument | Reason |
|---|---|
| NatGas | US shale revolution (2008–2012) permanently broke historical price dynamics. Independent structural change predating and explaining the observed weakness; IS scalars unreliable as forward estimates. |

### 4. Cost check

All 23 candidates have standardised cost per roundtrip well below 0.13 at typical slow-rule turnover. Detailed per-rule cost filtering is Step 3.

---

## Decisions by group

### Equities — 6 instruments

**US500, NAS100, GER40, JPN225, HK50, UK100**

Correlated pairs (US500/NAS100 ~0.90, GER40/UK100 ~0.75) handled in Step 4 handcrafting.

### Bonds — 5 instruments

**US2YR, US5YR, US10YR, US30YR, BUND**

BUND is the only non-USD bond — primary fixed-income diversifier. All four US maturities treated as one US-rates sub-group in Step 4.

Note on carry: with FX removed, carry applies to bonds only (5 instruments). Bond carry (yield differential / roll-down) is structurally well-defined. Carry family weight calibration reviewed at Step 3.

### Metals — 3 instruments

**XAU, XAG, COPPER**

XAU/XAG (~0.75 corr) as precious-metals pair; COPPER driven by industrial demand and China growth cycle, structurally independent (~0.25–0.35 corr with precious metals).

### Energy — 2 instruments

**SpotCrude, Gasoline**

High correlation (~0.80–0.85) handled in Step 4. Gasoline carries distinct demand signals (refinery margins, seasonal driving demand) that can diverge from crude in supply-shock episodes.

### Ags/Softs — 7 instruments

**Coffee, Cocoa, Sugar, Corn, Cotton, Soybeans, Wheat**

Unchanged from v2. Within-group correlations handled in Step 4 handcrafting.

---

## Final universe — 23 instruments

| Group | Instruments | Count |
|---|---|---|
| Equities | US500, NAS100, GER40, JPN225, HK50, UK100 | 6 |
| Bonds | US2YR, US5YR, US10YR, US30YR, BUND | 5 |
| Precious metals | XAU, XAG | 2 |
| Industrial metals | COPPER | 1 |
| Energy | SpotCrude, Gasoline | 2 |
| Ags/Softs | Coffee, Cocoa, Sugar, Corn, Cotton, Soybeans, Wheat | 7 |
| **Total** | | **23** |

---

## Handcrafting grouping tree (for Step 4)

Ags are a top-level group — not nested inside Commodities. Their price drivers (weather, crop cycles, supply shocks) are structurally orthogonal to both financial markets and financial-commodity dynamics. Nesting them three levels deep would dilute their budget without structural justification.

```
Portfolio
├── Equities
│   ├── US [US500, NAS100]       (~0.90 corr pair)
│   ├── European [GER40, UK100]  (~0.67 corr pair)
│   ├── JPN225
│   └── HK50
├── Bonds
│   ├── US rates [US2YR, US5YR, US10YR, US30YR]  (~0.80–0.92 within-curve)
│   └── BUND
├── Financial Commodities
│   ├── Precious metals [XAU, XAG]
│   ├── COPPER
│   └── Energy [SpotCrude, Gasoline]  (~0.54 corr pair)
└── Ags
    ├── Grains [Corn, Soybeans, Wheat]
    └── Tropical softs [Coffee, Cocoa, Sugar, Cotton]
```

---

## Open items for subsequent steps

- **Carry weight**: FX carry removed — recalibrate carry family top-level weight at Step 3 given bonds-only coverage.
- **Gasoline ctrader symbol**: confirm Pepperstone symbol before marking `traded: true`.
- **Soybeans / Wheat / Cocoa / Coffee / Sugar / Cotton tradability**: verify Pepperstone availability; mark `traded: false` for backtest-only if not offered.
- **US2YR**: very low IS vol (~2% ann) → large position sizes at the chosen vol target. Verify minimum-lot feasibility at Step 4.

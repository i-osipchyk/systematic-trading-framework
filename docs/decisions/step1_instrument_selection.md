# Step 1 — Instrument Selection

**Date:** 2026-08-24  
**Status:** Confirmed  
**Config target:** to be created as `config/universe_25.yaml`

---

## Candidate pool

The repository contains 31 instruments across 6 asset groups, sourced from FRED, Quandl (Nasdaq Data Link), Yahoo Finance, and datahub.io. All have daily price history; most reach back to 1984–1992 via FRED/World Bank monthly series spliced with futures data.

---

## Selection criteria applied (in order)

1. **Structural redundancy (correlation-based):** drop instruments that are largely derivable from others already in the set. Correlation between price series is a stable structural property, not a fitted result, so using it for exclusion does not contaminate in-sample data. All correlation reasoning here is intuition-based; empirical confirmation comes in the IS correlation analysis.

2. **Diversification value:** within each group, keep instruments that represent meaningfully different drivers (monetary policy regime, geography, demand cycle). Correlated pairs are *not* dropped — they are retained and handled by giving them asymmetric weights in the handcrafting step (Phase 3).

3. **Cost feasibility:** not evaluated numerically here (that is Phase 4 cost filtering). Any instrument with an obviously prohibitive spread relative to its volatility would be flagged, but none in this set triggered that concern at this stage.

4. **Practical tradability:** noted per instrument, but not used as an exclusion criterion for the backtest universe. Non-traded instruments still contribute to the IS correlation structure and backtest diversity. The distinction matters at Phase 7 (live preparation).

---

## Decisions by group

### FX — 5 kept, 2 dropped

**Kept:** EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD

**Dropped:**

- **USDX:** The US Dollar Index is approximately 57% EUR and 14% JPY by weight. Its correlation with EURUSD is around −0.95 — it is structurally the near-inverse of EURUSD, not a separate instrument. Including it would be adding a near-duplicate with an inverted sign, not a new source of return.

- **EURGBP:** Fully derived from EURUSD ÷ GBPUSD. Given both legs are already in the set, EURGBP carries no information not already present. It would increase within-FX correlation without adding any new driver.

**Correlation structure within the kept set:**  
EURUSD/GBPUSD (~0.75) and AUDUSD/USDCAD (~0.60) will form two natural sub-pairs. USDJPY partially decorrelates from EUR pairs in risk-off regimes (JPY safe-haven behaviour). The handcrafting in Phase 3 will assign lower combined weights to the correlated pairs; this is the correct outcome, not a signal to drop them.

---

### Equity indices — 5 kept, 1 dropped

**Kept:** US500, NAS100, GER40, JPN225, HK50

**Dropped:**

- **UK100:** Correlation with GER40 is approximately 0.75, and with US500 approximately 0.70. UK100 adds some commodity/energy sector weight (BP, Shell, miners) that distinguishes it from GER40, but the marginal diversification over a universe that already includes GER40, JPN225, and HK50 is small. Given the equity group already carries five instruments — including the US500/NAS100 correlated pair — adding a sixth weakly-differentiated European index was not judged worthwhile.

**Correlation structure within the kept set:**  
US500/NAS100 (~0.90) are essentially one US equity bet split across two instruments. They will be assigned a small combined weight within the "US equities" sub-pair and a correspondingly larger weight to GER40, JPN225, and HK50. JPN225 partially decouples via JPY movements and domestic demand cycles. HK50 is driven by China policy and growth rather than Western monetary policy.

---

### Government bonds — 5 kept, 0 dropped

**Kept:** US2YR, US5YR, US10YR, US30YR, BUND

All five are currently marked `traded: false` in the repo, reflecting the absence of long historical CFD data. Pepperstone does offer Treasury and Bund CFDs; their inclusion in live trading depends on whether usable CFD price history can be obtained (see note below).

**Rationale for keeping all four US maturities:**  
Within-curve correlation is high (0.70–0.90 between adjacent maturities), but over a 40-year IS window the term structure behaves differently across rate regimes: the 1980s disinflation, the 2000s low-rate era, and the post-2022 hiking cycle all produce meaningfully different duration dynamics. Capturing the full duration spread (2-year through 30-year) via four instruments is consistent with Carver's own multi-maturity approach. They will be handcrafted as a US-rates subgroup, with weight distributed by their mutual correlation.

**BUND** is approximately 0.65 correlated with US10YR across most regimes (different central bank, different fiscal cycle) and represents the only non-USD bond in the set. It is the primary geographic diversifier within the fixed-income group.

**Note on bond tradability:**  
BUND already has a `ctrader_symbol: EUROBUNDF` entry. US Treasury CFDs will need a liquidity/spread check on Pepperstone before being added to the live config. For now they are retained in the backtest universe and excluded from live position sizing via `traded: false`.

---

### Metals — 3 kept, 0 dropped

**Kept:** XAU, XAG, COPPER

XAU (gold) and XAG (silver) are approximately 0.75 correlated and will be treated as a correlated sub-pair within the metals group, with gold receiving the larger weight. COPPER is driven primarily by industrial demand and the China growth cycle — a structurally different driver from precious metals. Gold/copper correlation is approximately 0.25–0.35, making it genuinely diversifying.

---

### Energy — 2 kept, 1 dropped

**Kept:** SpotCrude, NatGas

**Dropped:**

- **Gasoline:** Approximately 0.85+ correlated with SpotCrude (RBOB gasoline is a refined crude product; its price is almost fully explained by crude oil cost plus the crack spread). Non-traded in the current config. Including it would add a near-duplicate of SpotCrude with a narrower spread.

**Note on NatGas:**  
Historical runs have shown poor performance for NatGas under trend-following rules. This is structurally explicable: natural gas storage follows a predictable annual injection/withdrawal cycle that produces frequent sharp price reversals — exactly the pattern that hurts EWMAC-style rules via whipsaw. NatGas is retained in the candidate universe at this stage. If the IS backtest confirms persistent underperformance, the preferred response (per the framework's guidance) is to re-match it to a seasonality rule rather than dropping it outright. Performance-based exclusion on IS data alone would be premature.

---

### Ags/Softs — 5 kept, 2 dropped

**Kept:** Coffee, Cocoa, Sugar, Corn, Cotton

**Dropped:**

- **Wheat:** Approximately 0.55–0.65 correlated with Corn (both grains; both respond to US Midwest planting/weather and global food demand). Corn is preferred as the representative grain because it has larger contract liquidity and is already an anchor of the Carver-style soft-commodity group. Wheat adds less marginal diversification than Cocoa or Cotton.

- **Soybeans:** Also approximately 0.55–0.65 correlated with Corn (US acreage competition; same growing season). The same logic as Wheat applies — keeping both Soybeans and Corn provides a pair of near-duplicates within an already-limited ag group.

**Correlation structure within the kept set:**  
Coffee, Cocoa, and Sugar are tropical softs with broadly independent supply dynamics (geographic separation, different weather exposures). Their mutual correlations are approximately 0.15–0.35. Cotton is a fiber crop with further separation from food commodities. Corn is the single grain representative. The five instruments will likely form a relatively flat sub-group without strong clustering pairs.

---

## Final universe (25 instruments)

| Group | Instruments | Count |
|---|---|---|
| FX | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD | 5 |
| Equity indices | US500, NAS100, GER40, JPN225, HK50 | 5 |
| Government bonds | US2YR, US5YR, US10YR, US30YR, BUND | 5 |
| Metals | XAU, XAG, COPPER | 3 |
| Energy | SpotCrude, NatGas | 2 |
| Ags/Softs | Coffee, Cocoa, Sugar, Corn, Cotton | 5 |
| **Total** | | **25** |

---

## Preliminary handcrafting grouping tree

The hierarchy below informs Phase 3 instrument weight calibration. Sub-pairs with high correlation (~0.75+) are flagged; they will receive asymmetric weights within their sub-group.

```
Portfolio
├── FX
│   ├── European FX
│   │   ├── EURUSD   (~0.75 corr pair)
│   │   └── GBPUSD
│   ├── Commodity FX
│   │   ├── AUDUSD   (~0.60 corr pair)
│   │   └── USDCAD
│   └── USDJPY
├── Equities
│   ├── US equities
│   │   ├── US500    (~0.90 corr pair)
│   │   └── NAS100
│   ├── GER40
│   ├── JPN225
│   └── HK50
├── Bonds
│   ├── US rates
│   │   ├── US2YR
│   │   ├── US5YR
│   │   ├── US10YR
│   │   └── US30YR
│   └── BUND
├── Metals
│   ├── Precious
│   │   ├── XAU     (~0.75 corr pair)
│   │   └── XAG
│   └── COPPER
├── Energy
│   ├── SpotCrude
│   └── NatGas
└── Ags/Softs
    ├── Coffee
    ├── Cocoa
    ├── Sugar
    ├── Corn
    └── Cotton
```

---

## Open items for later steps

- **NatGas** — watch IS performance under trend rules; consider seasonality rule as an alternative if performance is structurally poor (Phase 2 rule selection).
- **Bond CFD data** — verify whether Pepperstone US Treasury CFD history is long enough to include them in the walk-forward IS window; if not, they remain backtest-only.
- **AUDUSD/USDCAD** — petrocurrency link means USDCAD will correlate positively with SpotCrude (~0.45) and AUDUSD will correlate with COPPER (~0.45). This cross-group correlation is acceptable given the handcrafting structure but should be noted when reviewing IDM.

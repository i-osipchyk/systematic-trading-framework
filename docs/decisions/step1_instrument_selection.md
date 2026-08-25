# Step 1 — Instrument Selection

**Date:** 2026-08-25
**Status:** Confirmed
**Config:** `config/universe_v2.yaml` (29 instruments, IS 1984–2010)

---

## Discipline

Start broad, prune by structure only — never by performance.

Correlation-based pruning is legitimate (structural property of the market, not fitted to returns). Performance-based pruning on IS data inflates apparent OOS SR by construction. The only permitted performance-based exclusion is persistent underperformance with an **independent economic explanation** that predates and explains the observed weakness.

---

## Candidate pool

35 instruments with D1 price data in the repository. IS window ends 2010-01-01.

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
| USDX | Dollar Index ≈ 57% EUR + 14% JPY by weight; ~−0.95 correlated with EURUSD. Including both adds a near-inverse duplicate, not a new driver. |
| EURGBP | Derived cross: EURUSD ÷ GBPUSD. With both legs in the universe, EURGBP carries no independent information. Short IS history (1999 start) reinforces exclusion. |

### 3. Structural regime break → exclude

| Instrument | Reason |
|---|---|
| NatGas | The US shale revolution (2008–2012) permanently broke the historical crude/gas price relationship and collapsed Henry Hub price dynamics. This is an independent structural change, not a performance observation. The IS window (2000–2010) partially spans the break, making IS scalars unreliable as forward estimates. |

### 4. Cost check

All remaining candidates have standardised cost per roundtrip well below 0.13 at typical slow-rule turnover (3–10 RT/yr). Detailed per-rule cost filtering is Step 3.

### 5. IS history flags (included with caveat)

| Instrument | IS bars | Note |
|---|---|---|
| EURUSD | 2,799 (11yr) | EUR launched 1999; shorter IS window than others |
| Gasoline | 2,298 (10yr) | RBOB data from 2000; included despite high SpotCrude correlation (user decision — independent energy sub-component with different demand profile) |

---

## Decisions by group

### FX — 5 instruments

**AUDUSD, GBPUSD, USDCAD, USDJPY, EURUSD**

All five retained. The previous run excluded AUDUSD, GBPUSD, USDCAD, and EURUSD based on validation-period SR (−0.39, −0.59, −0.05, −0.19). Those are OOS performance observations — invalid as Step 1 criteria.

Structural correlation pairs: EURUSD/GBPUSD (~0.75), AUDUSD/USDCAD (~0.60). Both pairs retained; Step 4 handcrafting assigns lower combined weights to correlated clusters.

### Equities — 6 instruments

**US500, NAS100, GER40, JPN225, HK50, UK100**

UK100 (FTSE 100) added: 40-year IS history (1984), Pepperstone-traded, different sector composition from GER40 (heavy energy/mining vs. export-industrial). UK/EU economic cycles partly decouple at currency level (GBP vs EUR). The previous run excluded UK100 on marginal-diversification grounds relative to GER40; with a clean structural approach and 40yr data, it belongs.

US500/NAS100 (~0.90 corr) and UK100/GER40 (~0.75 corr) are correlated pairs — handled in Step 4.

### Bonds — 5 instruments

**US2YR, US5YR, US10YR, US30YR, BUND**

All five retained. The previous run excluded US2YR based on validation-period SR (−1.45, attributed to ZIRP). ZIRP began in 2009 and fully manifested in the 2010–2017 validation window — this is OOS data. US2YR has 26 years of IS history and low per-roundtrip cost; structural exclusion is not warranted.

All four US maturities handcrafted as one US-rates subgroup in Step 4. BUND is the only non-USD bond — primary fixed-income diversifier.

### Metals — 3 instruments

**XAU, XAG, COPPER**

XAU/XAG (~0.75 corr) treated as precious-metals sub-pair with gold receiving larger weight. COPPER driven by industrial demand and China growth cycle — structurally independent from precious metals (gold/copper corr ~0.25–0.35).

### Energy — 2 instruments

**SpotCrude, Gasoline**

NatGas excluded (structural regime break — see above).

Gasoline included despite ~0.80–0.85 correlation with SpotCrude. The correlation is high but Gasoline carries distinct demand signals (refinery margins, seasonal driving demand, US Gulf Coast supply dynamics) that can diverge from crude in supply-shock episodes. Included as second energy sub-instrument with lower weight than SpotCrude in Step 4.

### Ags/Softs — 8 instruments

**Coffee, Cocoa, Sugar, Corn, Cotton, Soybeans, Wheat**

Previous run included only Coffee, Cocoa, Sugar, Corn, Cotton (5 ags). Soybeans and Wheat dropped on correlation grounds (0.55–0.65 with Corn). This is correlation-based pruning on instruments that are genuinely structurally distinct:

- **Soybeans**: US acreage competes with corn but driven separately by global protein demand (China soy imports), biodiesel policy, and Southern Hemisphere harvest cycles. Corr with Corn ~0.55 — not so high as to justify exclusion given handcrafting will address it.
- **Wheat**: Different geography (US winter vs spring wheat, plus European/Black Sea supply), different end use (food vs feed), partially decorrelated from Corn in weather-shock years. Corr with Corn ~0.60.
- **Cocoa**: Previously excluded in the last run on IS performance grounds (IS SR −0.27). That exclusion was performance-based and illegitimate. 18 years of IS data; structurally independent tropical soft.

---

## Final universe — 29 instruments

| Group | Instruments | Count |
|---|---|---|
| FX | AUDUSD, GBPUSD, USDCAD, USDJPY, EURUSD | 5 |
| Equities | US500, NAS100, GER40, JPN225, HK50, UK100 | 6 |
| Bonds | US2YR, US5YR, US10YR, US30YR, BUND | 5 |
| Precious metals | XAU, XAG | 2 |
| Industrial metals | COPPER | 1 |
| Energy | SpotCrude, Gasoline | 2 |
| Ags/Softs | Coffee, Cocoa, Sugar, Corn, Cotton, Soybeans, Wheat | 7 |
| **Total** | | **29** |

---

## Handcrafting grouping tree (for Step 4)

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
│   ├── European equities
│   │   ├── GER40    (~0.75 corr pair)
│   │   └── UK100
│   ├── JPN225
│   └── HK50
├── Bonds
│   ├── US rates
│   │   ├── US2YR
│   │   ├── US5YR    (~0.80–0.90 within-curve corr)
│   │   ├── US10YR
│   │   └── US30YR
│   └── BUND
├── Commodities
│   ├── Precious metals
│   │   ├── XAU      (~0.75 corr pair)
│   │   └── XAG
│   ├── COPPER
│   ├── Energy
│   │   ├── SpotCrude  (~0.80 corr pair)
│   │   └── Gasoline
│   └── Ags/Softs
│       ├── Grains
│       │   ├── Corn     (~0.55–0.65 corr sub-group)
│       │   ├── Soybeans
│       │   └── Wheat
│       └── Tropical softs
│           ├── Coffee
│           ├── Cocoa
│           ├── Sugar
│           └── Cotton
```

---

## Open items for subsequent steps

- **Gasoline ctrader symbol**: confirm Pepperstone symbol before marking `traded: true`.
- **Soybeans / Wheat / Cocoa tradability**: verify Pepperstone availability; mark `traded: false` for backtest-only if not offered.
- **EURUSD IS window**: only 11 years (1999–2010). Scalar calibration and correlation estimation are noisier. Note at Step 5 variance assessment.
- **US2YR**: very low IS vol (2% ann). At the chosen vol target, position sizes will be large — verify minimum-lot feasibility at Step 4.

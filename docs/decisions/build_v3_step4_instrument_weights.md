# Build v3 — Step 4: Instrument Weights and IDM

**Date:** 2026-08-25
**Status:** Complete
**Config:** `config/universe_v3.yaml`
**State files:** `calibrate/state/step4a_instrument_weights.yaml`, `step4b_idm.yaml`

---

## Tree structure decision

Ags are promoted to a top-level group, separate from Financial Commodities (metals + energy). Structural rationale: ag price drivers (weather, crop cycles, planting/harvest calendars, geographic supply shocks) are entirely orthogonal to financial markets and to commodity price dynamics. Nesting them inside a single Commodities group alongside metals and energy would progressively dilute their budget through three levels of splitting, even though each individual ag instrument is as independently driven as a bond or equity index.

```
Portfolio
├── Equities
│   ├── US [US500, NAS100]
│   ├── European [GER40, UK100]
│   ├── JPN225
│   └── HK50
├── Bonds
│   ├── US rates [US2YR, US5YR, US10YR, US30YR]
│   └── BUND
├── Financial Commodities
│   ├── Precious metals [XAU, XAG]
│   ├── COPPER
│   └── Energy [SpotCrude, Gasoline]
└── Ags
    ├── Grains [Corn, Soybeans, Wheat]
    └── Tropical softs [Coffee, Cocoa, Sugar, Cotton]
```

---

## Step 4a — Instrument weights

### Top-level split

| Class | Weight | Avg inter-class corr |
|---|---|---|
| Equities | 25.2% | +0.033 |
| Bonds | 27.9% | −0.068 |
| Financial Commodities | 23.3% | +0.116 |
| Ags | 23.7% | +0.099 |

Bonds receive the largest share due to negative average inter-class correlation with equities (−0.088) and ags (−0.071). Financial Commodities receive the smallest share because they have a moderate positive correlation with ags (0.287) — both were influenced by the 2000s commodity supercycle in the IS window.

### Equities (25.2%)

| Instrument | Weight |
|---|---|
| US500 | 3.30% |
| NAS100 | 3.30% |
| GER40 | 3.00% |
| UK100 | 3.00% |
| JPN225 | 6.33% |
| HK50 | 6.24% |

JPN225 and HK50 receive ~2× the per-instrument weight of the US and European pairs because those pairs carry high internal correlation (~0.90 US, ~0.67 European), halving their combined effective units.

### Bonds (27.9%)

| Instrument | Weight |
|---|---|
| US2YR | 3.49% |
| US5YR | 3.49% |
| US10YR | 3.49% |
| US30YR | 3.49% |
| BUND | 13.94% |

BUND receives equal budget to the entire US yield curve. On IS position-weighted returns, BUND vs US rates correlation is 0.034–0.049 — essentially uncorrelated. Different ECB vs Fed regimes over the 1984–2010 IS window produce genuinely independent return streams, so the algorithm treats them as two fully independent units.

BUND at 13.94% is a high single-instrument weight. The IS backtest (Step 5) is the right place to validate this — if BUND's IS SR is clearly weaker or stronger than the rest of the portfolio, a manual sub-group weight adjustment (BUND vs US rates budget split) is warranted at that stage.

### Financial Commodities (23.3%)

| Instrument | Weight |
|---|---|
| XAU | 3.80% |
| XAG | 3.80% |
| COPPER | 7.60% |
| SpotCrude | 4.05% |
| Gasoline | 4.05% |

COPPER acts as a standalone industrial instrument (avg sibling corr 0.193 with precious metals and energy); precious metals and energy each form correlated pairs, splitting their sub-budgets equally.

### Ags (23.7%)

| Instrument | Weight |
|---|---|
| Corn | 3.94% |
| Soybeans | 3.94% |
| Wheat | 3.94% |
| Coffee | 2.96% |
| Cocoa | 2.96% |
| Sugar | 2.96% |
| Cotton | 2.96% |

Grains and Tropical softs split the Ags budget equally (Grains ↔ Tropical softs corr = 0.207). Within each sub-group, instruments get equal weight. Grains get slightly more per instrument (3.94% vs 2.96%) because there are 3 vs 4 instruments in the sub-group.

Individual ag weights are now 2.96–3.94% — substantially higher than the 1.04–1.38% from the three-level nesting structure. These are appropriate given each ag's genuinely independent price driver.

**Minimum position size:** at 20% vol target, IDM 2.5, and $100k capital, the smallest ag allocation (Coffee at 2.96%) produces a vol budget of ~$14,800 — well above minimum feasibility for any ag contract.

---

## Step 4b — IDM

**Raw IDM = 3.18 → capped at 2.50**

With ags now receiving ~24% of the portfolio and their near-zero correlations with financial markets and financial commodities, the measured portfolio variance is even lower than the three-group tree:

```
w'Cw = 0.099  →  IDM = 1/√0.099 = 3.18  (capped at 2.5)
```

The cap is appropriate. A raw IDM of 3.18 reflects the estimation noise in the IS correlation matrix at this instrument count — actual forward-looking diversification is unlikely to be this high. The 2.5 cap prevents over-leveraging on noisy IS estimates.

---

## Final Step 4 parameters

| Parameter | Value |
|---|---|
| IDM | 2.5 (capped) |
| BUND weight | 13.94% |
| JPN225 weight | 6.33% |
| HK50 weight | 6.24% |
| COPPER weight | 7.60% |
| Grains (each) | 3.94% |
| Tropical softs (each) | 2.96% |
| US bond maturities (each) | 3.49% |
| Equities — US pair (each) | 3.30% |
| Equities — European pair (each) | 3.00% |
| Precious metals (each) | 3.80% |
| Energy (each) | 4.05% |

Ready for Step 5 — IS backtest and volatility target.

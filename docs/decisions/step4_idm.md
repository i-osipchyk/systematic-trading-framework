# Step 4 — Instrument Diversification Multiplier (IDM)

**Date:** 2026-08-24  
**Status:** Confirmed  
**Calibrated file:** `calibrate/state/07_idm.yaml`  
**IS window:** 1984–2010, 25 instruments

---

## Result

**IDM = 2.500** (capped; uncapped formula gives 3.062)

Formula: **IDM = 1 / √(w′ C w)**

where w = instrument weights vector, C = IS instrument return correlation matrix.

The uncapped value of 3.062 reflects that the 25-instrument portfolio is genuinely highly diversified — most cross-asset-class correlations are near zero in the IS data. The 2.5 cap prevents over-leveraging on theoretical diversification that minimum position sizes would prevent from being realised in practice.

---

## IS instrument return correlation matrix — key readings

**High correlations (expected, reflected in handcrafting):**

| Pair | IS corr | Notes |
|---|---|---|
| US5YR / US10YR | 0.912 | US yield curve — one risk factor |
| US10YR / US30YR | 0.898 | Same |
| US5YR / US30YR | 0.784 | Duration spread across curve |
| US500 / NAS100 | 0.707 | One US equity bet |
| US500 / GER40 | 0.525 | Global equity co-movement |
| EURUSD / GBPUSD | 0.548 | European FX pair |

**Low correlations (confirming diversification value):**

- Most cross-asset-class pairs: 0.00–0.10 in absolute value
- FX vs commodities: near zero throughout
- Bonds vs energy/ags: near zero
- BUND vs US curve: near zero (different central bank dynamics)

**Surprise: Coffee / Cocoa = −0.479**

Strong negative IS correlation between two tropical softs. Both are supply-driven commodity markets with independent geographies (Central/South America for coffee; West Africa for cocoa). Large supply shocks in one crop do not coincide with the other. This is structurally plausible and helps within-ags diversification, but the magnitude (−0.479 over 40 years) may partially reflect limited data. It is not a concern — negative within-group correlation is welcome.

**XAU / BUND = −0.154**

Gold and German long-term bonds were negatively correlated in IS data. Gold is a crisis hedge that performs in inflationary stress; BUND tends to perform in deflationary/low-growth regimes. The sign is economically sensible, the magnitude modest.

---

## Why the cap binds

The IDM cap of 2.5 is standard in Carver's framework. The uncapped formula (3.062) would be valid only if every position could be sized precisely — i.e., fractional contracts. With minimum lot sizes and real account sizes, instruments with small weights (e.g., each ag at 2.0% of a $100k account) can be rounded to zero or one contract, eliminating their diversification contribution. The cap conservatively assumes this rounding effect is material. In practice, the IDM of 2.5 is a realistic estimate for a well-funded account.

---

## IDM in the daily process

```
portfolio_position = subsystem_position × instrument_weight × IDM
```

An IDM of 2.5 means positions are sized 2.5× larger than they would be if the portfolio held only a single instrument. This is the portfolio-level equivalent of the FDM: it rewards genuine diversification with proportionally larger aggregate exposure.

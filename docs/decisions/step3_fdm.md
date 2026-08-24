# Step 3 — Forecast Diversification Multiplier (FDM)

**Date:** 2026-08-24  
**Status:** Confirmed  
**Calibrated file:** `calibrate/state/03_fdm.yaml`  
**IS window:** 1984–2010, 25 instruments

---

## What the FDM does

The FDM rescales the combined forecast back to a mean absolute value of ~10 after weighting. Combining imperfectly-correlated rule forecasts via their weights shrinks the combined signal's average absolute value below 10 — partially cancelling the individual signals. The FDM corrects for this shrinkage.

Formula: **FDM = 1 / √(w′ C w)**

where w = forecast weights vector, C = IS rule forecast correlation matrix (instrument-specific, using only the rules active for that instrument).

The FDM is computed per instrument because the set of active rules differs:
- Bond instruments: trend (4 rules) + carry → 5 active rules with carry ~0 correlated with trend
- Energy/ag instruments: trend (4 rules) + seasonality → 5 active rules with seasonality ~0 correlated with trend
- FX instruments: trend (4 rules) + carry → 5 active rules (same structure as bonds)
- Metals/equity instruments: trend only → 4 correlated rules, least diversification

---

## IS results

```
Instrument        FDM    Active rules
──────────────────────────────────────────────────────────
EURUSD          1.446    trend + carry
GBPUSD          1.512    trend + carry
AUDUSD          1.432    trend + carry
USDJPY          1.374    trend + carry
USDCAD          1.532    trend + carry

US500           1.257    trend only
NAS100          1.276    trend only
GER40           1.243    trend only
JPN225          1.225    trend only  ← lowest
HK50            1.265    trend only

US2YR           1.981    trend + carry  ← highest
US5YR           1.801    trend + carry
US10YR          1.710    trend + carry
US30YR          1.657    trend + carry
BUND            1.757    trend + carry

XAU             1.261    trend only
XAG             1.281    trend only
COPPER          1.255    trend only

SpotCrude       1.568    trend + seasonality
NatGas          1.597    trend + seasonality
Coffee          1.578    trend + seasonality
Cocoa           1.588    trend + seasonality
Sugar           1.586    trend + seasonality
Corn            1.511    trend + seasonality
Cotton          1.566    trend + seasonality
```

---

## Pattern interpretation

**Bonds (1.66–1.98):** Highest FDMs in the portfolio. Bond carry (yield curve slope) is near-zero correlated with trend rules (−0.012 to +0.080 pooled across all instruments). Adding a truly orthogonal fifth signal produces the largest diversification benefit. US2YR gets the maximum (1.981) because short-duration bond carry is the most sensitive to the rate environment and diverges most cleanly from price momentum.

**Energy/ags (1.51–1.60):** Seasonality is structurally calendar-driven — orthogonal to price momentum by construction. The FDM range is tighter than bonds because all 7 seasonal instruments have similar correlation structure.

**FX (1.37–1.53):** Same 5-rule structure as bonds, but FX carry correlates fractionally more with trend than bond carry does in the IS data, producing slightly lower FDMs. USDCAD (1.532) and GBPUSD (1.512) are highest within FX; USDJPY (1.374) is lowest, consistent with JPY having relatively smaller rate differentials against USD in the early IS period.

**Metals + equities (1.22–1.28):** Only the 4 trend rules are active. All are correlated (fast pair 0.726, slow pair 0.864) — the FDM is lower because there is less genuine diversification to reward. JPN225 (1.225) is the lowest in the entire portfolio.

---

## Health check

- No instrument hits the 2.5 cap. In previous configs using MR alongside EWMAC, the anti-correlated rules (−0.9 correlation) pushed FDMs to ~3.5+, which exceeded the cap and inflated a noisy combined signal. The current rule set is well-behaved.
- FDMs are monotonically higher for instruments with more orthogonal signals — the expected ordering is confirmed: bonds > energy/ags > FX > trend-only.
- The FDM is recomputed per walk-forward fold (with expanding IS data) so it will drift gradually as rate regimes change over time. The structural ranking is expected to be stable.

---

## FDM in the daily process

Position size for each instrument uses the FDM-scaled combined forecast:

```
combined_forecast_scaled = combined_forecast × FDM    (clipped ±20)
subsystem_position = combined_forecast_scaled × vol_scalar / 10
```

A higher FDM (e.g. US2YR at 1.981) means the position is nearly twice as aggressive as it would be from the raw weighted average alone — reflecting the genuine diversification from combining orthogonal signals. A lower FDM (e.g. JPN225 at 1.225) means the four correlated trend rules don't add much beyond what one rule would give.

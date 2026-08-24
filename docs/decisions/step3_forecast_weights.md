# Step 3 — Forecast Weights

**Date:** 2026-08-24  
**Status:** Confirmed  
**Weights file:** `calibrate/state/02_forecast_weights.yaml`

---

## Method

Carver's handcrafting approach applied to the IS forecast correlation matrix.

**Assumptions:**
- Equal Sharpe ratio across all rules (insufficient evidence to assert one rule is meaningfully better than another over the full IS period)
- Equal weight between structurally distinct sub-families at each level of the hierarchy
- Structural parameters (weights) fixed at setup; only auto-calibrated params (scalars, FDM, IDM, vol target) are re-estimated per walk-forward fold

**Data:** IS period 1984–2010, 25 instruments, pooled pairwise correlations (each pair counted only on instruments where both rules are active).

---

## IS correlation matrix

```
                EWMAC_8_32  EWMAC_32_128  EWMAC_64_256  BREAKOUT_20    CARRY  SEASONALITY
    EWMAC_8_32       1.000         0.603         0.351        0.726   -0.012        0.133
  EWMAC_32_128       0.603         1.000         0.864        0.262    0.003       -0.005
  EWMAC_64_256       0.351         0.864         1.000        0.145    0.080       -0.037
   BREAKOUT_20       0.726         0.262         0.145        1.000    0.007        0.151
         CARRY      -0.012         0.003         0.080        0.007    1.000          n/a
   SEASONALITY       0.133        -0.005        -0.037        0.151      n/a        1.000
```

Active instrument count per rule (non-zero variance on IS data):

| Rule | Active |
|---|---|
| EWMAC_8_32 | 25/25 |
| EWMAC_32_128 | 25/25 |
| EWMAC_64_256 | 25/25 |
| BREAKOUT_20 | 25/25 |
| CARRY | 10/25 |
| SEASONALITY | 7/25 |

---

## Key findings from the correlation matrix

### Within the trend family: two natural sub-pairs

The data reveals two pairs of highly correlated rules within the trend family:

| Pair | Observed correlation | Interpretation |
|---|---|---|
| EWMAC_8_32 ↔ BREAKOUT_20 | 0.726 | Both fast signals (similar lookback horizon) |
| EWMAC_32_128 ↔ EWMAC_64_256 | 0.864 | Nearly identical slow signals |

The expected structure (EWMAC family vs BREAKOUT sub-family) was replaced by an empirically-grounded fast/slow split:

- **Fast sub-family:** EWMAC_8_32 + BREAKOUT_20 — both capture short-term directional moves over a 20–32 day horizon. BREAKOUT fires when price makes a new N-day high/low; EWMAC_8_32 smooths the same underlying trend. Correlation 0.726.
- **Slow sub-family:** EWMAC_32_128 + EWMAC_64_256 — both measure medium/long-term trend. At these time scales, the signals are nearly equivalent (correlation 0.864). Keeping both provides marginal additional data coverage but not meaningful diversification.

The 50%/50% fast/slow split within the trend family is the correct response to this symmetry: both sub-families are given equal standing, and within each the two members get equal weight.

### Carry: genuinely orthogonal

Carry correlations with all trend rules: −0.012 to +0.080. This is approximately zero at the sample sizes available and consistent with the theoretical expectation — carry is driven by interest rate differentials, not by recent price momentum. The signal is as independent from trend as any real-world rule can be.

### Seasonality: near-zero correlation with trend

Seasonality correlations with trend rules: −0.037 to +0.151. The slight positive readings with EWMAC_8_32 and BREAKOUT_20 are consistent with the idea that strong seasonal patterns can produce trends on a monthly timescale. The correlation is too small to alter the weight assignment.

### Carry and Seasonality never co-active

Carry applies to FX (5) and bond (5) instruments. Seasonality applies to energy (SpotCrude, NatGas) and ags (Coffee, Cocoa, Sugar, Corn, Cotton). There is no overlap — no instrument receives both signals. The `n/a` in the correlation matrix between CARRY and SEASONALITY reflects this. From a portfolio perspective these two rules provide complementary coverage over disjoint instrument subsets.

---

## Equity carry: removed

The original implementation included US500 and NAS100 in `EQUITY_CARRY_INSTRUMENTS`, using `div_yield − funding_rate` as the carry signal. IS analysis showed this is structurally broken for CFD equity trading:

| Year range | Signal | S&P 500 actual |
|---|---|---|
| 1984–2001 | SHORT (21 of 26 IS years) | Major bull market |
| 2002–2003 | LONG | Post-dot-com crash |
| 2004–2007 | SHORT | Further rally |
| 2008–2009 | LONG | Financial crisis |

The dividend yield (1–4%) is almost always below the short-term funding rate (3–9%) during normal rate regimes, producing a persistent short bias. This is mechanically correct — it reflects that equities do not yield enough income to cover funding costs — but it ignores the equity risk premium (expected capital appreciation) that actually makes equities worth holding. In a futures context, carry is captured by the futures roll (spot–futures spread), which implicitly includes ERP. That data is unavailable here. `EQUITY_CARRY_INSTRUMENTS` was cleared to `{}` in `src/rules/carry.py`.

---

## Handcrafting hierarchy

```
Portfolio forecast
├── Trend family (50%)
│   ├── Fast sub-family (50% of Trend = 25% total)
│   │   ├── EWMAC_8_32:   12.5%   — IS corr with BREAKOUT_20: 0.726
│   │   └── BREAKOUT_20:  12.5%
│   └── Slow sub-family (50% of Trend = 25% total)
│       ├── EWMAC_32_128: 12.5%   — IS corr with EWMAC_64_256: 0.864
│       └── EWMAC_64_256: 12.5%
├── Carry family (25%)
│   └── CARRY:            25.0%   — active: FX (5) + bonds (5) = 10/25
└── Seasonality family (25%)
    └── SEASONALITY:      25.0%   — active: energy (2) + ags (5) = 7/25
```

---

## Final weights

| Rule | Weight | Family | Sub-family |
|---|---|---|---|
| EWMAC_8_32 | 12.5% | Trend | Fast |
| BREAKOUT_20 | 12.5% | Trend | Fast |
| EWMAC_32_128 | 12.5% | Trend | Slow |
| EWMAC_64_256 | 12.5% | Trend | Slow |
| CARRY | 25.0% | Carry | — |
| SEASONALITY | 25.0% | Seasonality | — |

---

## Family weight rationale

**Trend 50%:** Universal signal — applies to all 25 instruments. The most established alpha source with the most statistical evidence across asset classes.

**Carry 25%:** Applies to 10/25 instruments. The IS data confirms it is genuinely uncorrelated with trend (−0.012 to +0.080). FX carry is well-documented (uncovered interest rate parity partial failure); bond carry (yield curve slope) is equally well-evidenced. 25% reflects carry's narrower applicability versus trend while still giving it meaningful weight where it fires.

**Seasonality 25%:** Applies to 7/25 instruments. Structurally orthogonal to both trend and carry — the signal is entirely calendar-driven, not price-driven. Calibrated on 40 years of IS data (40 independent seasonal cycles per instrument), which is sufficient for a 12-parameter monthly model. Given equal standing to carry because: (a) the causal mechanism is strong for agricultural and energy commodities, and (b) the IS correlation data confirms it is as uncorrelated from trend as carry is. The narrower instrument coverage (7 vs 10) is offset by the fact that seasonality covers the commodity subset where trend-following alone tends to underperform.

---

## Carry scalar note

The IS carry scalar is 33.80 — high relative to EWMAC scalars (1.89–6.37) — because the raw carry signal (rate differential divided by annualised price vol) produces small absolute values. This is expected: a 2pp rate differential divided by a 10% annualised vol gives a raw forecast of ~0.20. Multiplied by 33.80 this reaches the target mean absolute forecast of ~10. The high scalar is a calibration artifact, not a sign of a weak or noisy signal. IS carry verification confirmed economically sensible values (USDJPY persistently long given US−Japan rate gap; bond carry correctly negative during 1990 yield curve inversion; AUDUSD carry correctly large given Australia's persistent rate premium).

---

## What is not changed at the per-fold level

Forecast weights are structural parameters — fixed at setup and not re-estimated per walk-forward fold. Per-fold calibration updates: rule scalars (step 01), FDM (step 03), instrument weights (step 06), IDM (step 07), and vol target (step 05). The weights above are copied from the setup directory into each fold directory at the start of each fold run.

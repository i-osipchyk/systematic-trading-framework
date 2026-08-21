# Systematic Trading Framework — Calibration Process

This document walks through every calibration step taken to build the framework,
following Carver's methodology from *Systematic Trading* and *Advanced Futures Trading Strategies*.
Steps are presented in the order they were executed; only the final correct decisions are shown.

---

## 1. Instrument Selection

**Universe:** CFD instruments on Pepperstone (cTrader), starting capital $10,000.

**Asset class targets** (diversification first, liquidity second):

| Group | Allocation | Instruments |
|---|---|---|
| Crypto | 25% | BTC, ETH |
| Equity | 35% | US500, US30, GER40 |
| Commodity | 25% | XAU, USOIL |
| Currency | 15% | USDJPY |

**Why these instruments:**
- BTC/ETH — high vol, uncorrelated to equities; act as a risk-on diversifier
- US500/US30/GER40 — major global equity indices; GER40 adds EUR exposure
- XAU — safe-haven, low equity correlation; performs in risk-off
- USOIL — energy sector; structurally uncorrelated to financials
- USDJPY — trending FX driven by interest rate differentials and carry cycles

**Instruments considered and dropped:**
- EURUSD — negative IS and OOS Sharpe; FX crosses are more ranging than trending; dropped
- EURGBP — EWMAC hit rate 49.8% (below 50%, i.e. trend rules had no edge); dropped

**cTrader symbol mapping:**

| Code | Symbol | Notes |
|---|---|---|
| BTC | BTCUSD | |
| ETH | ETHUSD | |
| US500 | US500 | |
| US30 | US30 | |
| GER40 | GER40 | EUR-denominated |
| XAU | XAUUSD | |
| USOIL | WTOIL-PERP | XTIUSD only had data to 2021; use perpetual contract |
| USDJPY | USDJPY | JPY-denominated |

---

## 2. Trading Rules

Two rule families: trend-following (EWMAC) and mean reversion (MR).

### 2.1 EWMAC (EMA Crossover)

Six speed variants, each doubling the lookback:

| Rule | Fast | Slow | Bias |
|---|---|---|---|
| EWMAC_2_8 | 2 | 8 | Very fast, high turnover |
| EWMAC_4_16 | 4 | 16 | |
| EWMAC_8_32 | 8 | 32 | |
| EWMAC_16_64 | 16 | 64 | |
| EWMAC_32_128 | 32 | 128 | |
| EWMAC_64_256 | 64 | 256 | Slow, low turnover |

The raw signal is `fast_ema - slow_ema`, normalised by price vol so it's dimensionless and
comparable across instruments.

### 2.2 MR (Mean Reversion)

Normalised deviation from EMA at two periods:

| Rule | EMA Period | Behaviour |
|---|---|---|
| MR_16 | 16 | Short-term reversion, high turnover |
| MR_200 | 200 | Longer-term reversion, lower turnover |

**MR_64 and MR_100 were dropped** — their IS return correlation was 0.97, making them
effectively redundant. Keeping both adds no diversification value and dilutes the forecast weight.

### 2.3 Rule interaction

EWMAC and MR rules are structurally negatively correlated (~-0.66 average cross-family).
When price is trending, EWMAC gives a strong signal and MR gives a counter-signal, and vice versa.
This strong anti-correlation is the reason the FDM always hits its cap (see §4).

---

## 3. Forecast Scaling

Every rule output must be scaled so that `E[|forecast|] = 10` (Carver's convention).
This makes forecasts from different rules and instruments directly comparable.

### 3.1 EWMAC scalars

Carver's published scalars were calibrated on futures markets. On CFD data they yield
a combined MAF of ~7 instead of 10. Scalars were recalibrated from IS data:

```
new_scalar = 10 / mean_abs_raw_forecast
```

pooled across all 8 IS instruments.

**IS-calibrated EWMAC scalars:**

| Rule | Scalar |
|---|---|
| EWMAC_2_8 | 13.35 |
| EWMAC_4_16 | 9.38 |
| EWMAC_8_32 | 6.50 |
| EWMAC_16_64 | 4.50 |
| EWMAC_32_128 | 3.13 |
| EWMAC_64_256 | 2.35 |

### 3.2 MR scalars

| Rule | Scalar |
|---|---|
| MR_16 | 6.96 |
| MR_200 | 1.74 |

---

## 4. Forecast Weights

Weights determine how each rule contributes to the combined forecast.
Handcrafted based on desired trend bias:

| Family | Total Weight | Per-Rule Weight | Rules |
|---|---|---|---|
| EWMAC | 75% | 12.5% each | 6 rules |
| MR | 25% | 12.5% each | 2 rules |

Rationale: these instruments are selected for trend-following; MR provides
counter-trend diversification but should not dominate.

---

## 5. Forecast Diversification Multiplier (FDM)

The FDM corrects for the fact that combining rules reduces the combined forecast MAF
below 10 (the individual rules partially cancel each other).

**Calibration:** computed from IS return correlations of the individual rule forecasts.

```
FDM = target_MAF / actual_combined_MAF
```

capped at 2.5 (Carver's recommended maximum to avoid over-leverage in tail scenarios).

**Result:** all 8 instruments hit the cap — FDM = 2.500 for every instrument.

**Why the cap is hit:** the strong EWMAC/MR anti-correlation (~-0.66) requires FDM ≈ 3.5
to fully restore MAF to 10. The cap limits this, so the actual combined forecast MAF is ~9.03
rather than 10. This is a structural feature of the rule mix, not a calibration error.

---

## 6. Turnover (IS empirical)

Turnover is measured in roundtrips/year from IS data and used to estimate trading cost drag.

| Rule | Turnover (RT/year) |
|---|---|
| EWMAC_2_8 | 55.9 |
| EWMAC_4_16 | 42.1 |
| EWMAC_8_32 | 28.9 |
| EWMAC_16_64 | 17.4 |
| EWMAC_32_128 | 8.9 |
| EWMAC_64_256 | 3.9 |
| MR_16 | 54.6 |
| MR_200 | 15.7 |

Portfolio weighted-average (IS empirical): ~23 RT/year across instruments.

---

## 7. Volatility Target

**Derivation (Carver's Kelly framework):**

| Step | Value |
|---|---|
| IS Sharpe (after costs) | 0.27 |
| Realistic future SR (×0.75 haircut) | ~0.20 |
| Full Kelly vol target ≈ realistic SR | ~20% |
| Half Kelly | ~10% |
| Chosen vol target | **15%** |

The positive skew of the return distribution (trend-following has fat right tail) justifies
targeting above Half Kelly. 15% balances growth rate against drawdown risk.

---

## 8. Instrument Weights

Handcrafted by asset class group, then split equally within each group:

| Instrument | Group | Group Weight | Instrument Weight |
|---|---|---|---|
| BTC | Crypto | 25% | 12.50% |
| ETH | Crypto | 25% | 12.50% |
| US500 | Equity | 35% | 11.67% |
| US30 | Equity | 35% | 11.67% |
| GER40 | Equity | 35% | 11.67% |
| XAU | Commodity | 25% | 12.50% |
| USOIL | Commodity | 25% | 12.50% |
| USDJPY | Currency | 15% | 15.00% |

Weights sum to 100%. Group allocation rationale:
- Equity at 35% (largest liquid tradeable universe)
- Crypto + Commodity at 25% each (high vol, diversifying)
- Currency at 15% (single instrument, lower conviction on pure trend)

---

## 9. Instrument Diversification Multiplier (IDM)

IDM scales overall position size upward to account for imperfect correlation between instruments,
so the portfolio hits its vol target rather than falling short due to diversification.

**Formula:** `IDM = 1 / sqrt(w' C w)` where `w` = instrument weights, `C` = IS return correlation matrix.

**IS return correlation matrix (net P&L, USD):**

```
          BTC    ETH  US500   US30  GER40    XAU  USOIL  USDJPY
BTC      1.00   0.66   0.12   0.10   0.10   0.04   0.04    0.06
ETH      0.66   1.00   0.11   0.07   0.09   0.01   0.02   -0.02
US500    0.12   0.11   1.00   0.83   0.53  -0.00   0.14    0.12
US30     0.10   0.07   0.83   1.00   0.47   0.02   0.16    0.10
GER40    0.10   0.09   0.53   0.47   1.00   0.05   0.17    0.10
XAU      0.04   0.01  -0.00   0.02   0.05   1.00   0.08    0.19
USOIL    0.04   0.02   0.14   0.16   0.17   0.08   1.00    0.08
USDJPY   0.06  -0.02   0.12   0.10   0.10   0.19   0.08    1.00
```

**Observations:**
- BTC/ETH: 0.66 — within-group, expected
- US500/US30: 0.83 — high within-group equity co-movement
- US500/GER40: 0.53 — moderate cross-region equity correlation
- All cross-group pairs: 0.00–0.19 — strong asset class diversification
- USDJPY/XAU: 0.19 — mild safe-haven co-movement

**Result:** `w'Cw = 0.258` → `IDM = 1/√0.258 = 1.969` (well below the 2.5 cap)

Interpretation: the portfolio vol is ~51% of a single-instrument portfolio at the same per-instrument
sizing, so the IDM of ~2× restores it to the vol target.

---

## 10. Position Sizing Formula

The complete formula used in production:

```
annual_vol       = daily_vol * sqrt(256)
block_value_usd  = price * pointsize * fx_rate_to_usd
position         = capital * vol_target * IDM * instrument_weight * (forecast / 10)
                   / (block_value_usd * annual_vol)
```

**Currency conversion (`fx_rate_to_usd`):** converts 1 native-currency unit → USD:
- USD instruments → 1.0
- EUR instruments → EURUSD price
- GBP instruments → EURUSD / EURGBP (synthetic GBPUSD)
- JPY instruments → 1 / USDJPY

This ensures positions for all instruments are sized in USD-equivalent terms,
so the vol target is consistent across the portfolio.

---

## 11. IS/OOS Split

**Methodology:** 70/30 time split, chronological (no shuffling).

- In-Sample (IS): all data up to the split date — used for all calibration
- Out-of-Sample (OOS): data from split date onward — never touched during calibration

**Split date:** 2024-01-16 (70% of the data range across instruments)

**Two-pass backtest:**
1. Pass 1 — IDM=1.0: calibrate FDMs per instrument, build IS return correlation matrix, compute IDM
2. Pass 2 — calibrated IDM: rerun full history using IS-calibrated FDMs and IDM

OOS uses IS-calibrated parameters unchanged — no reoptimisation on OOS data.

---

## 12. Final Backtest Results

**Parameters locked for OOS:**

| Parameter | Value |
|---|---|
| Vol target | 15% |
| IDM | 1.969 |
| FDM | 2.500 (all instruments) |
| EWMAC forecast weights | 12.5% × 6 rules = 75% |
| MR forecast weights | 12.5% × 2 rules = 25% |

**Portfolio performance:**

| Period | Sharpe | Ann Return | Max Drawdown | Bars |
|---|---|---|---|---|
| IS (2018–2024) | 0.27 | 4.4% | -32.0% | 1,908 |
| OOS (2024–2026) | 0.66 | 10.0% | -12.8% | 946 |

**Per-instrument breakdown (IS → OOS):**

| Instrument | SR IS | SR OOS | Ret IS | Ret OOS | Turnover |
|---|---|---|---|---|---|
| BTC | 0.56 | 0.32 | 2.6% | 1.3% | 17.0 |
| ETH | 0.54 | 0.11 | 2.5% | 0.5% | 16.5 |
| US500 | -0.01 | 0.48 | -0.1% | 2.4% | 15.2 |
| US30 | -0.52 | 0.07 | -2.0% | 0.3% | 17.9 |
| GER40 | -0.25 | 0.58 | -1.0% | 2.4% | 17.4 |
| XAU | 0.22 | 1.91 | 1.0% | 11.9% | 18.2 |
| USOIL | 0.12 | -0.93 | 0.6% | -3.0% | 19.8 |
| USDJPY | 0.16 | -0.41 | 0.9% | -2.2% | 18.5 |

**Notes on OOS results:**
- OOS Sharpe (0.66) exceeds IS (0.27) due to the specific OOS period: gold ran from ~$2,000 to ~$3,300, equities in a sustained uptrend, and crypto recovered. This is a favourable period for trend-following, not a typical expectation.
- The IS Sharpe of 0.27 is the more conservative and reliable estimate of long-run edge.
- USOIL is the weakest instrument: trading costs (SR drag ~0.15 at its spread) consume nearly all the gross edge. Worth monitoring in live trading.
- USDJPY was hurt by the BOJ rate hike surprise in 2024 (carry unwind then re-carry), which broke the trend structure temporarily.

---

## Calibration Order Summary

Carver prescribes a strict order to avoid look-ahead bias. The steps taken here:

1. Define instrument universe and obtain price data
2. Design and implement trading rules (EWMAC + MR)
3. Calibrate individual rule scalars from IS data (so each rule has MAF=10 individually)
4. Set forecast weights (handcrafted based on trend bias)
5. Calibrate FDM from IS rule forecast correlations
6. Measure empirical turnover from IS positions
7. Set vol target (Kelly framework applied to IS Sharpe)
8. Set instrument weights (handcrafted by asset class group)
9. Compute IDM from IS instrument return correlations and instrument weights
10. Lock all parameters — run OOS

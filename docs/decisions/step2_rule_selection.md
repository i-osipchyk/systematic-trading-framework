# Step 2 — Rule Selection

**Date:** 2026-08-24  
**Status:** Confirmed — pending rate data extension (see action items)

---

## Diagnosis: why the current rules are all trend-following

### MR is structurally −EWMAC

The two formulae, from the source code:

```
EWMAC:  raw =  (fast_EMA − slow_EMA) / (price × daily_vol)
MR:     raw = −(price   − EMA)       / (price × daily_vol)
```

When price rises, fast\_EMA > slow\_EMA (EWMAC positive) and price > EMA (MR negative). They are measuring the same underlying fact — "price recently moved up relative to its own average" — with opposite signs. The −0.9 observed correlation is the expected mathematical consequence, not a coincidence. MR in this form is not a mean-reversion rule in any structural sense; it is an inverse-trend rule. Combining an inverse-trend rule with trend rules does not add diversification: it partially cancels the trend signal, requires the FDM to inflate the combined forecast to compensate, and produces a mostly-noise output with a misleadingly large position size. This is the exact failure mode described in the process notes ("combining near-perfectly-anticorrelated rules would push the FDM very high to inflate a mostly-noise signal").

### TSMOM and longer breakouts are redundant with EWMAC

TSMOM (time series momentum over a lookback window) and EWMAC (EMA crossover) both answer the same question: "has this instrument trended over the past N days?" They are the same factor expressed in different functional forms. The 0.5+ pairwise correlation is not surprising — it is the correct diagnosis. Keeping both means paying the weight allocation cost for a second, noisier proxy of the same signal.

BREAKOUT(20) is different in kind: a Donchian channel breakout triggers only when price makes a new N-day high/low, which fires discretely and less frequently than a smoothed EMA. The 20-day lookback sits at the fast end and captures sharp directional moves that a smoothed EMA would still be building up to. BREAKOUT(50), (100), (200) progressively converge toward the slower EWMAC signals and lose this differentiation.

---

## The case for carry

Carry is the one structurally different rule already implemented (`src/rules/carry.py`). Its signal is:

```
raw = (base_rate% − quote_rate%) / (price_vol × sqrt(bars_per_year))
```

This is entirely driven by central bank interest rate differentials — not by recent price movement at all. A country with higher rates attracts capital flows and its currency tends to appreciate; a country with lower rates tends to depreciate. This is an independent causal mechanism from trend-following: carry and trend can align (a high-rate currency is also trending up) or oppose (a low-rate currency is in a strong trend), but the signal source is orthogonal. Expected correlation with EWMAC: approximately 0.15–0.25 in periods where rate differentials are persistent and slowly changing; near zero in periods of rapid rate changes (2022–2023).

For non-FX instruments (equities, bonds, commodities), `carry.py` already returns a zero series — the forecast weight for carry is wasted for those instruments, but this is handled correctly by the per-instrument FDM: instruments without a carry signal get their FDM computed on the trend-only correlation matrix.

### The rate data blocker

The current `src/data/rates.py` contains hardcoded central bank rates starting from 2011. The IS window for a 40-year backtest runs from approximately 1984 to 2010. For the entire IS period, carry would return zero for every instrument, making it invisible to the calibration and useless in the FDM calculation.

FRED provides all the needed series with coverage reaching back to the 1960s–1990s:

| Currency | FRED series | Coverage |
|---|---|---|
| USD | FEDFUNDS | 1954+ |
| EUR | ECBDFR | 1999+ (pre-1999: INTDSREZQ193N for DEM proxy) |
| GBP | BOEBR | 1975+ |
| JPY | IRSTCI01JPM156N | 1960+ |
| AUD | RBATCTR | 1990+ |
| CAD | IRSTCB01CAM156N | 1960+ |

CAD is needed for USDCAD, which is in the 25-instrument universe but not yet in `FX_CARRY_PAIRS`. All other currencies for the 5 FX instruments are already modelled.

Note on EUR before 1999: EURUSD did not exist before the euro launch. The carry signal for EURUSD will naturally have no history before 1999 regardless of the rate proxy used. For GBPUSD, USDJPY, AUDUSD, USDCAD, history extends back to the mid-1970s onwards.

---

## Seasonality (flagged for future consideration)

A calendar-based seasonality signal is genuinely orthogonal to price momentum — the forecast is driven by what month it is, not by recent price movement. It is structurally most appropriate for:

- **Agricultural commodities** (Corn, Coffee, Cocoa, Sugar, Cotton): harvest/planting cycles produce repeatable seasonal price patterns. With 40 years of IS history, the statistical estimation is viable.
- **NatGas**: very strong winter-demand seasonality. Also the instrument most likely to be structurally hostile to trend-following specifically (storage injection/withdrawal causes the sharp reversals that hurt EWMAC). A seasonality rule would be the natural alternative rule family for NatGas.
- **Energy / SpotCrude**: weaker seasonal pattern but real (refinery maintenance cycles, summer driving demand).

Implementation sketch: for each instrument, fit the mean return by calendar month over IS data (possibly as a Fourier series to enforce smoothness). Normalize to forecast scale. Signal updates once per month.

Seasonality is not in scope for the current calibration pass — it needs new implementation in `src/rules/`. It is the recommended next addition once carry is working properly.

---

## Proposed rule set

| Family | Variants | Rationale |
|---|---|---|
| `ewmac` | (8,32), (32,128), (64,256) | 3 well-separated trend speeds; drop (2,8), (4,16), (16,64) |
| `breakout` | 20 | Short-term channel; lower correlation with slow EWMACs; drop 50, 100, 200 |
| `carry` | 1 (rate differential) | Structurally orthogonal driver; FX instruments only |
| ~~`mr`~~ | ~~dropped~~ | Structurally −EWMAC; not a genuine diversifier |
| ~~`tsmom`~~ | ~~dropped~~ | Redundant with EWMAC; same factor, noisier proxy |

Total: **5 rule variants** across 2 families with meaningfully different drivers.

### Expected correlation structure

Within the trend family:

| Pair | Expected correlation |
|---|---|
| EWMAC(8,32) vs EWMAC(32,128) | ~0.50 |
| EWMAC(8,32) vs EWMAC(64,256) | ~0.30 |
| EWMAC(32,128) vs EWMAC(64,256) | ~0.55 |
| BREAKOUT(20) vs EWMAC(8,32) | ~0.40 |
| BREAKOUT(20) vs EWMAC(32,128) | ~0.20 |
| BREAKOUT(20) vs EWMAC(64,256) | ~0.15 |

Cross-family:

| Pair | Expected correlation |
|---|---|
| CARRY vs any EWMAC (FX instruments) | ~0.15–0.25 |
| CARRY vs any EWMAC (non-FX) | 0.0 (zero signal) |

### Preliminary forecast weights (for handcrafting)

Two families: trend and carry. Equal weight at the family level (50/50) is a reasonable prior, given the two families are genuinely different in kind. Within the trend family, BREAKOUT(20) occupies its own sub-family distinct from the three EWMACs.

```
Trend family  (50%):
    EWMAC sub-family (75% of trend = 37.5% total):
        EWMAC_8_32:    ~12.5%
        EWMAC_32_128:  ~12.5%
        EWMAC_64_256:  ~12.5%
    BREAKOUT sub-family (25% of trend = 12.5% total):
        BREAKOUT_20:   ~12.5%

Carry family  (50%):
    CARRY:             ~50%
```

These are starting weights before handcrafting. The handcrafting step will adjust within-trend weights based on the actual observed correlation matrix. Because EWMAC(32,128) and EWMAC(64,256) are more correlated with each other (~0.55) than either is with EWMAC(8,32) (~0.30–0.50), the slow pair may end up slightly downweighted relative to the fast one.

The 50% carry weight reflects the two-family structure (trend vs. non-trend), consistent with Carver's own treatment where carry as a separate family receives roughly equal standing to trend. In practice the effective carry contribution to the portfolio is smaller than 50% because it returns zero for 20 of the 25 instruments — the FDM per instrument corrects for this.

---

## Action items before calibration

1. **Extend `src/data/rates.py`** to cover 1984+:
   - Load historical rates from FRED for USD, EUR, GBP, JPY, AUD, CAD
   - EUR pre-1999: use German Bundesbank rate (`INTDSREZQ193N`) as a proxy; note the discontinuity at 1999 in the record
   - Replace the hardcoded 2011-present table with FRED-sourced data from the earliest available date per currency
   - CAD: add `IRSTCB01CAM156N` (or equivalent) — not currently in rates.py at all

2. **Add USDCAD to `FX_CARRY_PAIRS`** in `src/rules/carry.py`:
   ```python
   "USDCAD": ("USD", "CAD"),
   ```

3. **Update configs** to reflect the new rule set:
   - Remove `tsmom` and `mr` blocks from the config
   - `ewmac` pairs: `[[8,32],[32,128],[64,256]]`
   - `breakout` lookbacks: `[20]`
   - `carry` block: add with `carry: 1.0` as initial scalar placeholder
   - Remove EURGBP from `FX_CARRY_PAIRS` since it is not in the 25-instrument universe

4. **Calibrate carry scalar** — `SCALARS["carry"] = 1.0` in `carry.py` is a placeholder. Once rate data is extended, run step 01 on IS data to calibrate the scalar so the mean absolute carry forecast equals 10.

5. **Run IS correlation matrix** on the proposed 5-rule set to confirm expected correlation structure before finalising weights.

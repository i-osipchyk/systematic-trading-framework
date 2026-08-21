# Walk-Forward Findings and Development Roadmap

This document records what we learned from running walk-forward validation on the current system,
the bugs we fixed and why, and the agreed plan for the next phase of development.

---

## 1. Walk-Forward Validation Results

### 1.1 Setup

The walk-forward (WF) runs use an expanding in-sample (IS) window and a fixed out-of-sample (OOS)
window of roughly one year per fold. All calibration steps (scalars, weights, FDM, IDM, vol target)
are re-run from scratch on each fold's IS data before the OOS window is evaluated.

Config used: `config/default_xag.yaml` — 8 instruments (BTC, ETH, US500, US30, GER40, XAU, XAG,
USDJPY), EWMAC 6 speeds + MR 2 spans.

### 1.2 Key findings

**Vol target Kelly undersizing (critical)**

The biggest performance drag was the Kelly vol target being chronically undersized in early folds.
The formula is:

```
vol_target = sqrt(full_kelly * half_kelly)
           = sqrt(IS_SR * IS_SR * 0.5)   [when IS SR > 0]
           = VOL_FLOOR                   [when IS SR ≤ 0]
```

clipped to `[VOL_FLOOR, 0.40]`.

The expanding IS window includes 2018–2020 (choppy crypto, COVID shock, early trend
failure) even as later folds have strong trend years. This meant IS SR hovered around
0.15–0.25 in early folds, producing `sqrt(0.20 * 0.10) ≈ 0.14`, which was below the
original floor and got clipped to it — 5% in the oldest version, then 10%.

**Fix:** raised `VOL_FLOOR` to `0.15` and raised the lower clip from `0.05/0.10` to `0.15`.
This prevents extreme undersizing without needing the IS SR to justify a reasonable position size.

**IDM near cap**

IDM consistently landed at ~1.85–1.94 across all WF folds. The cap is 2.0 at the instrument
level (not the portfolio cap of 2.5). Near-cap IDM indicates that 8 fairly correlated instruments
(especially BTC/ETH at 0.66, US500/US30 at 0.83) leave little room for diversification multipliers
to help. Expanding the instrument universe with genuinely uncorrelated assets (commodities, more
currencies, Asian indices) is the main lever to improve IDM and thus risk-adjusted position sizing.

**EURUSD as traded instrument**

When EURUSD was added as a ninth traded instrument (with reduced currency/crypto group weights),
portfolio Sharpe was largely unchanged. The mechanism is correct and the code now handles this
without crashing. EURUSD brings genuine trend history — the 2011–2015 period captured the sovereign
debt crisis and ECB QE announcements, which produced strong multi-year EUR trends. Its inclusion
is warranted in the dev period even if the 2018–2026 OOS window is more range-bound.

**EWMAC_2_8 removal**

The fastest rule (EWMAC_2_8) has the highest turnover (~56 RT/year) and the worst cost-adjusted
edge on CFD spreads. Removing it had no material effect on Sharpe but reduced overall portfolio
turnover slightly.

---

## 2. Bugs Fixed

### 2.1 Crash when rule family is omitted from config (`KeyError: 'mr'`)

**Cause:** calibration scripts used `rules["mr"]["spans"]` and `scalars_data["ewmac"]` — hard
dict access fails immediately if either key is absent from the config.

**Fix:** changed all such accesses to `rules.get("mr", {}).get("spans", [])` and
`scalars_data.get("ewmac", {})` across all calibration scripts
(`01_scale_forecasts.py` through `08_backtest.py` and `wf_pipeline.py`).

**Why this matters:** lets us run configs with only EWMAC, or test only MR, without a crash.

### 2.2 Crash when a traded instrument is also an FX conversion helper
(`TypeError: Cannot compare dtypes int64 and datetime64[ns]`)

**Cause:** `required_fx_helpers()` excluded instruments already in the traded list.
When EURUSD was traded, its helper entry was never loaded. The fallback `pd.Series(dtype=float)`
has a RangeIndex (int64), which then failed `.reindex(prices.index)` because prices use a
DatetimeIndex.

**Fix:** after loading the helper map, explicitly check whether any of EURUSD, EURGBP, USDJPY
appear in the traded set but are missing from the helper map, and load them regardless:

```python
for _fx in ("EURUSD", "EURGBP", "USDJPY"):
    if _fx in instruments and _fx not in fx_prices_map:
        fx_prices_map[_fx] = load_adjusted_prices(_fx)
```

Applied in `wf_pipeline.py`, `05_vol_target.py`, `07_idm.py`.

### 2.3 NaN propagation when MR rule family is empty (`combine.py`)

**Cause:** when no MR rules are configured, `mr_df` is an empty DataFrame. Taking
`.mean(axis=1)` of an empty DataFrame returns `NaN` for every row, which then poisons
the combined forecast.

**Fix:**

```python
mr_combined = (
    mr_df.mean(axis=1).clip(-FORECAST_CAP, FORECAST_CAP)
    if not mr_df.empty
    else pd.Series(0.0, index=prices.index)
)
```

---

## 3. Concern About Curve Fitting

Even with walk-forward validation, the OOS windows in our current setup are only ~1 year each.
With 5 folds that gives 5 years of OOS — but the rules, families, and universe were all chosen
while looking at results. This is a form of implicit model selection on OOS data.

**The core issue:** we are not confident that the edge we see is genuine rather than tuned
to the 2018–2026 data period.

**Agreed resolution:** formal dev/test split.

- **Dev period (2011–2018):** used for walk-forward calibration, rule selection, universe
  selection, and hyperparameter choices. All iteration happens here.
- **Test period (2018–2026):** completely blind hold-out. We do not look at results here
  until the dev-period work is finalised. This is treated the same as OOS data in a published
  academic study.

This is a strict discipline — once we start looking at test-period results to make decisions,
that period is no longer a valid test.

---

## 4. Expanded Instrument Universe

### 4.1 Instruments added

| Code | cTrader symbol | Rationale |
|---|---|---|
| GBPUSD | GBPUSD | Liquid FX; strong trends during Brexit/BoE cycles |
| AUDUSD | AUDUSD | Commodity-currency; AUD/USD driven by China demand cycles |
| NAS100 | NAS100 | Tech-heavy index; lower correlation to US500 than US30 |
| UK100 | UK100 | GBP-denominated; different sector mix to GER40 |
| HK50 | HK50 | Asia-Pacific equity; China policy exposure |
| COPPER | Copper | Industrial metal; macro cycle proxy, different from gold |
| NATGAS | NatGas | Energy; low correlation to crude oil |
| JPN225 | JPN225 | Japan equity; BoJ-driven, yen dynamics |
| USDX | USDX | Dollar index; diversifier in currency group |

**Note on USOIL:** on the live Pepperstone account the symbol is `SpotCrude`, not `USOIL` or
`WTOIL-PERP`. The config and data fetch scripts must use `SpotCrude`.

### 4.2 Instruments removed or restricted

| Instrument | Decision | Reason |
|---|---|---|
| US30 | **Removed** | 0.83 IS correlation with US500 — pure redundancy, no diversification value |
| BTC, ETH | **Dev-period only** | Crypto was not a mature or liquid market before 2018; including 2014–2017 data would introduce unusual regime noise into calibration |
| Bonds | **Deferred** | cTrader history only goes back to 2024 — far too short for robust calibration |

### 4.3 Dev vs test instrument sets

**Dev instruments (2011–2018 data window):**
GBPUSD, AUDUSD, EURUSD, USDX, USDJPY, XAU, XAG, US500, GER40, SpotCrude, COPPER

**Test instruments (2018–2026, evaluated once):**
All dev instruments + NAS100, UK100, HK50, NatGas, JPN225

Crypto (BTC, ETH) not included in either set as a primary instrument. They can be evaluated
separately as a satellite with a hard 2018 start.

---

## 5. New Trading Rules Planned

### 5.1 Donchian breakout

**Signal:** goes long when price closes above the N-day channel high; goes short below the
N-day channel low. Normalised to a forecast on the usual [-20, 20] scale.

**Why:** structurally different from EWMAC. EWMAC responds to the *rate of change* of price
(the EMA slope); breakout responds to a *new extreme*, which fires at the start of a move rather
than after momentum has built. The two signals are partially complementary.

**Variants planned:** lookback periods ~20, 50, 100, 200 days (analogous to EWMAC speed variants).

### 5.2 TSMOM (time-series momentum)

**Signal:** total return over the past L months (typically 12), sign gives direction, magnitude
gives position size. Normalised similarly.

**Why:** TSMOM is the basis for most academic momentum literature and has historically been
robust across asset classes. It is a longer-horizon signal than any of our EWMAC variants
(12-month lookback = ~256 days vs EWMAC_64_256's effective window).

**Variants planned:** 3-month, 6-month, 12-month lookbacks.

### 5.3 Rule architecture change needed

The current codebase treats EWMAC and MR as the only two possible rule families, with
hardcoded binary handling throughout `combine.py`, `wf_pipeline.py`, and the calibration scripts.
Before implementing breakout and TSMOM, the rule engine needs to be generalised to support
an arbitrary list of rule families defined in config.

---

## 6. Things Considered and Not Pursued

| Idea | Outcome | Reasoning |
|---|---|---|
| Dropping EURUSD entirely | Reversed | Initially looked poor in 2018–2026 OOS but the IS period 2011–2018 captured strong multi-year EUR trends (sovereign debt crisis, ECB QE). Dropping it would sacrifice genuine diversification. |
| Including bonds | Deferred | Only available from 2024 on Pepperstone. Four months of history is not enough to calibrate a trend rule on. Revisit when history accumulates. |
| Keeping US30 | Dropped | 0.83 correlation with US500 after all calibration. Both are US equities, reacting to the same macro drivers. The instrument weight for US30 provides essentially no diversification. |
| MR_64 and MR_100 spans | Dropped | Their IS return correlation was 0.97 — statistically indistinguishable from each other. Including both dilutes forecast weights with no diversification benefit. |
| BTC/ETH in formal test set | Excluded | Pre-2018 crypto markets were thin, manipulated, and structurally different. A trend rule calibrated on 2011–2018 data would be calibrating on an unusual regime that is unlikely to repeat. Including them would also raise suspicion that OOS results are contaminated by crypto's exceptional 2020–2021 run. |
| Raising FDM cap above 2.5 | Not considered | The cap exists to prevent explosive leverage in tail scenarios. Our FDM already hits the cap for all instruments (the EWMAC/MR anti-correlation requires ~3.5 to fully restore MAF). The right fix is to change the rule mix or adjust weights, not to raise the cap. |
| Intraday rules / H4 calibration | Not yet explored | The framework supports H4 and H1 data. Intraday trend rules would have much higher turnover and cost drag. May be worth exploring after the daily-bar system is stable. |

---

## 7. Implementation Plan

Work proceeds in three phases. The dev-period results gate entry into the test period — we do
not look at test-period Sharpe until the dev system is frozen.

### Phase 1 — Infrastructure (prerequisite for everything else)

**1a. Generalise the rule engine**

The codebase currently treats EWMAC and MR as the only two families, with hardcoded binary
branching in `combine.py`, `wf_pipeline.py`, and the calibration scripts. Before adding breakout
or TSMOM, this needs to become a generic loop over whatever families are declared in config.

Changes needed:
- `src/rules/combine.py` — iterate over rule families from config rather than `if ewmac / if mr`
- `calibrate/01_scale_forecasts.py` through `08_backtest.py` — replace family-specific branches
  with a loop over `rules` keys
- `calibrate/wf_pipeline.py` — same generalisation for scalar loading and forecast construction
- Config schema: each rule family declares `family:` (maps to a Python class) and its parameters

**1b. Implement Donchian breakout rule**

New file `src/rules/breakout.py`. Signal: goes long when price closes above the N-bar high,
short below the N-bar low. Output scaled to MAF=10 on IS data, same as EWMAC/MR.

Variants to calibrate: lookbacks 20, 50, 100, 200 days.

**1c. Implement TSMOM rule**

New file `src/rules/tsmom.py`. Signal: sign of total return over the past L months, magnitude
proportional to return size, normalised to MAF=10.

Variants to calibrate: 3-month (63 days), 6-month (126 days), 12-month (252 days) lookbacks.

---

### Phase 2 — Dev-period calibration (2011–2018)

**2a. Fetch extended history**

Fetch D1 data from 2011-01-01 for all dev instruments: GBPUSD, AUDUSD, EURUSD, USDX, USDJPY,
XAU, XAG, US500, GER40, SpotCrude, COPPER. Use `scripts/fetch_history.py` against the live
Pepperstone account (not demo — live account has deeper history).

**2b. Create dev config**

New file `config/dev_2011_2018.yaml`:
- Instruments: GBPUSD, AUDUSD, EURUSD, USDX, USDJPY, XAU, XAG, US500, GER40, SpotCrude, COPPER
- Date range: 2011-01-01 → 2018-01-01
- Rules: EWMAC (speeds 4–256, drop 2_8), Donchian breakout, TSMOM
- MR: keep for now, evaluate whether it earns its weight in dev WF

**2c. Run walk-forward on dev period**

Multiple WF runs to select the best-performing rule set and universe. Evaluation criteria:
- IS SR averaged across folds
- OOS SR averaged across folds
- IS/OOS SR ratio (closer to 1.0 = less overfitting)
- IDM level (higher = better diversification from the expanded universe)

Decisions to make during dev:
- Which rule families earn their weight (EWMAC, breakout, TSMOM, MR)?
- Which variants within each family are robust vs redundant?
- Which instruments improve IDM without dragging down portfolio SR?
- What instrument weights by asset class group?

**2d. Freeze the dev system**

Once satisfied with dev results, lock all parameters: scalars, weights, FDM, IDM, vol target.
Write them into `config/test_2018_2026.yaml`. Do not change them after this point based on
test-period feedback.

---

### Phase 3 — Test-period evaluation (2018–2026, once only)

**3a. Create test config**

New file `config/test_2018_2026.yaml`:
- Instruments: all dev instruments + NAS100, UK100, HK50, NatGas, JPN225
- Date range: 2018-01-01 → 2026-08-21
- All calibrated parameters from dev freeze carried forward

**3b. Fetch test-period data**

Fetch D1 data for the additional test instruments: NAS100, UK100, HK50, NatGas, JPN225.

**3c. Run single blind evaluation**

Run the frozen system on the test period. This is a one-shot result — do not iterate on it.
If test SR is materially below dev SR, investigate whether the gap is structural (e.g. regime
change post-2018) or a sign of overfitting in the dev period. Either way, the next iteration
starts a fresh dev period, not a re-tuning of the existing one.

---

### Dependency order

```
1a (rule engine generalisation)
 └─ 1b (breakout rule)
 └─ 1c (tsmom rule)
      └─ 2a (fetch history)
           └─ 2b (dev config)
                └─ 2c (dev WF runs)  ← iterate here until frozen
                     └─ 2d (freeze)
                          └─ 3a (test config)
                               └─ 3b (fetch test-period data)
                                    └─ 3c (blind test evaluation)
```

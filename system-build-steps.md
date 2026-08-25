# Building a Systematic Trading System — Process Notes

Based on Robert Carver's *Systematic Trading* framework (Chapter 15, "Staunch Systems Trader"), adapted for a CFD/futures portfolio with a 40-year IS history (1984–2010) and 18-instrument live universe.

---

## Five-step build sequence

The five steps must run in this exact order. Each step's output is a hard input to the next. No OOS data is touched for any purpose — not performance, not correlation, not inclusion decisions — until after all five steps are locked.

```
Step 1: Instrument choice
Step 2: Rule selection
Step 3: Rule correlations, trading speed, and forecast weights
Step 4: Instrument weights
Step 5: IS backtest and volatility target
─────────────────────────────────────────────────────────────
         (lock everything → one-shot OOS validation)
```

---

## Step 1: Instrument choice

**Principle: start broad, prune by structure — never by performance.**

Begin with a wide candidate set drawn from intuition and data availability. The goal is to end up with enough instruments to achieve genuine diversification across uncorrelated drivers of return (asset classes, geographies, supply/demand cycles). More instruments is better than fewer at this stage — the handcrafting method in Step 4 handles correlated clusters by downweighting them; you don't need to exclude them upfront.

**Inclusion criteria:**
- **Diversification**: spread across asset classes (FX, equities, bonds, commodities) and sub-classes (within commodities: metals, energy, ags). Instruments in the same sub-class (e.g. US500 and NAS100, or US5YR and US10YR) can both be included — their within-group correlation gets absorbed by uneven handcrafting weights.
- **Contract size**: larger pointsize reduces position rounding error at a given capital level. A contract so large that the minimum lot produces 5× the target vol allocation is practically unusable.
- **Standardised cost**: spread + commission + slippage expressed in SR units. Rule of thumb: standardised cost should be well below 0.13 (the combined cost ceiling from Step 3) on its own, so room exists for transaction cost drag from the trading rules.

**Pruning discipline:**
- **Correlation-based pruning is fine to do empirically** — correlation between price series is a structural property, not a fitted result. Computing it on IS data and using it to inform grouping and inclusion doesn't introduce overfitting.
- **Performance-based pruning is not fine** — dropping an instrument because it backtested poorly on IS data uses the same data you will validate against and inflates apparent OOS performance by construction. The only legitimate performance-based exclusion is a persistent, long-history underperformance with an independent economic explanation (regime change, structural cost mismatch), and even then the preferred first move is re-matching the instrument to a different rule family rather than dropping it.
- All selection work is done on **IS data only**.

**Common correlation clusters to watch:**
- US500 / NAS100: typically 0.85+; treat as one unit in handcrafting
- US5YR / US10YR / US30YR: highly correlated yield curve; treated as one sub-group
- XAU / XAG: ~0.70–0.80
- EUR/USD / GBP/USD: ~0.60–0.75
- Within ags (corn / sugar / coffee / cotton): lower cross-correlations, more genuinely independent

**Output of Step 1:** a finalized list of instruments that will be traded. This list is fixed for all subsequent steps.

---

## Step 2: Rule selection

**Principle: start broad, prune by diversification intuition — never by performance.**

Begin with a wide candidate set of rule families. The system's edge comes from combining genuinely uncorrelated rule families, not from finding the single best rule. Rule correlation is the key criterion at this stage — not backtested SR.

**Rule families and diversification:**
- **Trend-following** (EWMAC, breakout, TSMOM): all express the same underlying momentum hypothesis. They will be correlated within the family (~0.4–0.8). Multiple speeds within a trend family are worth keeping — different speeds capture different holding periods. Rule weights handle the within-family correlation (Step 3).
- **Carry**: interest-rate-differential-driven, structurally different from price-momentum rules. For CFDs, swap/financing rates serve as carry signal. This is the most genuinely decorrelated family from trend-following.
- **Seasonality**: calendar-driven, most relevant for ags (corn, coffee, sugar, cotton have documented planting/harvest cycles). Decorrelated from price-momentum rules by construction.
- **Mean reversion at the same timescale as trend rules**: typically approaches –0.9 correlation with trend, which is not diversification — it's cancellation. Avoid unless operating at a genuinely different timescale or on different instruments.

**Rule pruning criterion:**
- Drop a rule family only if it is structurally redundant with another family (correlation > 0.8 across the portfolio) or if no instrument survives the cost filter in Step 3.
- Do not drop based on backtested SR. Rules with similar SR but lower correlation are worth more in combination than rules with better SR but high correlation.

**Output of Step 2:** a finalized set of rule families and variants (e.g. EWMAC_8_32, EWMAC_32_128, EWMAC_64_256, CARRY, SEASONALITY). Fixed for all subsequent steps.

---

## Step 3: Rule correlations, trading speed, and forecast weights

This step has three sub-components that run together, not sequentially:

### 3a — Compute forecast scalars

For each rule variant, find the scalar such that the mean absolute forecast = 10 when applied to IS data, pooled across all instruments. This normalises forecast magnitude across rules so a forecast of +10 always represents the same position sizing signal.

Seasonality is instrument-specific (per-instrument monthly mean returns, scaled to max abs = 10).

### 3b — Compute rule correlation matrix

Compute pairwise correlations of the scaled forecasts across all rule variants, pooled across instruments. This is the input to handcrafting.

Typical structure:
- Within trend family (EWMAC speeds): 0.4–0.7
- Trend vs carry: 0.0–0.3
- Trend vs seasonality: 0.0–0.2
- Carry vs seasonality: 0.0–0.2

### 3c — Cost filtering per rule-instrument pair

For each rule variant, estimate annualised turnover (roundtrips per year) from IS positions. Apply the cost ceiling:

```
max standardised cost ≈ 0.13 / turnover
```

The 0.13 constant is Carver's cost budget: annual cost drag capped at approximately half the expected per-rule pre-cost SR. Any rule-instrument pair where the instrument's standardised cost exceeds this ceiling should be dropped for that instrument (the rule still applies to other instruments that clear the bar).

Fast rules (high turnover) require cheap instruments. Slow rules have a more relaxed ceiling. This is the only legitimate reason to drop a rule-instrument combination.

### 3d — Handcraft forecast weights

Using the rule correlation matrix, assign weights to each rule variant via the handcrafting method:
1. Group rules by family (Level 1: e.g. trend, carry, seasonality)
2. Assign top-level weights across families based on number of genuinely independent families and their correlations
3. Within each family, split the family's budget proportionally, downweighting more correlated variants

Compute the Forecast Diversification Multiplier (FDM) per instrument:

```
FDM = 1 / sqrt(w′ · Corr · w)
```

where w = forecast weights vector, Corr = rule correlation matrix. FDM rescales the combined forecast back to mean absolute = 10 after correlation-driven cancellation shrinks it. Higher FDM = more rule diversification. FDM is capped (Carver caps at ~1.5–2.5 depending on rule count) to prevent inflating noisy signals.

**Output of Step 3:** forecast scalars, forecast weights, FDM per instrument. Fixed for all subsequent steps.

---

## Step 4: Instrument weights

**Must come before the IS backtest** — the backtest requires instrument weights to compute portfolio-level PnL and SR.

**Principle:** same handcrafting approach as forecast weights, applied at the instrument level.

### Correlation input

Compute pairwise correlations of IS instrument returns (position-weighted daily PnL, or daily price returns as a proxy) across all instruments in the finalized set from Step 1.

### Handcrafting

1. Group instruments by asset class, then sub-class (e.g. Commodities → Precious / Industrial / Energy / Ags)
2. Within each sub-group, assign weights inversely proportional to within-group correlation (highly correlated pairs get equal shares of a smaller combined allocation; low-correlation instruments get more)
3. Across groups, assign weights based on the number of genuinely independent units each group contributes — a group of 3 highly correlated instruments has fewer independent units than a group of 3 low-correlated instruments
4. Use rounded correlation bands (~<0.2 / 0.2–0.4 / 0.4–0.6 / 0.6–0.8 / >0.8), not exact values — precision here overfits to the IS correlation matrix

### Instrument Diversification Multiplier (IDM)

Same formula as FDM, applied to instrument weights and the instrument correlation matrix:

```
IDM = 1 / sqrt(w′ · Corr · w)
```

Cap IDM based on instrument count (Carver's approximate caps: 2 instruments → 1.20, 5 → 1.50, 10 → 1.80, 20+ → 2.50). The cap prevents over-leveraging when the measured correlation matrix is noisier than the true structural correlations.

### Minimum position size check

At the chosen vol target and IDM, check that each instrument's allocation produces at least ~1 contract on most days. An instrument that rounds to zero position most of the time is effectively not traded — either bump its weight above the functional minimum or exclude it.

**Output of Step 4:** instrument weights, IDM. Fixed for all subsequent steps.

---

## Step 5: IS backtest and volatility target

**This is the only step where backtested performance is explicitly used as a decision input.**

**OOS data is not touched at this step.** The val and test periods are reserved for the one-shot validation that follows after all five steps are locked. Running Step 5 on IS data only is not a limitation — the vol target is derived from Kelly analysis on the IS SR, and IS SR is approximately scale-invariant to the vol target choice. Looking at val/test here would contaminate the one-shot validation.

### Run the IS backtest

With all parameters locked from Steps 1–4, run a full portfolio backtest on **IS data only**:

- Vol target: use a placeholder (e.g. 20%) to produce meaningful SR — SR is approximately scale-invariant to the vol target choice
- Apply FDMs from Step 3, IDM from Step 4
- Apply instrument weights from Step 4
- Report: IS SR, IS annual return, IS max drawdown, per-instrument IS SR only
- Do not split the output into val/test — OOS data stays locked

### Cross-validation function of the IS backtest

The IS backtest is not just for measuring SR — it validates Steps 1–4:

- **Per-instrument SR with realistic variance**: an instrument with IS SR < −0.5 over a long history is a signal to revisit the inclusion decision or rule-matching, not to tune parameters
- **Per-rule SR**: a rule with near-zero IS SR across instruments suggests the scalar calibration or rule implementation has a bug, or the rule genuinely has no IS edge (legitimate reason to revisit Step 2)
- **Turnover cross-check**: confirm actual IS turnover per instrument matches the estimates used in Step 3's cost filtering
- **IDM validation**: confirm realized portfolio vol matches vol_target × IDM — if not, IDM estimate or instrument weights have an error

### Choose the vol target

1. Apply an OOS degradation discount to the IS SR: **discounted SR ≈ IS SR × 0.75** (Carver's rule of thumb). Use a more aggressive discount (0.50–0.60) if any performance-based pruning occurred in Steps 1–4 or if the IS window is short (<15 years).
2. At the discounted SR, compute half-Kelly vol target: `vol_target ≈ discounted_SR / 2` (as a fraction of capital)
3. Cross-check against IS max drawdown: at the chosen vol target, is IS max DD within your tolerance? IS max DD is a best-case bound — OOS drawdowns will typically be worse.
4. Choose the final vol target within the range where (a) it is at or below half-Kelly, and (b) the implied IS max DD is tolerable. Carver's examples range 15–35%.

**The vol target is a risk sizing tool, not a performance tool.** If IS SR is disappointing, the correct response is to audit Steps 1–4, not to reduce the vol target. Reducing vol target scales both returns and drawdown equally (SR is unchanged) and does not improve the system's edge.

**Output of Step 5:** final vol target. This, combined with Steps 1–4 outputs, fully specifies the system. At this point, commit and do not adjust further based on OOS results.

---

## One-shot OOS validation

After all five steps are locked, run the system on OOS data exactly once:

- Compare OOS SR to the discounted IS SR estimate. A large gap signals overfitting somewhere in Steps 1–4.
- Check OOS max drawdown against what the chosen vol target implies.
- If validation and test periods are both available (e.g. Val 2010–2017 and Test 2018–2026), use the validation period for diagnostics and the test period for the final one-shot result. Do not use the test period for any tuning.
- Any adjustments based on OOS results (removing instruments, changing weights) must be treated as a new calibration cycle — re-run all five steps on the extended IS data before touching OOS again.

---

## Daily process (once the system is fully specified)

1. Get current account value
2. Daily vol target = annualised cash vol target ÷ √256
3. Get latest prices and FX rates
4. Calculate daily price volatility per instrument (exponentially weighted, ~25-day lookback)
5. Compute raw forecast per rule variant; apply scalar; cap at ±20
6. Combine forecasts using weights from Step 3; apply FDM; cap combined forecast at ±20
7. Volatility scalar = daily cash vol target ÷ instrument value volatility
8. Subsystem position = combined forecast × volatility scalar ÷ 10
9. Portfolio position = subsystem position × instrument weight × IDM
10. Round to minimum lot; apply position inertia buffer (avoid trading on small changes)
11. Issue trades

---

## IS / OOS discipline — key rules

- **All correlation analysis, scalar calibration, FDM, IDM, and weight decisions use IS data only.**
- **OOS data is never looked at for any purpose until the one-shot validation.**
- **Performance-based pruning on IS data inflates apparent OOS SR by construction.** The only valid pruning criteria are: structural (correlation clustering), cost (Step 3 ceiling), and minimum position size (Step 4 feasibility).
- **Walk-forward re-optimization is not the same as walk-forward validation.** Re-tuning parameters on each year's new data as it arrives is rolling re-optimization; it will look better than a genuinely frozen system would. Run a plain fixed-OOS test (fit once, freeze, apply unchanged) to measure the actual robustness of the design.

# OOS Validation — Review Protocol

Run after all five steps are locked and the user has executed the one-shot OOS validation.
This is a review-only session — no edits are made. Findings feed into the next build's Step 1/2.

The user will share (or AI will read from the results directory) a results table with columns:
`Instrument | IS SR | Val SR | Test SR | IS Ret | Val Ret | Test Ret`
plus asset-class and rule-level breakdowns if available.

---

## Cut 1 — Portfolio level

Report the IS → Val → Test SR trajectory. Frame it against the discounted IS SR estimate
(IS SR × 0.75) that was used to set the vol target:

- **OOS SR ≥ discounted estimate:** the discount was appropriate or conservative. Note this is
  also partly luck — which market regime fell in the OOS window matters.
- **OOS SR moderately below discounted estimate (0.5–1.0× discounted):** expected range; no
  alarm.
- **OOS SR materially below discounted estimate (<0.5×) or negative:** signals meaningful
  overfitting somewhere in Steps 1–4. Proceed to cuts 2–4 to locate the source.

Also report:
- Whether Val and Test SR move in the same direction (consistent signal) or diverge (one period
  drove all the result)
- OOS max drawdown vs. IS max drawdown. OOS DD exceeding IS DD by >1.5× is not unusual for
  trend-following but should be noted.

---

## Cut 2 — Asset class level

For each asset class, compare IS SR → Val SR → Test SR. Identify:

**Held up (both Val and Test positive):** the class's IS performance was real and structural.
Note this for building conviction in the next build.

**Delayed (Val negative, Test positive):** often explained by a regime shift at the Val boundary
(e.g. zero-rate era → rate normalisation). Check whether the Val underperformance has an economic
explanation consistent with trend-following theory. If yes, this is not overfitting — it is a
regime effect. Bonds in 2010–2017 (QE-era range-bound rates) are a canonical example.

**Reversed (Val positive, Test negative):** rarer and more concerning. Suggests the IS edge was
specific to the IS period's market structure rather than a persistent phenomenon.

**Consistently negative (both Val and Test negative):** the IS SR for this class was likely noise
or IS-fitted. Flag as a structural concern for the next build's Step 1.

---

## Cut 3 — Rule family level

For each rule family, compare IS SR → Val SR → Test SR across all instruments.

Key questions:
1. **Does the family contribute positively in both OOS windows?** A family that is consistently
   positive OOS (even at a lower SR than IS) is doing its job.
2. **Did the IS SR leader become the OOS laggard?** This is the signature of IS overfitting.
   Seasonality is the canonical risk here: per-instrument monthly scalars are calibrated on IS
   patterns that may not persist. If seasonality's OOS SR is near zero while its IS SR was high,
   the seasonality weight should be reduced in the next build.
3. **Does trend (EWMAC) broadly hold up across speeds?** Slow speeds (EWMAC_32_128, EWMAC_64_256)
   tend to be more robust OOS than fast speeds because their signals are less noise-sensitive.
   If fast speeds drag OOS, consider narrowing the speed range in the next build.

Overfitting signal threshold: if a family's OOS SR is <0.10 while its IS SR was >0.50, this is
a meaningful IS→OOS decay that warrants revisiting the family's weight in the next build.

---

## Cut 4 — Instrument level

Flag any instrument with Val SR < −0.30. These are candidates for review in the next build's
Step 1 discussion.

**Flagging is not exclusion.** The OOS results of a finished build cannot retroactively change
that build. Flags are inputs to the next build's Step 1 structural discussion only.

For each flagged instrument, assess:
1. **Is there an economic explanation for the Val underperformance?**
   (e.g. Bonds in QE era, a commodity during a supply-shock regime, a currency during a central
   bank intervention cycle)
   - If yes: the instrument may be worth keeping in the next build; the Val underperformance
     was regime-driven, not structural.
   - If no: the instrument is a stronger candidate for exclusion from the next build.

2. **Does the Test SR recover?**
   - If Val < −0.30 and Test > 0.00: likely a regime effect; keep and monitor.
   - If Val < −0.30 and Test also negative or near zero: the weakness persists across two
     independent OOS windows — this is a stronger structural flag.

3. **Is the instrument's IS SR high while both OOS periods are weak?**
   This is the overfitting signature for an individual instrument. It suggests the instrument's
   IS edge was noise or IS-specific (e.g. its IS period happened to coincide with a trend
   regime that the instrument is particularly sensitive to).

Threshold summary for instrument flags:
| Val SR | Test SR | Classification |
|---|---|---|
| < −0.30 | > 0.00 | Regime-driven; monitor |
| < −0.30 | < 0.00 | Structural concern; strong flag for next build Step 1 |
| < −0.30 | < −0.30 | Exclusion candidate; review in next build Step 1 with full structural argument |

---

## Assembling findings for the next build

After completing all four cuts, produce a summary with two sections:

**Decisions that held up:**
- List structural choices (groupings, inclusions, rule families) confirmed by OOS results.
- These become higher-conviction starting points for the next build.

**Flags for the next build's Step 1/2:**
- List instruments with Val SR < −0.30 and their classification (regime vs structural).
- List any rule family where OOS SR < 0.10 vs IS SR > 0.50 (overfitting signal).
- Note any asset class with consistent OOS weakness.
- Note whether fast EWMAC speeds dragged OOS (if yes, consider starting the next build's Step 2
  with EWMAC_8_32 as the fastest speed).

**Important:** these flags are inputs to the next build's open-minded Step 1 discussion. They are
not carry-overs. Each new build starts fresh — prior OOS observations inform the structural
discussion but do not automatically exclude anything. The new build's Step 1 must justify every
inclusion and exclusion on structural grounds using IS data only.

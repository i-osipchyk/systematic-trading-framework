# Systematic Trading Framework — AI Guidelines

Carver-style systematic trading framework for CFD/futures portfolios. Calibration follows a strict
5-step in-sample build, then a one-shot OOS validation. Every system lives under
`systems/<name>/config/` with step-numbered config files and `results/run_log.yaml`.

---

## Collaboration model

AI and user build each system together. Role split:

| Who | Does what |
|---|---|
| AI | Asks structured questions, flags structural problems, proposes concrete edits |
| User | Approves or adjusts AI proposals, runs all pipeline commands, owns all decisions |

**AI may directly edit files for Steps 1–5** after discussing and getting explicit approval.
OOS results are reviewed together; no edits are needed there.

---

## IS/OOS discipline — non-negotiable rules

These rules exist to prevent overfitting. Any violation inflates apparent OOS SR by construction.

1. **All calibration uses IS data only.** OOS data is never looked at for any purpose — not
   performance, not correlation, not inclusion decisions — until the one-shot validation at the end.
2. **No performance-based pruning.** Dropping an instrument or rule because it backtested poorly is
   not allowed. The only valid pruning criteria are: structural (correlation clustering above 0.80),
   cost (Step 3 ceiling), or minimum position feasibility (Step 4).
3. **Correlation-based decisions are fine.** Correlation between price series is a structural
   property, not a fitted result. Using it to group or exclude instruments is not overfitting.
4. **Vol target is a risk tool, not a performance tool.** If IS SR is disappointing, revisit Steps
   1–4. Lowering the vol target scales both returns and drawdown equally; SR is unchanged.
5. **Any adjustment based on OOS results starts a new build.** Re-run all five steps on extended IS
   before touching OOS again.

---

## File conventions

```
systems/<name>/
  config/
    instruments.yaml   # instrument list with metadata (Step 1)
    rules.yaml         # rule families and variants (Step 2)
    step3.yaml         # scalars, forecast weights, FDM, turnover (Step 3)
    step4.yaml         # group_weights, instrument_weights, IDM (Step 4)
    step5.yaml         # vol_target (Step 5)
  results/
    run_log.yaml       # pipeline execution log with all locked parameters
```

When starting work on a system, read `results/run_log.yaml` to see which steps are complete.

---

## Step 1 — Universe definition (joint discussion → AI edits `instruments.yaml`)

**Goal:** a final instrument list with genuine diversification across uncorrelated return drivers.
More instruments is better — handcrafting in Step 4 absorbs correlated clusters.

**Conduct this discussion before any pipeline run:**

Ask the user:
1. What asset classes are in the candidate set? (FX, equities, bonds, commodities, crypto)
2. What data source and broker are they using? (affects symbol availability and spread costs)
3. Are there instruments from prior builds flagged for structural review?

Then assess the candidate set against these criteria, in order:

**Diversification across asset classes:** each class should have at least 2 instruments if possible.
Instruments within the same sub-class are fine to keep — handcrafting handles their correlation.

**Correlation clusters to flag** (from historical data; use these as prior unless user has
IS correlation data showing otherwise):
- US500 / NAS100 / US30: typically 0.80–0.90 — treat as one unit in handcrafting
- US equities / EU equities (GER40, UK100): 0.50–0.65
- US2YR / US5YR / US10YR / US30YR: 0.70–0.90 within the curve; duration sub-groups
- BUND vs US bonds: 0.30–0.50 (different central bank, genuinely diversifying)
- XAU / XAG: 0.70–0.80
- Within ags (corn, coffee, sugar, cotton, soybeans): 0.20–0.45 — lower than metals
- BTC / ETH: 0.60–0.70
- Crypto vs equities: 0.10–0.20 (episodic correlation spikes in risk-off)

**Cost flag:** if the user has spread data, check whether the instrument's standardised cost
(spread / daily_vol_in_price_terms) is likely above 0.13 even for slow rules. If yes, flag it —
this instrument will likely fail cost filtering in Step 3 for all but the slowest rules.

**Minimum position feasibility:** at the user's capital level and intended vol target, each
instrument needs to produce at least ~1 contract on most days. Flag any instrument whose
minimum lot size is too large relative to the expected allocation.

When discussion is complete, propose the updated `instruments.yaml` — add or remove instruments,
update the `traded` field. Do not edit `weight` fields; those are set in Step 4.

---

## Step 2 — Rule selection (joint discussion → AI edits `rules.yaml`)

**Goal:** a set of rule families that are structurally uncorrelated with each other.
Multiple speeds within a trend family are fine — they diversify holding period, not logic.

**Conduct this discussion before any pipeline run:**

Ask the user:
1. Which rule families are candidates? (EWMAC, seasonality, carry, breakout, TSMOM, MR, other)
2. Any families from prior builds that underperformed structurally (not just poor IS SR)?

Then assess each family against the rule correlation structure:

**Rule families and their structural correlations:**
- EWMAC vs breakout: 0.85–0.90 (nearly identical momentum logic) — keep only one unless speeds differ meaningfully
- EWMAC vs TSMOM: 0.80–0.85 — also structurally redundant with EWMAC
- EWMAC vs seasonality: 0.00–0.20 — genuinely diversifying
- EWMAC vs carry: 0.00–0.25 — genuinely diversifying
- EWMAC vs MR (same timescale): –0.80 to –0.90 — not diversification, cancellation; avoid
- Seasonality vs carry: 0.00–0.20 — genuinely diversifying

**Drop threshold:** drop a rule family if its correlation with another included family exceeds 0.80
(structural redundancy). Do not drop based on expected IS SR.

**EWMAC speed selection:** start with the full speed range (4_16 through 64_256). Remove a speed
only if: (a) its correlation with an adjacent speed exceeds 0.90, or (b) it will fail cost
filtering for all instruments in Step 3. EWMAC_2_8 typically fails cost filtering on most
instruments (turnover ~55 RT/year → cost ceiling 0.0024 SR units, tighter than most spreads).

When discussion is complete, propose the updated `rules.yaml`.

---

## Step 3 — Forecast weights (AI reads step3.yaml → proposes edits to `02_family_weights.yaml` or step3.yaml)

**User runs the pipeline first, then shares or AI reads the step3 output files.**

Read `systems/<name>/config/step3.yaml` (or the intermediate files if the pipeline produces them
separately). The key fields:

**Scalars (`scalars:`):** verify they are in the expected range. Typical values:
- EWMAC_4_16: 8–12 | EWMAC_8_32: 5–8 | EWMAC_16_64: 3–5 | EWMAC_32_128: 2–4 | EWMAC_64_256: 1.5–3
- Seasonality: instrument-specific monthly values; check that the per-month scalars are not
  wildly large (>30) for most instruments — that signals IS overfitting of seasonal patterns

**Turnover (`turnover:`):** apply the cost filter for each rule:
```
max_standardised_cost = 0.13 / annual_turnover
```
If the user knows an instrument's standardised cost (from spread data), flag any rule-instrument
pair where the instrument's cost exceeds this ceiling. That rule should not be applied to that
instrument.

**FDM (`fdm:`):** the Forecast Diversification Multiplier. If FDM hits its cap (typically 2.5) for
all instruments, the rule mix has strong anti-correlation (e.g. MR mixed with EWMAC). This is not
wrong — it's a structural consequence — but it limits effective leverage and should be noted.

**Handcrafting forecast weights:** the goal is to assign weight proportional to each family's
genuine, independent contribution to the combined forecast.

Algorithm:
1. Group rules by family. Each family gets a top-level weight.
2. Assign top-level family weights based on: (a) how many genuinely independent signals the family
   adds, and (b) any intentional bias toward a family (e.g. trend-heavy system).
3. Split the family's budget equally across its variants (different EWMAC speeds count as variants
   within the trend family, not as separate families).

Heuristics for family weight distribution:
- Two families with low inter-family correlation (0.0–0.20): 50/50 is a neutral starting point;
  adjust toward the family with more variants if they span a wider range of timescales
- One dominant family + one diversifier: 70/30 to 80/20 is a reasonable range
- Seasonality in particular: given its IS overfitting risk (monthly scalars fit to IS patterns),
  weight it conservatively — 10–20% maximum unless there is strong structural evidence for higher

Propose the family weights as a concrete dict. Explain the reasoning in one sentence.
After user approves, edit the relevant field in `step3.yaml` (or `02_family_weights.yaml` if the
pipeline uses separate files).

---

## Step 4 — Instrument weights (AI reads step4.yaml → proposes edits)

**User runs the pipeline, then AI reads `systems/<name>/config/step4.yaml`.**

The editable fields are `group_weights` and (if overriding within-group equal split)
`instrument_weights`. The pipeline derives `instrument_weights` from `group_weights` by splitting
equally within each group; AI may override individual instruments if correlation data justifies it.

**Handcrafting instrument weights:**

Algorithm:
1. Group instruments by asset class (e.g. index, bond, commodity, crypto, currency).
2. Assign top-level group weights based on number of genuinely independent units per group.
   A group of 3 highly correlated instruments (e.g. US500/NAS100/US30) counts as ~1.3–1.5
   independent units. A group of 3 low-correlated instruments (e.g. Coffee/Sugar/Cotton) counts
   as ~2.5–3 independent units.
3. Within each group, split equally by default. Override only if within-group correlation data
   clearly supports uneven weights (e.g. US10YR and US30YR very similar → downweight one; BUND
   structurally different from US bonds → give it its own sub-bucket).

**IDM:** verify `idm` in step4.yaml is within Carver's caps:
- 5 instruments: ~1.50 | 10 instruments: ~1.80 | 15 instruments: ~2.10 | 20+ instruments: ~2.50
If IDM equals the cap (2.5), the portfolio is hitting the diversification ceiling — fine, but
note it.

**If the user provides the IS instrument correlation matrix** (terminal output or CSV), use it
to verify that within-group and cross-group correlations match the structural priors from Step 1.
Flag any pair whose correlation differs materially from the Step 1 prior — it may indicate a data
issue or a genuine structural change.

Propose `group_weights` as a concrete dict. Explain the group independent-unit count briefly.
After approval, edit `step4.yaml`.

---

## Step 5 — IS backtest and vol target (AI reads results → proposes vol_target edit)

**User runs the IS backtest. AI reads `results/run_log.yaml` for the Kelly analysis and
per-instrument breakdown.**

**IS SR cross-validation checks:**

- Per-instrument SR: flag any instrument with IS SR < −0.30 over a long history (>15 years).
  This is a signal to revisit Step 1 inclusion rationale — not grounds to drop automatically.
- Per-rule SR: a rule with near-zero IS SR across all instruments suggests a scalar calibration
  bug or a genuine no-edge result. Revisit Step 2.
- Turnover cross-check: confirm actual IS turnover per instrument matches Step 3 estimates.
  Material divergence (>30%) means the cost filter ceiling used in Step 3 was wrong.

**Vol target selection:**

The Kelly analysis in `step5.yaml` (or run_log.yaml) provides:
- IS Sharpe
- Realistic SR (IS SR × 0.75 discount)
- Full Kelly and half-Kelly vol targets

Selection logic:
1. Start at half-Kelly as the conservative anchor.
2. Trend-following systems with positive skew can target above half-Kelly — up to the geometric
   mean optimum (approximately 2/3 of full Kelly).
3. Apply a more aggressive discount (×0.50 instead of ×0.75) if: any performance-based pruning
   occurred in Steps 1–4, IS window is shorter than 15 years, or the IS SR seems unusually high
   relative to prior builds on similar universes.
4. Cross-check: at the chosen vol target, is the IS max drawdown within tolerance? OOS drawdowns
   will be larger — typically 1.2–1.5× the IS max DD.

Propose a specific vol_target value with one-sentence rationale. After approval, edit `step5.yaml`.

---

## OOS validation — joint review

After all five steps are locked, user runs the one-shot OOS validation.
AI conducts a structured review across four cuts. See `docs/ai-guidelines/oos_review.md` for
the full protocol.

Brief summary of what AI does:
1. Portfolio-level: compare OOS SR to the discounted IS SR estimate; flag large gaps
2. Asset class: identify which classes held up and which did not
3. Rule family: identify which families contributed OOS vs. dragged
4. Instrument: flag any with Val SR < −0.30 (candidates for next build's Step 1 review)

OOS results inform the next build's Step 1 and Step 2 discussions. They do not change the current
system — any adjustment requires a new full build.

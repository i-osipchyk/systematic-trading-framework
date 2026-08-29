# Building a Systematic Trading System — Process Notes

Based on Robert Carver's "Staunch Systems Trader" framework (Chapter 15), adapted for a CFD portfolio (no futures, no native carry contracts) with a candidate instrument set of:

`EURUSD, USDJPY, US500, NAS100, GER40, XAUUSD, XAGUSD, COFFEE, CORN, SUGAR, USTN10YRF, USTN2YRF, EUROBUNDF`

plus an expanded candidate list under consideration: `GBPUSD, USDX, US30, UK100, HK50, COPPER, CACAO, WHEAT`.

Data available: daily prices from 1992 (some instruments from 1984).

---

## Overview: correct dependency order

The chapter presents its steps in a narrative order (1→6, then daily process). The actual *calculation* dependency order is different, because some steps (backtesting, choosing a vol target) depend on outputs of later-numbered steps (forecast weights, instrument weights). The real build order is:

1. Instrument selection & correlation analysis (structural, in-sample only)
2. Rule selection & rule correlation analysis (in-sample only)
3. Forecast weights (handcrafting, per instrument)
4. Instrument weights (handcrafting, across the portfolio)
5. Cost filtering (rule × instrument, via turnover/standardised cost)
6. Full in-sample backtest → Sharpe Ratio estimate
7. Discount SR for realistic forward performance
8. Choose volatility target (uses discounted SR + risk tolerance + skew)
9. Position sizing math (daily process)
10. Out-of-sample validation (one-shot, on a previously untouched dataset)

Everything through step 8 uses **in-sample data only**. OOS data is not looked at for *any* purpose — not performance, not correlation, not instrument inclusion — until step 10.

---

## Step 1: Instrument choice — size, diversification, costs

**What the framework asks for:**
- Enough diversification (spread across asset classes)
- Large contract sizes (keeps rounding error in position sizing small)
- Avoid instruments with high cost relative to their own volatility (measured as "standardised cost" in SR units)

**Q: Is "avoid low-volatility instruments" really about avoiding currencies as a category?**
A: No. It's about cost relative to volatility for *any* instrument, not currency-specific. A volatile EM currency like MXP/USD can clear the bar; a low-volatility instrument in any asset class can fail it. Table 42's "standard cost SR" column is what actually measures this.

**Q: Is diversifying across FX, equities, commodities, bonds — with sub-diversification inside each (e.g. multiple indices, multiple metals, multiple softs, a few bonds) — a reasonable approach?**
A: Yes, and it's actually closer to a real Carver-style portfolio than the book's 6-instrument teaching example. Caveats:
- Within-class instruments won't diversify each other as much as across-class ones (e.g. US500 vs NAS100 often 0.85+ correlated — closer to one bet split two ways than two independent bets).
- Gold/silver, EUR/USD vs GBP/USD-style majors, and grains (corn/wheat) tend to cluster.
- Softs like coffee/corn/sugar are more genuinely diversifying from each other.
- The handcrafting method (see Step 4) is specifically designed to absorb these clusters via uneven within-group weighting rather than requiring you to drop correlated instruments.

**Q: Is the candidate 13-instrument list reasonable?**
A: Yes overall — 5 asset groups, no single class dominating. Specific notes:
- US500/NAS100 likely to behave as one equity bet; GER40 adds more genuine diversification.
- XAUUSD/XAGUSD historically correlate ~0.7–0.8+.
- USTN10YR/USTN2YR correlated but capture different duration exposure — reasonable to hold both (same logic Carver uses for multiple bond maturities).
- USTN10YR/EUROBUND more genuinely diversifying (different central banks/economies).
- EURUSD/USDJPY reasonably diversifying from each other (JPY can act as risk-off/safe-haven, decoupling from EUR in stress).
- Missing: no EM/high-volatility FX pair — both FX pairs are low-vol majors relative to account risk, similar to the "avoid low-volatility instruments" trap from Step 1's own logic. Something like USD/MXN, USD/ZAR, or USD/TRY would diversify better and clear the cost-per-volatility bar more easily.

**Q: Worth expanding the candidate list further (GBPUSD, USDX, US30, UK100, HK50, copper, cacao, wheat), then pruning by correlation?**
A: Build the expanded candidate list using intuition first, then confirm/refine with **in-sample correlation analysis** (not performance-based pruning — see the note on pruning discipline below). Specific reads on the expanded candidates:
- US30 alongside NAS100/US500: very likely redundant (large-cap US equity, likely 0.85+ correlated).
- GBPUSD alongside EURUSD: likely adds less than a structurally different pair.
- USDX: dollar index dominated by EUR (~57%) and JPY (~14%) weighting — likely *more* redundant with EURUSD than GBPUSD would be, despite not looking obviously redundant at first glance.
- HK50: genuinely interesting — different monetary policy/growth driver than US/Europe equities, can decouple in some regimes.
- Copper: different demand driver (industrial/China growth-linked) than precious metals or ags — likely genuinely diversifying.
- Cacao: highly idiosyncratic price action (West African supply shocks) — good diversification candidate, but check liquidity/cost on CFDs.
- Wheat alongside corn: grains tend to correlate with each other more than corn does with coffee/sugar — likely adds less than copper or cacao.

**Pruning discipline (applies throughout, not just Step 1):**
- **Structural/correlation-based pruning is fine to do empirically** — correlation between price series is a stable structural property, not a fitted result, so using it to decide inclusion doesn't create the overfitting problem below.
- **Performance-based pruning (dropping an instrument or rule because it backtested poorly) is not fine to do casually** — doing this uses the same data you're about to validate against, and inflates apparent OOS performance by construction.
- Exception: an instrument/rule combination with a *persistent, long-history, economically explainable* structural mismatch (not just a noisy bad number) can be reconsidered — but the better first move is usually re-matching it to a more suitable rule family (see Step 2) rather than dropping it outright, and any such decision should ideally be checked against data that was never used for the decision itself.
- All correlation-based selection work happens on **in-sample data only**.

---

## Step 2: Selecting trading rules

**What the framework asks for:**
- Choose rule families (book uses EWMAC + Carry)
- For carry, use a contract further out on the curve than the nearest one (avoids roll/expiry distortion) — not directly applicable to CFDs
- Filter rule variants by cost: faster rules (higher turnover) need cheaper instruments; Table 43 gives turnover and max standardised cost per rule speed

**Q: How do I calculate turnover and max standardised cost for my own rules/instruments, since I can't just take Carver's table values?**
A: Carver's table has a hidden constant: turnover × max standardised cost ≈ 0.13 for every row. This reflects a cost budget capping annual cost drag (in SR units) at roughly half of an assumed ~0.26 pre-cost SR per rule. So:
- **max standardised cost ≈ 0.13 / turnover**
- Turnover itself is empirical: backtest the rule to get its scaled forecast series (avg absolute forecast ≈ 10), compute the annualized average absolute day-to-day change in that forecast, divide by roughly 2× the average absolute forecast level.
- Turnover for a given rule *speed* tends to be fairly stable across instruments (driven mostly by lookback parameters), so one backtest per rule variant (on a representative liquid instrument) is often enough, rather than testing every instrument separately.

**Q: I trade CFDs, not futures — carry doesn't work the same way. I'm adding time series momentum, breakout, and mean reversion instead. Good set?**
A: Partial concern: EWMAC, TSMOM, and breakout are all trend-following at the core and will likely be correlated with each other (confirmed empirically: 0.5–0.9). Mean reversion is the one different-logic candidate, playing the role carry played in the original chapter — but check it's actually usefully diversifying once backtested, not just labeled differently.
- Carry isn't necessarily unavailable on CFDs: most brokers charge/pay overnight financing (swap rates) reflecting interest rate differentials — functionally a carry signal. Worth testing if historical swap data is available, especially for FX and index CFDs, since it would restore the original two-family (trend + genuinely different family) structure.

**Q: My mean reversion rule is ~-0.9 correlated with all trend rules — it hurts in trending periods, doesn't help in ranging ones. Worth finding an uncorrelated rule instead of adding more trend variants?**
A: Yes. A correlation that close to -1 usually means the rule isn't capturing a separate phenomenon — it's structurally close to the mathematical inverse of the trend signal (e.g., "fade when far from a moving average" ≈ negative EWMAC). A genuine diversifier should sit closer to 0, not the opposite extreme. Candidates, roughly ordered by how structurally different they are from trend:
- **Carry via swap/financing rates** — most structurally different (interest-rate-driven, not price-action-driven).
- **Relative value / skew between correlated instrument pairs** (e.g. US500 vs NAS100, USTN10YR vs EUROBUND) — driven by spread dynamics, not either leg's own trend.
- **Seasonality** — especially relevant for the ag instruments (corn, coffee, sugar have real planting/harvest cycles); calendar-driven, not price-momentum-driven.
- **Volatility-regime-based signals** — different underlying driver than price direction.
- **Mean reversion at a very different timescale** (e.g. intraday vs the current swing-timescale MR) — may decorrelate better even under the same "MR" label.
- Diagnostic before adding anything new: check whether the current MR's construction is literally derived from the same moving average as the trend rules — if so, that structural similarity, not the "mean reversion" label, explains the -0.9.

**Q: What does Carver actually say about rule correlation — what should it look like ideally?**
A: Not "aim for zero." Correlation within a rule family (e.g. across EWMAC speeds) is expected and handled via uneven weighting (handcrafting), not exclusion — Carver's own EWMAC-speed-vs-speed correlations mostly sit around 0.3–0.7. Across families (e.g. trend vs carry), he wants low or even slightly negative correlation, but not extreme — because averaging two near-perfect opposites cancels signal rather than diversifying it, and the Forecast Diversification Multiplier (see Step 3) then inflates a mostly-cancelled, noisy combined signal rather than recovering real edge. Rough target: ~0.3–0.7 within-family, closer to 0 (not extreme negative) across-family.

**On rule pruning specifically:** don't drop a correlated rule variant — downweight it via handcrafting (see Step 3). The valid reason to drop a rule-instrument combination is the cost filter (turnover × cost ceiling), not correlation, and not backtested performance.

---

## Step 3: Forecast weights and trading speed (per instrument)

**What the framework asks for:**
- Handcrafting method: group rules by family (1st level), then across families (2nd level)
- Assume equal historical SR across rules (hard to prove statistically they differ)
- A rule with higher within-family correlation gets a lower forecast weight (e.g. EWMAC 32,128 got 8% vs ~21% for the others, specifically because of its higher correlation with other EWMAC speeds)

**Q: What is the 1.31 multiplier?**
A: The **Forecast Diversification Multiplier (FDM)**. Combining several imperfectly-correlated forecasts via their weights shrinks the combined forecast's average absolute value below the target of 10 (correlation-driven cancellation). The FDM rescales the combined forecast back up to the standard target.
- Formula (page 311 referenced in source notes): FDM = 1 / √(w′ Corr w), where w = forecast weights, Corr = the rules' correlation matrix.
- More diversifying (lower-correlated) rules → smaller weighted-correlation term → larger multiplier needed.
- More correlated rules → smaller multiplier needed.
- This directly ties diversification quality to position sizing: the combined forecast feeds Step 5/6's position sizing math, so a well-diversified rule set produces appropriately sized positions rather than systematic under-trading.
- Connects to the -0.9 MR discussion: combining near-perfectly-anticorrelated rules would push the FDM very high to compensate for cancellation — inflating a mostly-noise signal rather than recovering real edge. A well-behaved rule set (0.3–0.7 within-family, low-but-not-extreme across-family) keeps the FDM modest and meaningful.
- The same multiplier concept reappears at the instrument level in Step 4 as the **Instrument Diversification Multiplier** (1.89 in the source example).

**Note on rule correlation matrix scope:** compute correlations across all rule variations you're actually using (this feeds handcrafting directly). Doesn't necessarily need to be recomputed per instrument if turnover/correlation behavior is stable across instruments for a given rule speed — but the full rule-vs-rule matrix is a required input.

---

## Step 4: Volatility target calculation

**What the framework asks for:**
- Start from trading capital (e.g. $250,000)
- Choose a percentage volatility target (e.g. 20%) reflecting how much you're willing to put at risk
- Annualised cash volatility target = Trading capital × Volatility target % (e.g. $250,000 × 0.20 = $50,000)
- Risk adjustment happens daily, based on *current* account value, not the original starting capital

**Q: How is the 0.53 backtest SR obtained if the system (e.g. instrument weights) isn't finished yet? Isn't this circular — vol target depends on SR, but SR depends on a completed system?**
A: Resolved by two facts:
1. **SR is roughly scale-invariant to the chosen vol target** — doubling the vol target roughly doubles both returns and risk proportionally, so you don't need your *final* vol target chosen to get a meaningful SR estimate; a placeholder value works.
2. **Instrument and forecast weights only need a correlation matrix of returns** (price returns for instruments, forecast returns for rules) — this is a separate statistical exercise on raw historical data, not dependent on a completed, calibrated system.

Actual sequencing: forecast weights (Step 3) and instrument weights (Step 4/6) are derived from in-sample correlations first (independent of each other, can be done in parallel) → full system assembled and backtested at a placeholder vol target → SR estimate obtained → SR discounted for realistic forward performance (0.75 factor in the source example, giving 0.53 × 0.75 ≈ 0.4) → *then* the real vol target is chosen using that discounted SR plus personal risk tolerance and system skew. The vol target choice does not feed back into the SR estimate — it only determines position size given the already-measured edge.

**Where the 20%/0.75 factors come from:** not derived mechanically — the 0.75 OOS-degradation discount is Carver's own rule of thumb (could reasonably be more conservative with a shorter or more idiosyncratic dataset); the vol target itself is a subjective choice balancing the discounted SR, the system's skew (the example is "slightly positive skew," typical of trend-following — occasional large wins, frequent small losses, which can typically tolerate a somewhat higher vol target for the same subjective risk-of-ruin), and genuine personal capacity for drawdown. Carver's own examples across the book range roughly 15–35%.

---

## Step 5: Position sizing and measuring price volatility

**What the framework asks for (per instrument, per day):**
1. Daily volatility target (A) = annualised cash vol target ÷ √256
2. Price (B) — current market price
3. Point/tick value (C) — fixed instrument specification
4. Block value (E) = C × B ÷ 100 — cash value of one contract
5. Price volatility % (G) — moving-average estimate of daily price movement as % of price
6. Instrument currency volatility (H) = G × E
7. Instrument value volatility (I) = H × D (D = FX rate, converts to account currency)
8. Volatility scalar (J) = A ÷ I — contracts needed at forecast +10 to fully use the daily risk budget

**Purpose:** normalizes wildly different per-contract dollar volatility across instruments (e.g. $170 vs $546 per contract in the source example) so a forecast of +10 means the same risk exposure regardless of instrument.

**On lookback choice:** price volatility (G) depends on the lookback window used for the moving average of price changes — shorter lookback reacts faster but is noisier, longer is smoother but slower to adapt. This choice also interacts with the standardised cost calculation from Step 1/2, since cost-as-fraction-of-volatility shifts with how volatility itself is measured (source notes show 0.113 vs 0.105 SR depending on 5-week vs 20-week lookback).

This scalar feeds Step 6's position sizing: Subsystem position = combined forecast × volatility scalar ÷ 10.

---

## Step 6: Portfolio of trading subsystems (instrument weights)

**What the framework asks for:**
- One subsystem per instrument
- Instrument weights via handcrafting: group instruments hierarchically (asset group → asset class → instrument), weight within and across groups based on correlation
- Adjust for practical constraints (e.g. minimum position size / minimum blocks)
- Compute Instrument Diversification Multiplier (IDM) — same math as the FDM, applied to instrument correlations and weights

**Q: Is this the same idea as rule weighting — e.g. gold/silver (0.7 correlated) get smaller combined weight than corn/sugar (lower correlated), for diversification?**
A: Correct in spirit, with two refinements:
1. **It's hierarchical, not a flat all-pairs comparison.** Gold and silver sit together in a "precious metals" subgroup and split weight *within* that group based on their mutual correlation (same as the Euro Stoxx/V2TX 0.42-correlation → 66.6%/33.3% split in the source example). Subgroups are then compared to each other at higher levels (e.g. metals vs ags within commodities, then commodities vs equities vs FX vs bonds). This avoids the instability of a full-portfolio mean-variance optimization across all instruments at once, which Carver deliberately avoids.
2. **It uses rounded correlation bands, not exact continuous values** (roughly <0.2 / 0.2–0.4 / 0.4–0.6 / 0.6–0.8 / >0.8, mapped to standard split ratios) — intentional, since exact correlations from limited historical data are noisy and precise optimization against them tends to overfit.

**Applying to the 13-instrument candidate list**, an example grouping tree:
- Rates: USTN10YR, USTN2YR, EUROBUND (split within by US vs EU sub-branch)
- Equities: US500, NAS100 (correlated pair, split unevenly), GER40 (own slice)
- Metals: XAUUSD, XAGUSD (split unevenly given ~0.7 correlation)
- Softs: COFFEE, CORN, SUGAR (likely closer to even split if genuinely low-correlated)
- FX: EURUSD, USDJPY (split based on mutual correlation)
- These 5 groups then weighted against each other at the top level.

**On minimum position size constraints:** an instrument whose weight × vol target rounds to under ~1 contract most of the time is effectively unusable — either force a minimum weight (as the source example did for equities, bumping 25%→30% to let Euro Stoxx clear a 4-block minimum) or exclude it.

---

## Cost filtering (applies across Steps 2 and 6)

- Estimate standardised cost per instrument (spread + commission + typical slippage, in SR units, using actual broker costs) — same logic as Table 42's cost column.
- Backtest turnover per rule variant (per instrument, or pooled per rule speed if stable across instruments).
- Apply the ≈0.13/turnover ceiling per rule-instrument combination; drop any combination that fails it (same logic as the fast-EWMAC-on-V2TX exclusion in the source example).
- This is the *correct* place to drop a rule-instrument pairing — not correlation, not backtested performance.

---

## Daily process (once the system is fully specified)

1. Get account value
2. Volatility target: annual ÷ √256
3. Get latest prices
4. Get latest FX rates
5. Calculate price volatility using lookback, FX rates, and block value for each instrument
6. Calculate forecast per rule, cap it
7. Combine forecasts using weights (Step 3), cap the combined forecast
8. Volatility scalar: daily cash volatility target ÷ instrument value volatility
9. Subsystem position: combined forecast × volatility scalar ÷ 10
10. Portfolio instrument position: subsystem position × instrument weight × instrument diversification multiplier
11. Round to target position
12. Issue trades, considering position inertia (avoid churning on small changes)

---

## In-sample / out-of-sample methodology

**Data available:** daily prices from 1992 (some instruments from 1984). Prior approach: split IS/OOS at 2010, then walk-forward validation year by year on the OOS period.

**Q: Is this split/walk-forward approach correct?**
A: Reasonable and arguably better than a single static split. Notes:
- The 1992/1984–2010 IS window covers multiple genuine regimes (dot-com boom/bust, several rate cycles, 2008 boundary) — good for handcrafting correlations and setting rule parameters.
- Year-by-year walk-forward gives a more honest OOS picture than a single static holdout.
- Important distinction: **walk-forward should mean re-testing the fixed system each year, not re-optimizing parameters each year.** If parameters/weights are re-tuned using each new year's data as it arrives, that's rolling re-optimization, not OOS validation — it will look better than a genuinely fixed, unmaintained system would. Worth being explicit about which is actually being done.
- Worth running a plain fixed-OOS test (fit once, freeze, run through all OOS years unchanged) alongside the rolling version — they answer different questions ("does this exact design survive untouched" vs "does this build process produce good systems repeatedly") and it's useful to know if they diverge.
- 2008 sitting at the IS/OOS boundary is worth a specific check — confirm rule/weight choices weren't implicitly shaped by knowledge of how 2008 played out.

**Q: If some instruments/rules underperform, is it OK to drop them for OOS testing?**
A: Depends on what's driving the underperformance, and *when* the decision is made:
- **Never drop based on IS or OOS backtested performance alone** — this uses the same data being validated against and inflates apparent OOS results by construction (classic overfitting/selection bias).
- **A persistent, long-history, economically explainable structural mismatch is a different case** — e.g. natgas at SR -1 over a long history has a known structural cause (storage/injection-withdrawal seasonal dynamics causing sharp reversals — exactly what hurts trend-following via whipsaw); broad OOS failure across developed FX trend-following is a documented industry-wide pattern (linked to post-2008 central bank intervention/QE suppressing sustained directional moves). These are closer to real findings than noise, *if* consistent across the whole IS period and every rolling OOS fold, with an independent economic rationale — not just "the number was bad."
- **Preferred first move: re-match the instrument to a better-suited rule family rather than dropping it outright** — e.g. test natgas under seasonality/MR rather than trend; test currencies under carry (swap-rate-based) rather than trend, given the swap rate data being pulled anyway.
- **Any post-hoc pruning still costs some validity** — the "final" OOS SR on survivors is somewhat optimistic since the data was used for both evaluation and selection. If enough history exists, the cleanest fix is a further held-back slice never looked at until after pruning decisions are made, purely to confirm the pruning generalizes.
- **Apply a larger discount factor than the standard 0.75** if any pruning occurred, since a design adjusted based on what was seen in the OOS window deserves more skepticism than one that wasn't touched.

**Q: For the expanded instrument candidate list — is it worth trying more assets and pruning by correlation after the fact, or just deciding intuitively upfront?**
A: Correlation-based pruning (unlike performance-based pruning) is low-risk to do empirically, since correlation between price series is a stable structural property rather than a fitted result. Process: use intuition to build the initial expanded candidate list (saves effort on obviously-redundant pairs like US30 alongside NAS100/US500, or GBPUSD alongside EURUSD), then confirm/refine with **in-sample correlation analysis** for the less obvious cases (USDX vs EURUSD, HK50, copper, cacao, wheat). This determines inclusion and the handcrafting grouping tree — done entirely on in-sample data, before any backtest.

**Q: Is instrument/rule correlation analysis for selection done on IS or OOS data?**
A: **In-sample only, always.** Correlation-based selection is structural (not performance-based) but still counts as "looking at the data" — OOS data must remain completely untouched, for any purpose, until the final one-shot validation step. Computing correlations on OOS data to decide inclusion would contaminate the test even though it feels more benign than performance-based selection.

---

## Suggested build sequence (concrete steps)

**Phase 1 — Data and split**
1. Pull historical price data for all candidate instruments (daily minimum; finer granularity if testing intraday MR variants).
2. Confirm IS/OOS split (2010 boundary) and walk-forward structure before looking at results; ensure both IS and OOS periods contain some regime variety.
3. Pull swap/financing rate history for FX and index CFDs (for carry rule testing).

**Phase 2 — Rule selection (IS only)**
4. Finalize rule parameters (EWMAC speeds, TSMOM lookback, breakout window, MR construction) on IS data.
5. Test carry (swap-rate-based) and seasonality (esp. ags) as candidates to supplement or replace the -0.9-correlated MR rule.
6. Compute rule correlation matrix (IS data).
7. Derive forecast weights via handcrafting; compute FDM per instrument.

**Phase 3 — Instrument weights (IS only)**
8. Compute instrument return correlation matrix (IS data) across the finalized candidate list (original 13 + any expanded candidates that survive the correlation check).
9. Build the grouping tree; handcraft weights within and across groups.
10. Compute IDM.
11. Check minimum-position-size feasibility per instrument given actual account size.

**Phase 4 — Cost filtering**
12. Estimate standardised cost per instrument (actual broker costs).
13. Backtest turnover per rule variant.
14. Apply the ≈0.13/turnover ceiling; drop failing rule-instrument combinations.

**Phase 5 — IS backtest and vol target**
15. Backtest the assembled system at a placeholder vol target → IS SR estimate.
16. Apply OOS-degradation discount factor.
17. Choose real vol target using discounted SR, skew, and drawdown tolerance.

**Phase 6 — OOS validation**
18. Run the fully fixed system (nothing re-optimized) on the untouched OOS data.
19. Compare OOS SR to the discounted IS estimate; a large gap signals overfitting somewhere in Phases 2–4.
20. Check OOS drawdown depth/duration against what the chosen vol target implied.

**Phase 7 — Live preparation**
21. Build the daily process pipeline using the validated, fixed parameters.
22. Paper trade before committing real capital, since CFD execution (slippage, financing rate changes, broker quirks) can differ from backtest assumptions.

**Open decision:** re-optimization cadence going forward (e.g. quarterly/annual weight recomputation vs. fixed-until-broken) — Carver generally favors infrequent, disciplined re-estimation over frequent tweaking, since constant re-optimization on live data is itself a form of overfitting.

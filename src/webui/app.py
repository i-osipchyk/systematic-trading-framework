"""Calibration pipeline web UI (Streamlit). Launch with ``trading-ui``.

Lets you run each calibration step from the browser instead of a terminal,
then review results split by IS / Test (see docs/ai-guidelines and
CLAUDE.md for the methodology this mirrors). Steps 1-5 normally block on a
terminal Enter keypress to confirm; here they auto-confirm whatever is
currently on disk in config/. Instruments/rules (Steps 1-2) are edited by
hand, via "Build a new universe" above, or via the AI in Claude Code; the
Step 3-5 "AI edits" fields — forecast_weights, group/instrument_weights,
vol_target — have dedicated editors under each step below (config_editor.py),
so overriding the computed defaults never requires opening a YAML file.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.webui import config_editor, discovery, results, rule_builder, step_summary, universe_builder
from src.webui.runner import run_step

_STEP_FORMATTERS = {
    "0": step_summary.format_step0,
    "1": step_summary.format_step1,
    "2": step_summary.format_step2,
    "3": step_summary.format_step3,
    "4": step_summary.format_step4,
}

SYSTEMS_ROOT = Path(__file__).parents[2] / "systems"

st.set_page_config(page_title="Trading Framework — Calibration", layout="wide")
st.title("Systematic Trading Framework — Calibration")

# --- build a new universe (Step 1 + Step 2 scaffold) -------------------------

with st.expander("Build a new universe"):
    st.caption(
        "Pick instruments and rule families/variants from the vetted candidate catalogs to "
        "scaffold a new system (instruments.yaml + rules.yaml from your picks; base.yaml copied "
        "from a template). Review asset-class diversification, correlation clusters, cost, and "
        "position-size feasibility per CLAUDE.md's Steps 1-2 — this is a starting point, not a "
        "substitute for that discussion."
    )

    st.markdown("### Instruments")
    instrument_catalog = universe_builder.load_candidate_catalog()
    groups: dict[str, list[str]] = {}
    for code, meta in instrument_catalog.items():
        groups.setdefault(meta.get("asset_type", "other"), []).append(code)

    selected_instruments: set[str] = set()
    for asset_type, codes in groups.items():
        st.markdown(f"**{asset_type.title()}**")
        cols = st.columns(min(len(codes), 4))
        for i, code in enumerate(codes):
            meta = instrument_catalog[code]
            label = f"{code} — {meta.get('description', '')}"
            help_text = (
                f"currency={meta.get('currency')}  pointsize={meta.get('pointsize')}  "
                f"spread_cost={meta.get('spread_cost')}"
            )
            if cols[i % len(cols)].checkbox(label, key=f"ubuild_{code}", help=help_text):
                selected_instruments.add(code)

    for hint in universe_builder.correlation_hints(selected_instruments):
        st.warning(hint)

    st.markdown("### Rules")
    rules_catalog = rule_builder.load_candidate_rules()

    selected_families: dict[str, list[str]] = {}
    for family, cfg in rules_catalog.items():
        variants = rule_builder.family_variants(family, cfg)
        if variants is None:
            if st.checkbox(family, key=f"rbuild_family_{family}"):
                selected_families[family] = []
            continue
        if st.checkbox(family, key=f"rbuild_family_{family}"):
            cols = st.columns(min(len(variants), 6))
            chosen = []
            for i, label in enumerate(variants):
                is_ewmac_2_8 = family == "ewmac" and label == "2_8"
                default = not is_ewmac_2_8
                help_text = "Typically fails cost filtering on most instruments." if is_ewmac_2_8 else None
                if cols[i % len(cols)].checkbox(label, value=default, key=f"rbuild_{family}_{label}", help=help_text):
                    chosen.append(label)
            if chosen:
                selected_families[family] = chosen

    for hint in rule_builder.rule_correlation_hints(set(selected_families)):
        st.warning(hint)

    st.markdown("### Create")
    c1, c2 = st.columns(2)
    new_name = c1.text_input("System name", value=universe_builder.next_system_name(SYSTEMS_ROOT))
    template_choices = [n for n in discovery.list_systems(SYSTEMS_ROOT) if n == "defaults"] or \
        discovery.list_systems(SYSTEMS_ROOT)
    template_system = c2.selectbox("Copy base.yaml from", template_choices or ["defaults"])

    can_create = bool(selected_instruments) and bool(selected_families)
    if st.button("Create universe", type="primary", disabled=not can_create):
        try:
            new_system_dir = universe_builder.build_system(
                SYSTEMS_ROOT, new_name, sorted(selected_instruments),
                catalog=instrument_catalog, template_system=template_system,
            )
            rule_builder.build_rules(new_system_dir, selected_families, catalog=rules_catalog)
        except (FileExistsError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state["system_select"] = new_name
            st.success(
                f"Created systems/{new_name}/ with {len(selected_instruments)} instruments "
                f"and {len(selected_families)} rule families."
            )
            st.rerun()

st.divider()

# --- pick a system -----------------------------------------------------------

system_names = discovery.list_systems(SYSTEMS_ROOT)
if not system_names:
    st.info(f"No systems found under `{SYSTEMS_ROOT}`. Create one with `systems/<name>/config/`.")
    st.stop()

system_name = st.selectbox("System", system_names, key="system_select")
system_dir = SYSTEMS_ROOT / system_name

# --- Step 3/4/5 config editors (edit weights/vol_target without leaving the browser) ---

def _forecast_weights_editor(system_dir: Path, system_name: str) -> None:
    """Step 3: edit config/step3.yaml's forecast_weights in place of a hand edit."""
    weights = config_editor.read_forecast_weights(system_dir)
    if weights is None:
        return
    families = config_editor.forecast_weight_families(weights)
    with st.expander("Edit forecast weights", expanded=False):
        st.caption(
            "Family budgets split equally across variants by default (CLAUDE.md's Step 3 "
            "handcrafting algorithm) — switch to per-rule to override individual variants."
        )
        mode = st.radio(
            "Mode", ["By family (equal split within family)", "Per rule (advanced)"],
            key=f"fw_mode_{system_name}", horizontal=True,
        )
        if mode.startswith("By family"):
            family_budgets: dict[str, float] = {}
            cols = st.columns(min(len(families), 4) or 1)
            for i, (family, names) in enumerate(families.items()):
                default = round(sum(weights[n] for n in names), 4)
                family_budgets[family] = cols[i % len(cols)].number_input(
                    f"{family} ({len(names)})", min_value=0.0, max_value=1.0,
                    value=default, step=0.01, key=f"fw_fam_{system_name}_{family}",
                )
            final_weights = config_editor.split_family_budgets_equally(weights, family_budgets)
        else:
            final_weights = {}
            for family, names in families.items():
                st.markdown(f"**{family}**")
                cols = st.columns(min(len(names), 4) or 1)
                for i, name in enumerate(names):
                    final_weights[name] = cols[i % len(cols)].number_input(
                        name, min_value=0.0, max_value=1.0, value=weights[name],
                        step=0.001, format="%.4f", key=f"fw_rule_{system_name}_{name}",
                    )
        total = sum(final_weights.values())
        st.caption(f"Total: {total:.4f}  (must be 1.0 ± {config_editor.SUM_TOL})")
        if st.button("Save forecast weights", key=f"fw_save_{system_name}"):
            try:
                config_editor.write_forecast_weights(system_dir, final_weights)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("Saved step3.yaml → forecast_weights. Click Run above to recompute FDM.")
                st.rerun()


def _instrument_weights_editor(system_dir: Path, system_name: str) -> None:
    """Step 4: edit config/step4.yaml's group_weights / instrument_weights in place of a hand edit."""
    group_weights = config_editor.read_group_weights(system_dir)
    if group_weights is None:
        return
    groups = config_editor.instrument_groups(system_dir)
    instrument_weights = config_editor.read_instrument_weights(system_dir) or {}

    with st.expander("Edit group / instrument weights", expanded=False):
        st.caption(
            "Group budgets split equally across instruments by default (CLAUDE.md's Step 4 "
            "handcrafting algorithm) — switch to per-instrument to override uneven splits "
            "backed by correlation data."
        )
        mode = st.radio(
            "Mode", ["By group (equal split within group)", "Per instrument (advanced)"],
            key=f"iw_mode_{system_name}", horizontal=True,
        )
        if mode.startswith("By group"):
            final_group_weights: dict[str, float] = {}
            cols = st.columns(min(len(groups), 4) or 1)
            for i, (group, codes) in enumerate(groups.items()):
                default = round(group_weights.get(group, 0.0), 4)
                final_group_weights[group] = cols[i % len(cols)].number_input(
                    f"{group} ({len(codes)})", min_value=0.0, max_value=1.0,
                    value=default, step=0.01, key=f"iw_grp_{system_name}_{group}",
                )
            total = sum(final_group_weights.values())
            st.caption(f"Total: {total:.4f}  (must be 1.0 ± {config_editor.SUM_TOL})")
            c1, c2 = st.columns(2)
            if c1.button("Save group weights", key=f"iw_save_grp_{system_name}"):
                try:
                    config_editor.write_group_weights(system_dir, final_group_weights)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        "Saved step4.yaml → group_weights. Click Run above to re-derive "
                        "instrument_weights and IDM."
                    )
                    st.rerun()
            if c2.button("Reset instrument split to equal", key=f"iw_reset_{system_name}"):
                config_editor.reset_instrument_weights(system_dir)
                st.success(
                    "Cleared the instrument_weights override — Run will re-derive an equal "
                    "split within each group."
                )
                st.rerun()
        else:
            final_instrument_weights = {}
            for group, codes in groups.items():
                st.markdown(f"**{group}**")
                cols = st.columns(min(len(codes), 4) or 1)
                for i, code in enumerate(codes):
                    default = instrument_weights.get(code, 0.0)
                    final_instrument_weights[code] = cols[i % len(cols)].number_input(
                        code, min_value=0.0, max_value=1.0, value=default,
                        step=0.001, format="%.4f", key=f"iw_inst_{system_name}_{code}",
                    )
            total = sum(final_instrument_weights.values())
            st.caption(f"Total: {total:.4f}  (must be 1.0 ± {config_editor.SUM_TOL})")
            if st.button("Save instrument weights", key=f"iw_save_inst_{system_name}"):
                try:
                    config_editor.write_instrument_weights(system_dir, final_instrument_weights)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success("Saved step4.yaml → instrument_weights. Click Run above to recompute IDM.")
                    st.rerun()


def _step5_panel(system_dir: Path, system_name: str, step: dict) -> None:
    """Step 5: pick a vol target (default 20%), run the real IS backtest at it, and
    show the per-instrument table exactly as step5_calibrate.py prints it to the log,
    big-font portfolio metrics, and the equity curve underneath.

    SR is only approximately scale-invariant across vol targets — lot rounding and
    inertia buffering (src/backtest/sizing.py) are nonlinear — so Run always
    re-executes the backtest at the chosen target rather than rescaling a placeholder.
    """
    preview_key = f"vt_preview_result_{system_name}"
    outcome_key = f"outcome_5_{system_name}"

    current = config_editor.read_vol_target(system_dir)
    default_vt = float(current) if current is not None else 0.20

    badge = "✅" if step["done"] else "⬜"
    user_tag = "  *(auto-confirms current config on disk)*" if step["requires_user"] else ""
    st.markdown(f"{badge} **{step['description']}**{user_tag}")

    ready = config_editor.can_preview_backtest(system_dir)
    vt_col, run_col = st.columns([4, 1])
    vol_target = vt_col.slider(
        "Vol target", min_value=config_editor.VOL_TARGET_MIN, max_value=config_editor.VOL_TARGET_MAX,
        value=default_vt, step=0.01, key=f"vt_run_{system_name}",
    )
    vt_col.markdown(f"##### Vol target = {vol_target:.0%}")
    run_col.markdown("&nbsp;")
    if run_col.button("Run", key="run_5", disabled=not ready):
        with st.spinner(f"Running IS backtest at {vol_target:.0%}..."):
            config_editor.write_vol_target(system_dir, vol_target)
            outcome = run_step(system_dir, "5")
            preview = config_editor.preview_vol_target(system_dir, vol_target) if outcome.ok else None
        st.session_state[outcome_key] = outcome
        st.session_state[preview_key] = preview
        st.rerun()
    if not ready:
        st.caption("Run Steps 3 and 4 first — forecast weights/FDM and instrument weights/IDM are needed.")

    outcome = st.session_state.get(outcome_key)
    if outcome is not None and not outcome.ok:
        st.error(f"Step 5 failed: {outcome.error}")
    if outcome is not None:
        with st.expander("Full log", expanded=not outcome.ok):
            st.code(outcome.stdout or "(no output)")

    preview = st.session_state.get(preview_key)
    if preview is None:
        return

    st.markdown("##### Per-instrument IS breakdown")
    st.dataframe(
        [
            {
                "Code": r["code"],
                "SR": f"{r['sharpe']:.2f}",
                "Ret": f"{r['ann_return']:.1%}",
                "MaxDD": f"{r['max_drawdown']:.1%}",
                "TV": f"{r['turnover']:.1f}",
                "Wt": f"{r['weight']:.1%}",
                "FDM": f"{r['fdm']:.3f}",
            }
            for r in preview["instruments"]
        ],
        hide_index=True,
        use_container_width=True,
    )

    m = st.columns(4)
    m[0].metric("IS Sharpe", f"{preview['is_sharpe']:.2f}")
    m[1].metric("Ann Return", f"{preview['ann_return']:.1%}")
    m[2].metric("Max DD", f"{preview['max_drawdown']:.1%}")
    m[3].metric("Vol target", f"{preview['vol_target']:.0%}")
    st.caption(
        f"Realistic SR (×0.75) {preview['realistic_sr']:.2f} | Half Kelly "
        f"{preview['half_kelly']:.1%} | Full Kelly {preview['full_kelly']:.1%} "
        f"| Geo mean {preview['geo_mean']:.1%} | Suggested {preview['suggested']:.1%}"
    )

    st.markdown("##### Equity curve")
    st.line_chart(preview["equity_curve"], height=260)


def _oos_table(rows: dict, id_col: str, extra_cols: dict[str, str] | None = None) -> list[dict]:
    """Flatten an OOS {name: {is:{sr,ret}, test:{...}, ...}} map into
    row dicts for st.dataframe, formatted like oos_validation.py's printed tables.
    """
    out = []
    for name, row in rows.items():
        entry = {id_col: name}
        if extra_cols:
            for label, key in extra_cols.items():
                entry[label] = row.get(key)
        entry.update({
            "IS SR": f"{row['is']['sr']:.2f}", "Test SR": f"{row['test']['sr']:.2f}",
            "IS Ret": f"{row['is']['ret']:.1%}", "Test Ret": f"{row['test']['ret']:.1%}",
        })
        out.append(entry)
    return out


def _step6_panel(system_dir: Path, system_name: str, step: dict) -> None:
    """OOS validation ('Step 6'): pick a vol target (default 20%), re-run the
    IS/Test backtest at it, and show the same per-instrument / asset-class /
    rule / rule-family tables oos_validation.py prints to the log, big-font
    portfolio metrics (matching the Results tab below), and the combined
    IS->Test equity curve underneath.

    Re-running at different vol targets doesn't look at OOS performance to prune
    anything — CLAUDE.md treats vol_target as a risk tool, not a performance lever
    (Step 5 rule 4) — but any *other* adjustment made after seeing these numbers
    still requires a new build (CLAUDE.md's IS/OOS discipline rule 5).
    """
    preview_key = f"oos_preview_result_{system_name}"
    outcome_key = f"outcome_oos_{system_name}"

    badge = "✅" if step["done"] else "⬜"
    st.markdown(f"{badge} **{step['description']}**")

    ready = config_editor.can_preview_backtest(system_dir)
    vt_col, run_col = st.columns([4, 1])
    vol_target = vt_col.slider(
        "Vol target", min_value=config_editor.VOL_TARGET_MIN, max_value=config_editor.VOL_TARGET_MAX,
        value=0.20, step=0.01, key=f"vt6_run_{system_name}",
    )
    vt_col.markdown(f"##### Vol target = {vol_target:.0%}")
    run_col.markdown("&nbsp;")
    if run_col.button("Run", key="run_oos", disabled=not ready):
        with st.spinner(f"Running OOS validation at {vol_target:.0%}..."):
            outcome = run_step(system_dir, "oos", extra_kwargs={"vol_target": vol_target})
            preview = config_editor.preview_oos(system_dir, vol_target) if outcome.ok else None
        st.session_state[outcome_key] = outcome
        st.session_state[preview_key] = preview
        st.rerun()
    if not ready:
        st.caption("Run Steps 3 and 4 first — forecast weights/FDM and instrument weights/IDM are needed.")

    outcome = st.session_state.get(outcome_key)
    if outcome is not None and not outcome.ok:
        st.error(f"OOS validation failed: {outcome.error}")
    if outcome is not None:
        with st.expander("Full log", expanded=not outcome.ok):
            st.code(outcome.stdout or "(no output)")

    preview = st.session_state.get(preview_key)
    if preview is None:
        return

    st.markdown("##### Per-instrument SR")
    st.dataframe(
        _oos_table(preview["instruments"], "Code"),
        hide_index=True, use_container_width=True,
    )
    st.markdown("##### Asset class SR")
    st.dataframe(
        _oos_table(preview["asset_classes"], "Class"),
        hide_index=True, use_container_width=True,
    )
    st.markdown("##### Rule SR")
    st.dataframe(
        _oos_table(preview["rules"], "Rule"),
        hide_index=True, use_container_width=True,
    )
    st.markdown("##### Rule family SR")
    st.dataframe(
        _oos_table(preview["families"], "Family", extra_cols={"Rules": "n_rules"}),
        hide_index=True, use_container_width=True,
    )

    pr = preview["portfolio"]
    st.markdown("##### Portfolio")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**In-Sample**")
        st.metric("SR", f"{pr['is']['sr']:.2f}")
        st.metric("Return", f"{pr['is']['ret']:.1%}")
        st.metric("Max DD", f"{pr['is']['max_dd']:.1%}")
    with c2:
        st.markdown("**Test**")
        st.metric("SR", f"{pr['test']['sr']:.2f}")
        st.metric("Return", f"{pr['test']['ret']:.1%}")
        st.metric("Max DD", f"{pr['test']['max_dd']:.1%}")

    if preview["test_weak"]:
        st.warning(f"Test SR < -0.30 for: {', '.join(preview['test_weak'])} — candidates for next build's Step 1 review.")

    st.markdown("##### Equity curve (IS → Test)")
    st.line_chart(preview["equity_curve"], height=260)


# --- pipeline status + run controls ------------------------------------------

st.subheader("Pipeline")
statuses = discovery.step_status(system_dir)
run_log = results.read_run_log(system_dir)
log_steps = (run_log or {}).get("steps", {})

for step in statuses:
    if step["number"] == "5":
        _step5_panel(system_dir, system_name, step)
        continue
    if step["number"] == "oos":
        _step6_panel(system_dir, system_name, step)
        continue

    cols = st.columns([5, 1, 1])
    badge = "✅" if step["done"] else "⬜"
    user_tag = "  *(auto-confirms current config on disk)*" if step["requires_user"] else ""
    cols[0].markdown(f"{badge} **{step['description']}**{user_tag}")

    demo = False
    if step["number"] == "0":
        demo = cols[1].checkbox("demo", key="demo_fetch", label_visibility="collapsed", help="Use demo account for data fetching")

    if cols[2].button("Run", key=f"run_{step['number']}"):
        with st.spinner(f"Running step {step['number']}..."):
            outcome = run_step(system_dir, step["number"], demo=demo)
        st.session_state[f"outcome_{step['number']}"] = outcome
        st.rerun()  # refresh run_log/step status immediately instead of on the next natural rerun

    outcome = st.session_state.get(f"outcome_{step['number']}")
    if outcome is not None and not outcome.ok:
        st.error(f"Step {step['number']} failed: {outcome.error}")
    else:
        step_values = log_steps.get(step["number"], {})
        formatter = _STEP_FORMATTERS.get(step["number"])
        summary = formatter(step_values) if formatter else None
        if summary:
            lines = summary if isinstance(summary, list) else [summary]
            for line in lines:
                st.markdown(f"##### {line}")

    if outcome is not None:
        with st.expander("Full log", expanded=not outcome.ok):
            st.code(outcome.stdout or "(no output)")

    if step["number"] == "3":
        _forecast_weights_editor(system_dir, system_name)
    elif step["number"] == "4":
        _instrument_weights_editor(system_dir, system_name)

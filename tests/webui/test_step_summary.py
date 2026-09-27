from __future__ import annotations


def test_format_step0_all_up_to_date():
    from src.webui.step_summary import format_step0
    assert format_step0({"up_to_date": 3, "needs_update": 0, "missing": 0}) == "All 3 instruments up to date."


def test_format_step0_mixed():
    from src.webui.step_summary import format_step0
    text = format_step0({"up_to_date": 1, "needs_update": 2, "missing": 1})
    assert text == "1 up to date, 2 updated, 1 fetched."


def test_format_step0_none_when_no_values():
    from src.webui.step_summary import format_step0
    assert format_step0({}) is None


def test_format_step1_breaks_down_by_asset_class_as_separate_lines():
    from src.webui.step_summary import format_step1
    lines = format_step1({
        "n_traded": 4,
        "instruments": ["US500", "GER40", "US10YR", "BUND"],
        "asset_groups": {"index": ["US500", "GER40"], "bond": ["US10YR", "BUND"]},
    })
    assert lines == [
        "Confirmed 4 instruments across 2 asset classes:",
        "Index: US500, GER40",
        "Bond: US10YR, BUND",
    ]


def test_format_step1_shows_every_instrument_no_truncation():
    from src.webui.step_summary import format_step1
    instruments = [f"I{i}" for i in range(12)]
    lines = format_step1({"n_traded": 12, "instruments": instruments, "asset_groups": {"commodity": instruments}})
    assert lines == [
        "Confirmed 12 instruments across 1 asset classes:",
        "Commodity: " + ", ".join(instruments),
    ]


def test_format_step1_falls_back_without_asset_groups():
    """Older run_log entries (written before asset_groups existed) still render."""
    from src.webui.step_summary import format_step1
    lines = format_step1({"n_traded": 2, "instruments": ["US500", "BUND"]})
    assert lines == ["Confirmed 2 instruments: US500, BUND"]


def test_format_step2_breaks_down_by_family_and_variant_as_separate_lines():
    from src.webui.step_summary import format_step2
    lines = format_step2({
        "n_families": 2, "n_variants": 6,
        "families": ["ewmac", "seasonality"],
        "family_variants": {"ewmac": ["16_64", "32_128"], "seasonality": []},
    })
    assert lines == [
        "Confirmed 2 rule families, 6 variants:",
        "Ewmac: 16_64, 32_128",
        "Seasonality",
    ]


def test_format_step2_falls_back_without_family_variants():
    """Older run_log entries (written before family_variants existed) still render."""
    from src.webui.step_summary import format_step2
    lines = format_step2({"n_families": 2, "n_variants": 6, "families": ["ewmac", "seasonality"]})
    assert lines == ["Confirmed 2 families / 6 variants: ewmac, seasonality"]


def test_format_step2_falls_back_without_families_key_either():
    from src.webui.step_summary import format_step2
    lines = format_step2({"n_families": 2, "n_variants": 6})
    assert lines == ["Confirmed 2 families / 6 variants"]


def test_format_step3_summarizes_weights_and_fdm_range():
    from src.webui.step_summary import format_step3
    text = format_step3({
        "forecast_weights": {"EWMAC_4_16": 0.5, "EWMAC_8_32": 0.5},
        "fdm": {"US500": 1.1, "BUND": 1.45},
    })
    assert text == "Forecast weights: EWMAC_4_16=0.50, EWMAC_8_32=0.50 | FDM 1.10–1.45 (avg 1.27)"


def test_format_step3_none_when_no_fdm():
    from src.webui.step_summary import format_step3
    assert format_step3({"state": "x", "report": "y"}) is None


def test_format_step4_summarizes_groups_and_idm():
    from src.webui.step_summary import format_step4
    text = format_step4({
        "group_weights": {"index": 0.22, "bond": 0.18, "commodity": 0.60},
        "idm": 1.39,
    })
    assert text == "Groups: index 22%, bond 18%, commodity 60% | IDM 1.39"


def test_format_step5_summarizes_kelly_and_vol_target():
    from src.webui.step_summary import format_step5
    text = format_step5({
        "is_sharpe": 0.68, "realistic_sr": 0.51, "half_kelly": 0.25,
        "full_kelly": 0.51, "geo_mean": 0.36, "vol_target": 0.20,
    })
    assert text == "IS Sharpe 0.68 | Realistic SR 0.51 | Vol target 20%"


def test_format_step5_none_when_empty():
    from src.webui.step_summary import format_step5
    assert format_step5({}) is None


def test_format_oos_summarizes_sr_and_weak_flags():
    from src.webui.step_summary import format_oos
    text = format_oos({
        "is_sr": 0.68, "test_sr": 0.15,
        "test_weak_flags": ["GER40", "JPN225"],
    })
    assert text == "SR — IS 0.68 / Test 0.15 | 2 weak: GER40, JPN225"


def test_format_oos_no_weak_flags_suffix_when_none():
    from src.webui.step_summary import format_oos
    text = format_oos({"is_sr": 0.68, "test_sr": 0.15, "test_weak_flags": []})
    assert text == "SR — IS 0.68 / Test 0.15"


def test_format_oos_none_when_empty():
    from src.webui.step_summary import format_oos
    assert format_oos({}) is None

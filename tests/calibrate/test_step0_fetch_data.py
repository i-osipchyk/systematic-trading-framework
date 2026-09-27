from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from src.calibration import state as st


def test_main_returns_summary_when_all_data_up_to_date(config_dir: Path, monkeypatch):
    import calibrate.step0_fetch_data as step0

    today = date.today()
    monkeypatch.setattr(step0, "_data_status", lambda code: (date(2000, 1, 1), today))

    def _fail_if_fetching(*a, **kw):
        raise AssertionError("should not fetch when everything is up to date")
    monkeypatch.setattr(step0, "_run_fetch", _fail_if_fetching)

    result = step0.main(state_dir=config_dir)

    # config_dir fixture declares US500, BUND, EURUSD (EURUSD as a non-traded FX helper)
    assert result == {"up_to_date": 3, "needs_update": 0, "missing": 0}


def test_main_returns_summary_with_missing_and_stale_counts(config_dir: Path, monkeypatch):
    import calibrate.step0_fetch_data as step0

    today = date.today()
    stale = today - timedelta(days=step0.STALENESS_DAYS + 10)

    def _fake_status(code):
        if code == "US500":
            return None, None  # missing
        return date(2000, 1, 1), stale  # needs update

    monkeypatch.setattr(step0, "_data_status", _fake_status)
    monkeypatch.setattr(step0, "_run_fetch", lambda *a, **kw: None)

    result = step0.main(state_dir=config_dir)

    # US500 missing; BUND and EURUSD both stale ("needs update")
    assert result == {"up_to_date": 0, "needs_update": 2, "missing": 1}

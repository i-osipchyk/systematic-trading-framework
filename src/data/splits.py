"""
In-sample / out-of-sample split utilities.

Strategy: single global split date computed from calendar time across all
instruments. This ensures the OOS window is the same for every instrument,
making portfolio-level OOS validation consistent.

Split date = common_start + train_frac * (common_end - common_start)
where common_start = latest first bar across instruments
      common_end   = earliest last bar across instruments

Default train_frac = 0.70  (70% IS, 30% OOS)
"""

from datetime import datetime

import pandas as pd

from src.data.pst_writer import adjusted_prices_dir, load_adjusted_prices

TRAIN_FRAC = 0.70


def compute_split_date(
    instrument_codes: list[str] | None = None,
    train_frac: float = TRAIN_FRAC,
) -> datetime:
    """Compute the global IS/OOS split date.

    If the active config specifies a split_date, that value is returned
    directly. Otherwise, the split is computed as a calendar-time fraction of
    the common data window across all instruments, subject to two optional
    config overrides:
      - start_date: floor for common_start (excludes low-quality early data)
      - test_size:  overrides the default 0.30 OOS fraction

    Returns the first date that belongs to the OOS period.
    """
    from src.backtest.config import load_split_date, load_start_date, load_test_size
    explicit = load_split_date()
    if explicit is not None:
        return explicit

    if instrument_codes is None:
        # Use only the instruments that are traded in the active config.
        # Scanning the whole data directory can include instruments with much
        # shorter histories (e.g. BTC, ETH) that shift common_start forward
        # and produce a meaninglessly late split date.
        try:
            from src.backtest.config import load_instrument_configs, traded_instruments
            instrument_codes = traded_instruments(load_instrument_configs())
        except Exception:
            instrument_codes = [p.stem for p in adjusted_prices_dir().glob("*.csv")]

    starts, ends = [], []
    for code in instrument_codes:
        s = load_adjusted_prices(code)
        starts.append(s.index.min())
        ends.append(s.index.max())

    common_start = max(starts)
    common_end = min(ends)

    # Clamp IS start to start_date if configured (removes low-quality early data)
    config_start = load_start_date()
    if config_start is not None and config_start > common_start:
        common_start = config_start

    # Use test_size from config when caller did not override train_frac
    if train_frac == TRAIN_FRAC:
        test_size = load_test_size()
        if test_size is not None:
            train_frac = 1.0 - test_size

    total_span = common_end - common_start
    split_date = common_start + train_frac * total_span
    return split_date


def split_series(
    series: pd.Series,
    split_date: datetime,
) -> tuple[pd.Series, pd.Series]:
    """Split a price series into IS and OOS at split_date."""
    is_data = series[series.index < split_date]
    oos_data = series[series.index >= split_date]
    return is_data, oos_data


def print_split_summary(
    instrument_codes: list[str] | None = None,
    train_frac: float = TRAIN_FRAC,
) -> None:
    """Print IS/OOS bar counts for every instrument."""
    if instrument_codes is None:
        instrument_codes = sorted(
            p.stem for p in adjusted_prices_dir().glob("*.csv")
        )

    split_date = compute_split_date(instrument_codes, train_frac)
    print(f"Split date: {split_date.date()}  ({int(train_frac*100)}% IS / {int((1-train_frac)*100)}% OOS)\n")
    print(f"{'Instrument':<12} {'IS bars':>8} {'OOS bars':>9} {'IS start':>12} {'IS end':>12} {'OOS end':>12}")
    print("-" * 72)

    for code in instrument_codes:
        s = load_adjusted_prices(code)
        is_data, oos_data = split_series(s, split_date)
        print(
            f"{code:<12} {len(is_data):>8} {len(oos_data):>9} "
            f"{is_data.index.min().date()!s:>12} "
            f"{is_data.index.max().date()!s:>12} "
            f"{oos_data.index.max().date()!s:>12}"
        )

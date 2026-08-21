"""
Data pipeline orchestrator.

Connects to cTrader, fetches historical bars for all configured instruments,
and writes them to the pysystemtrade CSV data directory.

Usage (from pipeline.py directly or via scripts/fetch_history.py):
    from src.data.pipeline import run_pipeline
    run_pipeline(from_date=datetime(2018, 1, 1), to_date=datetime.utcnow(), period="D1")
"""

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from twisted.internet import defer, reactor

from src.backtest.config import load_instrument_configs
from src.data.ctrader_client import CTraderClient
from src.data.pst_writer import write_adjusted_prices, write_multiple_prices

load_dotenv()


def _load_config() -> dict:
    """Return {code: cfg_dict} for all instruments using the active config."""
    cfgs = load_instrument_configs()
    return {code: {"ctrader_symbol": cfg.ctrader_symbol} for code, cfg in cfgs.items()}


def _client_from_env(live: bool) -> CTraderClient:
    return CTraderClient(
        client_id=os.environ["CTRADER_CLIENT_ID"],
        client_secret=os.environ["CTRADER_CLIENT_SECRET"],
        access_token=os.environ["CTRADER_ACCESS_TOKEN"],
        account_id=int(os.environ["CTRADER_ACCOUNT_ID"]),
        live=live,
    )


@defer.inlineCallbacks
def _fetch_and_write(client: CTraderClient, instruments: dict, period: str, from_dt: datetime, to_dt: datetime):
    print("Authenticating...")
    yield client.authenticate()

    print("Loading symbol list...")
    symbol_map = yield client.load_symbols()
    print(f"  {len(symbol_map)} symbols available on this account.")

    for code, cfg in instruments.items():
        ctrader_symbol = cfg["ctrader_symbol"]
        print(f"\nFetching {code} ({ctrader_symbol}) [{period}] "
              f"{from_dt.date()} → {to_dt.date()}")

        try:
            df = yield client.fetch_bars(ctrader_symbol, period, from_dt, to_dt)
        except KeyError as e:
            print(f"  WARNING: {e} — skipping.")
            continue

        if df.empty:
            print(f"  WARNING: no bars returned for {code}.")
            continue

        adj_path = write_adjusted_prices(df, code)
        mul_path = write_multiple_prices(df, code)
        print(f"  {len(df)} bars → {adj_path.name}, {mul_path.name}")

    print("\nAll instruments fetched.")
    reactor.stop()


def _on_error(failure):
    print(f"ERROR: {failure.getErrorMessage()}")
    reactor.stop()


def run_pipeline(
    from_date: datetime,
    to_date: datetime,
    period: str = "D1",
    live: bool | None = None,
    instruments: list[str] | None = None,
):
    """Fetch historical data for instruments and write to CSV.

    Args:
        from_date:   Start date (UTC).
        to_date:     End date (UTC).
        period:      Bar period — one of D1, H1, H4, M1.
        live:        True = live endpoint, False = demo.
                     Defaults to CTRADER_ENV env var ('live' / 'demo').
        instruments: Subset of instrument codes to fetch. None = all.
    """
    if live is None:
        live = os.getenv("CTRADER_ENV", "live").lower() == "live"

    all_instruments = _load_config()
    if instruments:
        missing = set(instruments) - set(all_instruments)
        if missing:
            raise ValueError(f"Unknown instrument codes: {missing}")
        all_instruments = {k: v for k, v in all_instruments.items() if k in instruments}
    instruments = all_instruments
    client = _client_from_env(live)

    def on_connected(_):
        d = _fetch_and_write(client, instruments, period, from_date, to_date)
        d.addErrback(_on_error)

    client.start(on_connected)
    reactor.run()

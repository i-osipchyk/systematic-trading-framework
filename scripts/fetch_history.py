#!/usr/bin/env python3
"""
Fetch historical OHLCV data from cTrader and write to pysystemtrade CSV format.

Examples:
    # Daily bars from 2018 to today
    python scripts/fetch_history.py --from 2018-01-01 --period D1

    # Hourly bars for a recent window (demo account)
    python scripts/fetch_history.py --from 2023-01-01 --to 2024-01-01 --period H1 --demo
"""

import argparse
from datetime import datetime, timezone

from src.backtest.config import set_config
from src.data.pipeline import run_pipeline


def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description="Fetch historical data from cTrader")
    parser.add_argument("--from", dest="from_date", required=True, metavar="YYYY-MM-DD",
                        help="Start date (UTC)")
    parser.add_argument("--to", dest="to_date", default=None, metavar="YYYY-MM-DD",
                        help="End date (UTC). Defaults to today.")
    parser.add_argument("--period", default="D1", choices=["D1", "H1", "H4", "M1"],
                        help="Bar period (default: D1)")
    parser.add_argument("--demo", action="store_true",
                        help="Use demo account endpoint instead of live")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="Config file to use for instrument/symbol lookup "
                             "(default: config/universe_v3.yaml)")
    parser.add_argument("--instruments", nargs="+", metavar="CODE",
                        help="Only fetch these instrument codes (default: all in config)")
    args = parser.parse_args()

    if args.config:
        set_config(args.config)

    from_dt = parse_date(args.from_date)
    to_dt = parse_date(args.to_date) if args.to_date else datetime.now(timezone.utc)

    print(f"Fetching {args.period} bars: {from_dt.date()} → {to_dt.date()}")
    print(f"Endpoint: {'demo' if args.demo else 'live'}\n")

    run_pipeline(
        from_date=from_dt,
        to_date=to_dt,
        period=args.period,
        live=not args.demo,
        instruments=args.instruments,
    )


if __name__ == "__main__":
    main()

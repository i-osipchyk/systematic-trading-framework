#!/usr/bin/env python3
"""
Probe cTrader for candidate instruments for the expanded universe.

For each candidate, discovers the exact symbol name on the account then
fetches D1 data from 2011-01-01 to report how far back history goes.

Usage:
    uv run python scripts/probe_new_instruments.py
    uv run python scripts/probe_new_instruments.py --demo
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from dotenv import load_dotenv
from twisted.internet import defer, reactor, task

from src.data.ctrader_client import CTraderClient, HISTORICAL_RATE_LIMIT_DELAY

load_dotenv()

# Candidates: (our_code, [possible cTrader names in order of likelihood])
CANDIDATES = [
    ("GBPUSD",  ["GBPUSD"]),
    ("AUDUSD",  ["AUDUSD"]),
    ("NAS100",  ["NAS100", "NASDAQ", "NDX100", "US100"]),
    ("UK100",   ["UK100", "FTSE100", "FTSE"]),
    ("HK50",    ["HK50", "HKG50", "HSI", "HKHI"]),
    ("COPPER",  ["COPPER", "XCUUSD", "COPPERUSD"]),
    ("NATGAS",  ["NATGAS", "XNGUSD", "NATURALGAS"]),
    ("JPN225",  ["JPN225", "JP225", "JPN225.r", "NIKKEI225"]),
    ("USDX",    ["USDX", "USDIDX", "DXY", "USDOLLAR"]),
]

FULL_FROM = datetime(2011, 1, 1, tzinfo=timezone.utc)
FULL_TO   = datetime(2026, 8, 21, tzinfo=timezone.utc)


@defer.inlineCallbacks
def run(_):
    yield client.authenticate()
    symbol_map = yield client.load_symbols()
    print(f"  {len(symbol_map)} symbols on account.\n")

    print(f"  {'Code':<10} {'cTrader symbol':<18} {'First bar':>12} {'Last bar':>12} {'Bars':>6}")
    print(f"  {'─'*62}")

    for code, candidates in CANDIDATES:
        matched = next((c for c in candidates if c in symbol_map), None)

        if matched is None:
            fuzzy = sorted(s for s in symbol_map if any(
                t.lower() in s.lower() for t in [code] + candidates
            ))[:6]
            hint = f"  (similar: {fuzzy})" if fuzzy else ""
            print(f"  {code:<10} {'NOT FOUND':<18} {'—':>12} {'—':>12} {'—':>6}{hint}")
            continue

        try:
            df = yield client.fetch_bars(matched, "D1", FULL_FROM, FULL_TO)
        except Exception as e:
            print(f"  {code:<10} {matched:<18} ERROR: {e}")
            yield task.deferLater(reactor, HISTORICAL_RATE_LIMIT_DELAY, lambda: None)
            continue

        yield task.deferLater(reactor, HISTORICAL_RATE_LIMIT_DELAY, lambda: None)

        if df.empty:
            print(f"  {code:<10} {matched:<18} {'no data':>12} {'—':>12} {'0':>6}")
        else:
            first = df["DATETIME"].iloc[0].strftime("%Y-%m-%d")
            last  = df["DATETIME"].iloc[-1].strftime("%Y-%m-%d")
            print(f"  {code:<10} {matched:<18} {first:>12} {last:>12} {len(df):>6}")

    reactor.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    for var in ("CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET",
                "CTRADER_ACCESS_TOKEN", "CTRADER_ACCOUNT_ID"):
        if not os.environ.get(var):
            sys.exit(f"ERROR: {var} not set in .env")

    client = CTraderClient(
        client_id=os.environ["CTRADER_CLIENT_ID"],
        client_secret=os.environ["CTRADER_CLIENT_SECRET"],
        access_token=os.environ["CTRADER_ACCESS_TOKEN"],
        account_id=int(os.environ["CTRADER_ACCOUNT_ID"]),
        live=not args.demo,
    )
    client.start(run)
    reactor.run()

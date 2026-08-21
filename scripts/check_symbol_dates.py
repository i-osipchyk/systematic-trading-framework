#!/usr/bin/env python3
"""Check the date range available for given symbols on demo."""
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from twisted.internet import defer, reactor
from src.data.ctrader_client import CTraderClient

load_dotenv()
symbols = sys.argv[1:] or ["SpotCrude", "WTOIL-PERP", "XTIUSD"]

client = CTraderClient(
    client_id=os.environ["CTRADER_CLIENT_ID"],
    client_secret=os.environ["CTRADER_CLIENT_SECRET"],
    access_token=os.environ["CTRADER_ACCESS_TOKEN"],
    account_id=int(os.environ["CTRADER_ACCOUNT_ID"]),
    live=False,
)

@defer.inlineCallbacks
def run(_):
    yield client.authenticate()
    yield client.load_symbols()
    for sym in symbols:
        try:
            df = yield client.fetch_bars(
                sym, "D1",
                datetime(2018, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 8, 20, tzinfo=timezone.utc),
            )
            if len(df):
                first = df["DATETIME"].iloc[0].strftime("%Y-%m-%d")
                last = df["DATETIME"].iloc[-1].strftime("%Y-%m-%d")
                print(f"{sym}: {len(df)} bars, {first} → {last}")
            else:
                print(f"{sym}: 0 bars returned")
        except Exception as e:
            print(f"{sym}: ERROR {e}")
    reactor.stop()

client.start(run)
reactor.run()

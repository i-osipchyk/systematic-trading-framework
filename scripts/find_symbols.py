#!/usr/bin/env python3
"""Print cTrader symbols matching given search terms."""
import os
import sys
from dotenv import load_dotenv
from twisted.internet import defer, reactor
from src.data.ctrader_client import CTraderClient

load_dotenv()

terms = sys.argv[1:] or ["oil", "wti", "crude", "usoil", "xti", "jpy", "ngas", "gas"]

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
    symbol_map = yield client.load_symbols()
    print(f"{len(symbol_map)} symbols on account.\n")
    for term in terms:
        matches = [s for s in symbol_map if term.lower() in s.lower()]
        if matches:
            print(f"[{term}]: {matches[:20]}")
        else:
            print(f"[{term}]: (none found)")
    reactor.stop()

client.start(run)
reactor.run()

"""
cTrader Open API client for fetching historical OHLCV bars.

Uses the official ctrader-open-api library (Twisted-based). Authentication
is two-step: app-level auth with client credentials, then account-level auth
with an OAuth2 access token.

Pagination: cTrader returns bars newest-first when hasMore=True. We walk
backward through time by shifting toTimestamp to the oldest bar received
on each page until we cover the full requested range.
"""

from datetime import datetime, timezone

import pandas as pd
from twisted.internet import defer, reactor, task

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
    ProtoOAGetTrendbarsReq,
    ProtoOASymbolsListReq,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOATrendbarPeriod,
)

PRICE_DIVISOR = 100_000
HISTORICAL_RATE_LIMIT_DELAY = 0.25  # 4 req/s, under the 5 req/s limit
MAX_BARS_PER_REQUEST = 5000          # cTrader hard limit per call

PERIOD_MAP = {
    "D1": ProtoOATrendbarPeriod.Value("D1"),
    "H1": ProtoOATrendbarPeriod.Value("H1"),
    "H4": ProtoOATrendbarPeriod.Value("H4"),
    "M1": ProtoOATrendbarPeriod.Value("M1"),
}


def _to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _bar_to_row(bar) -> dict:
    ts = datetime.utcfromtimestamp(bar.utcTimestampInMinutes * 60)
    low = bar.low / PRICE_DIVISOR
    return {
        "DATETIME": ts,
        "OPEN": (bar.low + bar.deltaOpen) / PRICE_DIVISOR,
        "HIGH": (bar.low + bar.deltaHigh) / PRICE_DIVISOR,
        "LOW": low,
        "CLOSE": (bar.low + bar.deltaClose) / PRICE_DIVISOR,
        "VOLUME": bar.volume,
    }


class CTraderClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        account_id: int,
        live: bool = True,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.account_id = account_id

        host = EndPoints.PROTOBUF_LIVE_HOST if live else EndPoints.PROTOBUF_DEMO_HOST
        self._client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self._symbol_map: dict[str, int] = {}

    def _send(self, request):
        """Send a request and return a Deferred resolving to the typed response.

        Raises RuntimeError if the API returns a ProtoOAErrorRes, so callers
        never silently receive an error object instead of a real response.
        """
        d = self._client.send(request)
        d.addCallback(Protobuf.extract)
        d.addCallback(self._raise_on_error)
        return d

    @staticmethod
    def _raise_on_error(response):
        if type(response).__name__ == "ProtoOAErrorRes":
            code = getattr(response, "errorCode", "UNKNOWN")
            desc = getattr(response, "description", "")
            raise RuntimeError(
                f"cTrader API error: {code}"
                + (f" — {desc}" if desc else "")
                + "\n  Common causes: expired access token, wrong account ID, "
                  "or account not authorized for this app."
            )
        return response

    @defer.inlineCallbacks
    def authenticate(self):
        app_req = ProtoOAApplicationAuthReq()
        app_req.clientId = self.client_id
        app_req.clientSecret = self.client_secret
        yield self._send(app_req)

        acct_req = ProtoOAAccountAuthReq()
        acct_req.ctidTraderAccountId = self.account_id
        acct_req.accessToken = self.access_token
        yield self._send(acct_req)

    @defer.inlineCallbacks
    def load_symbols(self):
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self.account_id
        response = yield self._send(req)
        self._symbol_map = {s.symbolName: s.symbolId for s in response.symbol}
        return self._symbol_map

    def symbol_id(self, ctrader_symbol: str) -> int:
        sid = self._symbol_map.get(ctrader_symbol)
        if sid is None:
            available = sorted(self._symbol_map.keys())
            raise KeyError(
                f"Symbol '{ctrader_symbol}' not found. Available: {available}"
            )
        return sid

    @defer.inlineCallbacks
    def fetch_bars(
        self,
        ctrader_symbol: str,
        period: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> pd.DataFrame:
        """Fetch all bars for a symbol between from_dt and to_dt (UTC).

        Paginates backward in time using hasMore until the full range is covered.
        Returns a DataFrame sorted ascending by DATETIME.
        """
        sid = self.symbol_id(ctrader_symbol)
        period_val = PERIOD_MAP[period]
        all_bars: list[dict] = []

        to_ms = _to_ms(to_dt)
        from_ms = _to_ms(from_dt)

        while True:
            req = ProtoOAGetTrendbarsReq()
            req.ctidTraderAccountId = self.account_id
            req.symbolId = sid
            req.period = period_val
            req.fromTimestamp = from_ms
            req.toTimestamp = to_ms

            response = yield self._send(req)
            bars = list(response.trendbar)

            if not bars:
                break

            # Bars arrive oldest-first; prepend so all_bars stays chronological
            rows = [_bar_to_row(b) for b in bars]
            all_bars = rows + all_bars

            if len(bars) < MAX_BARS_PER_REQUEST:
                # Received fewer than a full page — no more data in range
                break

            # Full page returned: walk toTimestamp back to just before the
            # oldest bar on this page to fetch the next (earlier) chunk
            oldest_ms = bars[0].utcTimestampInMinutes * 60 * 1000
            to_ms = oldest_ms - 1

            if to_ms <= from_ms:
                break

            yield task.deferLater(reactor, HISTORICAL_RATE_LIMIT_DELAY, lambda: None)

        if not all_bars:
            return pd.DataFrame(columns=["DATETIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"])

        df = pd.DataFrame(all_bars).sort_values("DATETIME").reset_index(drop=True)
        df["DATETIME"] = pd.to_datetime(df["DATETIME"])
        return df

    def start(self, on_connected):
        self._client.setConnectedCallback(on_connected)
        self._client.startService()

    def stop(self):
        self._client.stopService()

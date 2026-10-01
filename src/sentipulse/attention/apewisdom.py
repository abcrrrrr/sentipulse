"""Reddit (+ 4chan /biz/) mention counts from ApeWisdom's public API.

ApeWisdom aggregates mention counts across stock and crypto boards, which gives
a Reddit attention signal without Reddit API access. It returns counts only (no
post text), so there is no sentiment, and only a rolling-24h snapshot (no
history), so each run stores today's snapshot and history accumulates forward.
Run it at the same time each day so snapshots are comparable.

The API publishes no terms or rate limits; keep usage to one pass a day, and
ask them (see apewisdom.io/api) before any commercial use.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..tickers import Asset
from . import ATTENTION_COLUMNS, USER_AGENT, empty_attention

log = logging.getLogger(__name__)
BASE = "https://apewisdom.io/api/v1.0/filter"
MAX_PAGES = 20  # ~100 tickers per page; a guard against a runaway loop


def _default_get(url, headers, timeout):
    import requests

    return requests.get(url, headers=headers, timeout=timeout)


class ApeWisdom:
    name = "apewisdom"

    def __init__(self, http_get=None):
        self.http_get = http_get
        self._listings: dict[str, dict[str, dict] | None] = {}  # one pass per filter per run

    def _listing(self, filt: str) -> dict[str, dict] | None:
        """All tickers on the board, keyed by ticker; None if any page failed."""
        if filt in self._listings:
            return self._listings[filt]
        get = self.http_get or _default_get
        by_ticker: dict[str, dict] = {}
        page, pages = 1, 1
        while page <= min(pages, MAX_PAGES):
            resp = get(f"{BASE}/{filt}/page/{page}", headers={"User-Agent": USER_AGENT}, timeout=30)
            if resp.status_code != 200:
                log.warning("ApeWisdom %s page %d failed: HTTP %s", filt, page, resp.status_code)
                self._listings[filt] = None
                return None
            data = resp.json()
            pages = int(data.get("pages", 1))
            for row in data.get("results", []):
                # Crypto tickers come suffixed ("BTC.X"); key by the bare symbol.
                ticker = str(row["ticker"]).upper().removesuffix(".X")
                by_ticker.setdefault(ticker, row)
            page += 1
        self._listings[filt] = by_ticker
        return by_ticker

    def fetch(self, asset: Asset, now: datetime | None = None) -> pd.DataFrame:
        filt = "all-crypto" if asset.kind == "crypto" else "all-stocks"
        listing = self._listing(filt)
        if listing is None:
            # Unknown is not zero: record nothing rather than a false quiet day.
            return empty_attention()
        day = (now or datetime.now(timezone.utc)).date()
        row = listing.get(asset.ticker.upper())
        # Not on the full board means effectively no mentions in the last 24h.
        metrics = {"mentions": 0, "upvotes": 0}
        if row:
            metrics = {"mentions": row["mentions"], "upvotes": row["upvotes"], "rank": row["rank"]}
        rows = [
            {"ticker": asset.ticker, "day": day, "source": self.name, "metric": m, "value": v}
            for m, v in metrics.items()
        ]
        return pd.DataFrame(rows, columns=ATTENTION_COLUMNS)

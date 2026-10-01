"""English Wikipedia daily page views via the Wikimedia REST API.

Free, no key, years of history, so it is the one series that can be backfilled.
Wikimedia asks for a descriptive User-Agent with contact info; requests without
one may be blocked. Counts are human traffic only (agent=user), and today is
excluded because its count is still incomplete.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd

from ..tickers import Asset
from . import ATTENTION_COLUMNS, USER_AGENT, empty_attention

log = logging.getLogger(__name__)
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"


def _default_get(url, headers, timeout):
    import requests

    return requests.get(url, headers=headers, timeout=timeout)


def _day(ts: str) -> date:
    """Wikimedia timestamps look like 2026092800 (YYYYMMDDHH)."""
    return date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))


class WikipediaPageviews:
    name = "wikipedia"

    def __init__(self, http_get=None):
        self.http_get = http_get

    def fetch(self, asset: Asset, days: int = 30, today: date | None = None) -> pd.DataFrame:
        if not asset.wiki_title:
            log.info("%s: no wiki_title in registry, skipping Wikipedia", asset.ticker)
            return empty_attention()
        today = today or datetime.now(timezone.utc).date()
        end = today - timedelta(days=1)
        start = end - timedelta(days=max(days, 1) - 1)
        title = quote(asset.wiki_title.replace(" ", "_"), safe="")
        url = f"{BASE}/{title}/daily/{start:%Y%m%d}/{end:%Y%m%d}"

        get = self.http_get or _default_get
        resp = get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.status_code == 404:  # no views recorded in the window
            return empty_attention()
        if resp.status_code != 200:
            log.warning("Wikipedia pageviews failed for %s: HTTP %s", asset.ticker, resp.status_code)
            return empty_attention()

        rows = [
            {
                "ticker": asset.ticker,
                "day": _day(item["timestamp"]),
                "source": self.name,
                "metric": "views",
                "value": item["views"],
            }
            for item in resp.json().get("items", [])
        ]
        return pd.DataFrame(rows, columns=ATTENTION_COLUMNS)

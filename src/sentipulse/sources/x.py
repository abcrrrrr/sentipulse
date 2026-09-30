"""X (Twitter) collector — OPTIONAL, pay-per-use.

As of 2026 the X API has no free read tier: reads are billed per post
(roughly $0.005 each on pay-per-use, capped at 2M/month; no streaming or
full-archive search). This collector enforces a daily read budget so a
runaway loop can't run up a bill.

Enable by setting X_BEARER_TOKEN. Uses the v2 recent-search endpoint
(7-day window) via plain HTTP to avoid a heavy client dependency.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..models import Post
from ..store import Store
from ..tickers import Asset
from .base import BaseSource

log = logging.getLogger(__name__)
RECENT_SEARCH = "https://api.x.com/2/tweets/search/recent"


class XSource(BaseSource):
    name = "x"

    def __init__(
        self,
        ledger: Store,
        daily_budget: int | None = None,
        bearer_token: str | None = None,
        http_get=None,
    ):
        """`ledger` persists reads per UTC day, so the budget holds across runs."""
        self.token = bearer_token or settings.x_bearer_token
        if not self.token:
            raise RuntimeError("X_BEARER_TOKEN not set; X source disabled")
        self.ledger = ledger
        self.budget = daily_budget or settings.x_daily_read_budget
        self.http_get = http_get

    def _query(self, asset: Asset) -> str:
        terms = [f"${asset.ticker}"] + [f'"{n}"' for n in asset.names]
        return f"({' OR '.join(terms)}) -is:retweet lang:en"

    def fetch(self, asset: Asset, days: int = 1, limit: int = 100) -> Iterator[Post]:
        if self.http_get is None:
            import requests

            self.http_get = requests.get

        remaining = min(limit, self.budget - self.ledger.x_reads_today())
        # The API's minimum page is 10 reads; don't start a request the budget can't cover.
        if remaining < 10:
            log.warning("X daily read budget exhausted (%d)", self.budget)
            return
        start = datetime.now(timezone.utc) - timedelta(days=min(days, 7))
        params = {
            "query": self._query(asset),
            "max_results": min(100, remaining),
            "start_time": start.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "tweet.fields": "created_at,public_metrics,author_id",
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = self.http_get(RECENT_SEARCH, params=params, headers=headers, timeout=30)
        if resp.status_code != 200:
            log.warning("X search failed %s: %s", resp.status_code, resp.text[:200])
            return
        data = resp.json().get("data", [])
        self.ledger.add_x_reads(len(data))
        for t in data:
            pm = t.get("public_metrics", {})
            yield Post(
                id=f"x_{t['id']}",
                source="x",
                ticker=asset.ticker,
                created_at=datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")),
                author=str(t.get("author_id", "")),
                text=t["text"],
                url=f"https://x.com/i/status/{t['id']}",
                community="search",
                upvotes=int(pm.get("like_count", 0)),
                num_comments=int(pm.get("reply_count", 0)),
            )

"""Reddit collector built on PRAW.

Free tier: 100 queries/min per OAuth client. This collector stays well inside
that by default (one search per subreddit per query, plus comment expansion
on the top N submissions).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from ..config import CRYPTO_SUBREDDITS, STOCK_SUBREDDITS, settings
from ..models import Post
from ..tickers import Asset, mentions, search_queries
from .base import BaseSource

log = logging.getLogger(__name__)


class RedditSource(BaseSource):
    name = "reddit"

    def __init__(self, subreddits: list[str] | None = None, expand_comments: int = 10):
        import praw  # imported lazily so tests don't need it

        if not settings.reddit_configured:
            raise RuntimeError("Reddit credentials missing; see .env.example")
        self.reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )
        self.reddit.read_only = True
        self.subreddits = subreddits
        self.expand_comments = expand_comments

    def _subreddits_for(self, asset: Asset) -> list[str]:
        if self.subreddits:
            return self.subreddits
        return CRYPTO_SUBREDDITS if asset.kind == "crypto" else STOCK_SUBREDDITS

    def fetch(self, asset: Asset, days: int = 1, limit: int = 200) -> Iterator[Post]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        time_filter = "day" if days <= 1 else "week" if days <= 7 else "month"
        seen: set[str] = set()
        yielded = 0

        for sub in self._subreddits_for(asset):
            for q in search_queries(asset):
                try:
                    results = self.reddit.subreddit(sub).search(
                        q, sort="new", time_filter=time_filter, limit=limit
                    )
                    for s in results:
                        created = datetime.fromtimestamp(s.created_utc, tz=timezone.utc)
                        if created < since or s.id in seen:
                            continue
                        text = f"{s.title}\n{s.selftext or ''}".strip()
                        if not mentions(text, asset):
                            continue
                        seen.add(s.id)
                        yield Post(
                            id=f"t3_{s.id}",
                            source="reddit",
                            ticker=asset.ticker,
                            created_at=created,
                            author=str(s.author) if s.author else "[deleted]",
                            text=text[:4000],
                            url=f"https://reddit.com{s.permalink}",
                            community=sub,
                            upvotes=int(s.score),
                            num_comments=int(s.num_comments),
                        )
                        yielded += 1
                        # Expand comments on the most active threads.
                        if self.expand_comments and s.num_comments > 5:
                            yield from self._comments(s, asset, sub, since, seen)
                        if yielded >= limit:
                            return
                except Exception as e:  # rate limits, deleted subs, etc.
                    log.warning("reddit search failed r/%s %r: %s", sub, q, e)
                    time.sleep(2)

    def _comments(self, submission, asset: Asset, sub: str, since, seen) -> Iterator[Post]:
        try:
            submission.comments.replace_more(limit=0)
            comments = submission.comments.list()[: self.expand_comments * 5]
        except Exception as e:
            log.warning("comment expansion failed %s: %s", submission.id, e)
            return
        n = 0
        for c in comments:
            if c.id in seen or not getattr(c, "body", None):
                continue
            created = datetime.fromtimestamp(c.created_utc, tz=timezone.utc)
            if created < since:
                continue
            # Comments inherit the thread's topic; don't require an explicit mention.
            seen.add(c.id)
            yield Post(
                id=f"t1_{c.id}",
                source="reddit",
                ticker=asset.ticker,
                created_at=created,
                author=str(c.author) if c.author else "[deleted]",
                text=c.body[:2000],
                url=f"https://reddit.com{c.permalink}",
                community=sub,
                upvotes=int(c.score),
                is_comment=True,
            )
            n += 1
            if n >= self.expand_comments:
                return

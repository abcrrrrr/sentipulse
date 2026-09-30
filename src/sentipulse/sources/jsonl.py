"""Read posts from a JSONL file. Used for tests, replays and offline dev."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..models import Post
from ..tickers import Asset, mentions
from .base import BaseSource


class JsonlSource(BaseSource):
    name = "jsonl"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self, asset: Asset, days: int = 1, limit: int = 200) -> Iterator[Post]:
        n = 0
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                raw.setdefault("ticker", asset.ticker)
                post = Post(**raw)
                if post.ticker != asset.ticker and not mentions(post.text, asset):
                    continue
                post.ticker = asset.ticker
                yield post
                n += 1
                if n >= limit:
                    return

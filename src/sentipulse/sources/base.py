from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..models import Post
from ..tickers import Asset


class BaseSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, asset: Asset, days: int = 1, limit: int = 200) -> Iterator[Post]:
        """Yield posts mentioning `asset` from roughly the last `days` days."""

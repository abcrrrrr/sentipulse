from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Post, Score


class BaseScorer(ABC):
    name: str

    @abstractmethod
    def score_batch(self, posts: list[Post]) -> list[Score]: ...

    def score(self, post: Post) -> Score:
        return self.score_batch([post])[0]


def label_from_score(s: float, band: float = 0.15) -> str:
    if s > band:
        return "positive"
    if s < -band:
        return "negative"
    return "neutral"

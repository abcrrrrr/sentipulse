from .base import BaseScorer
from .vader import VaderScorer

__all__ = ["BaseScorer", "VaderScorer", "get_scorer"]


def get_scorer(name: str) -> BaseScorer:
    """Factory. Heavy scorers are imported lazily."""
    if name == "vader":
        return VaderScorer()
    if name == "finbert":
        from .finbert import FinBertScorer

        return FinBertScorer()
    if name == "claude":
        from .claude import ClaudeScorer

        return ClaudeScorer()
    raise ValueError(f"unknown scorer: {name}")

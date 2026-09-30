"""VADER with a small finance/retail lexicon patch.

Cheap, no model download, decent baseline. Used as the default in tests and
as a fallback when torch is not installed.
"""

from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ..models import Post, Score
from .base import BaseScorer, label_from_score

# Retail-trading slang that VADER's general lexicon gets wrong or misses.
FINANCE_LEXICON = {
    "moon": 2.5, "mooning": 2.5, "rocket": 2.0, "tendies": 2.0, "bullish": 2.5,
    "bull": 1.5, "calls": 1.0, "breakout": 1.5, "rip": 1.5, "squeeze": 1.5,
    "undervalued": 1.5, "buy": 1.0, "bought": 1.0, "hodl": 1.0, "diamond hands": 1.5,
    "bearish": -2.5, "bear": -1.5, "puts": -1.0, "dump": -2.0, "dumping": -2.0,
    "crash": -2.5, "rug": -3.0, "rugged": -3.0, "bagholder": -2.0, "bags": -1.5,
    "overvalued": -1.5, "short": -1.0, "shorting": -1.5, "scam": -3.0, "ponzi": -3.0,
    "drill": -2.0, "drilling": -2.0, "tank": -2.0, "tanking": -2.5, "guh": -2.0,
    "printing": 1.5, "green": 1.0, "red": -1.0,
}


class VaderScorer(BaseScorer):
    name = "vader"

    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()
        self.analyzer.lexicon.update(FINANCE_LEXICON)

    def score_batch(self, posts: list[Post]) -> list[Score]:
        out = []
        for p in posts:
            c = self.analyzer.polarity_scores(p.text)["compound"]
            out.append(
                Score(
                    post_id=p.id,
                    scorer=self.name,
                    label=label_from_score(c, band=0.05),
                    score=float(c),
                    confidence=abs(float(c)),
                )
            )
        return out

"""Claude scorer — used on a SAMPLE of posts for quality control.

FinBERT was trained on analyst-style financial news; it misreads sarcasm,
memes and "I'm in it for the long haul at -40%" style posts. Scoring a
random sample with Claude each day gives you (a) a calibration check on
FinBERT, and (b) a per-ticker "why" summary. Batches ~25 posts per call.

Uses structured outputs, so the response is schema-valid JSON; a refused or
truncated batch is logged and skipped rather than failing the whole run.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel

from ..config import settings
from ..models import Post, Score
from .base import BaseScorer

log = logging.getLogger(__name__)

SYSTEM = """You are a financial sentiment analyst reading retail investor posts.
For each post, judge the author's stance on the named asset's future PRICE — not
their mood. Sarcasm, memes and loss-porn are common: "$NVDA to zero, loading more
calls" is positive. Pure questions, off-topic and unclear posts are neutral.
Return one entry per post, using the post's id. score is in [-1, 1] (sign = stance,
magnitude = strength); confidence is in [0, 1]."""


class ClaudeItem(BaseModel):
    id: str
    label: Literal["positive", "negative", "neutral"]
    score: float
    confidence: float


class ClaudeBatch(BaseModel):
    scores: list[ClaudeItem]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class ClaudeScorer(BaseScorer):
    name = "claude"

    def __init__(self, model: str | None = None, client=None):
        """`client` is an injected Anthropic-compatible client (tests); default builds one."""
        if client is None:
            import anthropic

            if not settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.client = client
        self.model = model or settings.claude_model

    def score_batch(self, posts: list[Post], batch_size: int = 25) -> list[Score]:
        out: list[Score] = []
        for i in range(0, len(posts), batch_size):
            out.extend(self._call(posts[i : i + batch_size]))
        return out

    def _call(self, chunk: list[Post]) -> list[Score]:
        ticker = chunk[0].ticker
        items = [{"id": p.id, "text": p.text[:1200]} for p in chunk]
        user = f"Asset: {ticker}\nPosts:\n{json.dumps(items, ensure_ascii=False)}"
        resp = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_format=ClaudeBatch,
            # Classification: low effort is plenty and keeps the QC sample cheap.
            output_config={"effort": "low"},
            # On a safety decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason != "end_turn" or resp.parsed_output is None:
            log.error("Claude batch for %s skipped: stop_reason=%s", ticker, resp.stop_reason)
            return []
        by_id = {p.id: p for p in chunk}
        return [
            Score(
                post_id=s.id,
                ticker=by_id[s.id].ticker,
                scorer=self.name,
                label=s.label,
                score=_clamp(s.score, -1.0, 1.0),
                confidence=_clamp(s.confidence, 0.0, 1.0),
            )
            for s in resp.parsed_output.scores
            if s.id in by_id
        ]

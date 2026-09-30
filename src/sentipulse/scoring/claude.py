"""Claude scorer — used on a SAMPLE of posts for quality control.

FinBERT was trained on analyst-style financial news; it misreads sarcasm,
memes and "I'm in it for the long haul at -40%" style posts. Scoring a
random sample with Claude each day gives you (a) a calibration check on
FinBERT, and (b) a per-ticker "why" summary. Batches ~25 posts per call.
"""

from __future__ import annotations

import json
import logging

from ..config import settings
from ..models import Post, Score
from .base import BaseScorer

log = logging.getLogger(__name__)

SYSTEM = """You are a financial sentiment analyst reading retail investor posts.
For each post, judge the author's stance on the named asset's future PRICE — not
their mood. Sarcasm, memes and loss-porn are common: "$NVDA to zero, loading more
calls" is positive. Pure questions, off-topic and unclear posts are neutral.
Respond with JSON only: {"scores":[{"id":"...","label":"positive|negative|neutral",
"score":-1.0..1.0,"confidence":0.0..1.0}]}"""


class ClaudeScorer(BaseScorer):
    name = "claude"

    def __init__(self, model: str | None = None):
        import anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model or settings.claude_model

    def score_batch(self, posts: list[Post], batch_size: int = 25) -> list[Score]:
        out: list[Score] = []
        for i in range(0, len(posts), batch_size):
            chunk = posts[i : i + batch_size]
            out.extend(self._call(chunk))
        return out

    def _call(self, chunk: list[Post]) -> list[Score]:
        ticker = chunk[0].ticker
        items = [{"id": p.id, "text": p.text[:1200]} for p in chunk]
        user = f"Asset: {ticker}\nPosts:\n{json.dumps(items, ensure_ascii=False)}"
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```")
        try:
            parsed = json.loads(raw)["scores"]
        except Exception as e:
            log.error("Claude returned non-JSON: %s | %s", e, raw[:200])
            return []
        by_id = {p.id: p for p in chunk}
        scores = []
        for s in parsed:
            if s.get("id") not in by_id:
                continue
            scores.append(
                Score(
                    post_id=s["id"],
                    scorer=self.name,
                    label=s.get("label", "neutral"),
                    score=max(-1.0, min(1.0, float(s.get("score", 0.0)))),
                    confidence=max(0.0, min(1.0, float(s.get("confidence", 0.5)))),
                )
            )
        return scores

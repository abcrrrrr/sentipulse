"""FinBERT (ProsusAI/finbert) — finance-tuned BERT classifier.

Runs locally on CPU at roughly 20-50 posts/sec. First run downloads ~440MB.
Install with `pip install -e ".[finbert]"`.
"""

from __future__ import annotations

from ..models import Post, Score
from .base import BaseScorer

MODEL_ID = "ProsusAI/finbert"


class FinBertScorer(BaseScorer):
    name = "finbert"

    def __init__(self, model_id: str = MODEL_ID, device: str | None = None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_id)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device).eval()
        # ProsusAI/finbert label order: positive, negative, neutral
        self.labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]

    def score_batch(self, posts: list[Post], batch_size: int = 32) -> list[Score]:
        out: list[Score] = []
        for i in range(0, len(posts), batch_size):
            chunk = posts[i : i + batch_size]
            enc = self.tok(
                [p.text for p in chunk],
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            ).to(self.device)
            with self.torch.no_grad():
                probs = self.model(**enc).logits.softmax(-1).cpu().tolist()
            for p, pr in zip(chunk, probs):
                d = dict(zip(self.labels, pr))
                signed = d.get("positive", 0.0) - d.get("negative", 0.0)
                label = max(d, key=d.get)
                out.append(
                    Score(
                        post_id=p.id,
                        ticker=p.ticker,
                        scorer=self.name,
                        label=label,  # type: ignore[arg-type]
                        score=float(signed),
                        confidence=float(d[label]),
                    )
                )
        return out

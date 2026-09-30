"""ClaudeScorer against a fake client: no network, no API key."""

from datetime import datetime, timezone
from types import SimpleNamespace

from sentipulse.models import Post
from sentipulse.scoring.claude import ClaudeBatch, ClaudeScorer


def _posts(n: int) -> list[Post]:
    t = datetime(2026, 9, 14, tzinfo=timezone.utc)
    return [
        Post(id=f"t3_{i}", source="reddit", ticker="NVDA", created_at=t, text=f"post {i}")
        for i in range(n)
    ]


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.requests.append(kw)
        return self.responses.pop(0)


def _ok(items):
    return SimpleNamespace(stop_reason="end_turn", parsed_output=ClaudeBatch(scores=items))


def test_scores_are_attached_to_ticker_and_clamped():
    client = _FakeClient(
        [_ok([{"id": "t3_0", "label": "positive", "score": 1.7, "confidence": 0.9}])]
    )
    [s] = ClaudeScorer(client=client).score_batch(_posts(1))
    assert (s.post_id, s.ticker, s.label, s.score) == ("t3_0", "NVDA", "positive", 1.0)
    assert client.requests[0]["model"] == "claude-sonnet-5-5"


def test_unknown_ids_are_dropped():
    client = _FakeClient(
        [_ok([{"id": "t3_999", "label": "negative", "score": -0.5, "confidence": 0.5}])]
    )
    assert ClaudeScorer(client=client).score_batch(_posts(1)) == []


def test_refusal_skips_batch_without_crashing():
    refused = SimpleNamespace(stop_reason="refusal", parsed_output=None)
    ok = _ok([{"id": "t3_25", "label": "neutral", "score": 0.0, "confidence": 0.5}])
    client = _FakeClient([refused, ok])
    scores = ClaudeScorer(client=client).score_batch(_posts(26))
    assert [s.post_id for s in scores] == ["t3_25"]

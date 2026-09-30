import json
from datetime import datetime, timezone
from types import SimpleNamespace

from sentipulse.sources import JsonlSource, RedditSource, XSource
from sentipulse.store import Store
from sentipulse.tickers import resolve


def test_jsonl_reads_utf8_regardless_of_locale(tmp_path):
    f = tmp_path / "p.jsonl"
    row = {
        "id": "t3_e",
        "source": "reddit",
        "ticker": "NVDA",
        "created_at": "2026-09-14T13:00:00+00:00",
        "text": "NVDA 🚀🚀 to the moon — ça va",
    }
    f.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    [post] = JsonlSource(f).fetch(resolve("NVDA"), days=30)
    assert post.text == row["text"]


# ---- Reddit, with a fake PRAW client --------------------------------------


def _comment(i: int, ts: float):
    return SimpleNamespace(
        id=f"c{i}", body=f"comment {i}", created_utc=ts, author="u", permalink=f"/c{i}", score=1
    )


def _submission(i: int, ts: float, n_comments: int):
    comments = [_comment(i * 100 + j, ts) for j in range(n_comments)]
    forest = SimpleNamespace(replace_more=lambda limit: None, list=lambda: comments)
    return SimpleNamespace(
        id=f"s{i}",
        title=f"NVDA thread {i}",
        selftext="",
        created_utc=ts,
        author="op",
        permalink=f"/s{i}",
        score=10,
        num_comments=n_comments,
        comments=forest,
    )


class _FakeReddit:
    def __init__(self, submissions):
        self.submissions = submissions

    def subreddit(self, name):
        return SimpleNamespace(search=lambda q, **kw: iter(self.submissions))


def test_reddit_limit_counts_comments_too():
    ts = datetime.now(timezone.utc).timestamp()
    fake = _FakeReddit([_submission(i, ts, n_comments=20) for i in range(5)])
    src = RedditSource(subreddits=["stocks"], expand_comments=10, reddit=fake)
    posts = list(src.fetch(resolve("NVDA"), days=1, limit=15))
    assert len(posts) == 15
    assert any(p.is_comment for p in posts)


# ---- X, with a fake HTTP getter --------------------------------------------


class _FakeResp:
    status_code = 200

    def __init__(self, n):
        self._data = [
            {"id": str(i), "text": f"$NVDA {i}", "created_at": "2026-09-30T12:00:00Z"}
            for i in range(n)
        ]

    def json(self):
        return {"data": self._data}


def test_x_budget_is_shared_across_runs(tmp_path):
    calls = []

    def http_get(url, params, headers, timeout):
        calls.append(params)
        return _FakeResp(params["max_results"])

    store = Store(tmp_path / "t.duckdb")
    nvda = resolve("NVDA")
    first = XSource(store, daily_budget=100, bearer_token="t", http_get=http_get)
    assert len(list(first.fetch(nvda, limit=100))) == 100

    # A second process on the same day must see the budget as spent.
    second = XSource(store, daily_budget=100, bearer_token="t", http_get=http_get)
    assert list(second.fetch(nvda, limit=100)) == []
    assert len(calls) == 1

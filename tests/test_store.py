from datetime import datetime, timedelta, timezone

from sentipulse.models import Post, Score
from sentipulse.store import Store


def _post(ticker: str, created_at: datetime | None = None) -> Post:
    return Post(
        id="t3_x",
        source="reddit",
        ticker=ticker,
        created_at=created_at or datetime.now(timezone.utc),
        text="NVDA vs AMD, which one?",
    )


def test_same_post_can_belong_to_two_tickers(tmp_path):
    store = Store(tmp_path / "t.duckdb")
    store.upsert_posts([_post("NVDA")])
    store.upsert_posts([_post("AMD")])
    assert len(store.unscored_posts("NVDA", "vader")) == 1
    assert len(store.unscored_posts("AMD", "vader")) == 1


def test_scores_are_per_ticker(tmp_path):
    store = Store(tmp_path / "t.duckdb")
    store.upsert_posts([_post("NVDA"), _post("AMD")])
    store.upsert_scores(
        [Score(post_id="t3_x", ticker="NVDA", scorer="claude", label="positive", score=0.8)]
    )
    assert store.unscored_posts("NVDA", "claude") == []
    assert len(store.unscored_posts("AMD", "claude")) == 1
    scored = store.scored_posts("NVDA", "claude")
    assert list(scored.label) == ["positive"]


def test_scored_posts_without_window_returns_old_posts(tmp_path):
    store = Store(tmp_path / "t.duckdb")
    old = datetime.now(timezone.utc) - timedelta(days=400)
    store.upsert_posts([_post("NVDA", old)])
    store.upsert_scores(
        [Score(post_id="t3_x", ticker="NVDA", scorer="vader", label="neutral", score=0.0)]
    )
    assert store.scored_posts("NVDA", "vader", days=30).empty
    assert len(store.scored_posts("NVDA", "vader", days=None)) == 1


def test_x_read_ledger_persists_across_connections(tmp_path):
    path = tmp_path / "t.duckdb"
    store = Store(path)
    store.add_x_reads(120)
    store.close()
    store = Store(path)
    store.add_x_reads(30)
    assert store.x_reads_today() == 150


def test_daily_window_is_anchored_at_latest_data(tmp_path):
    import pandas as pd

    store = Store(tmp_path / "t.duckdb")
    days = pd.date_range("2025-01-01", periods=20, freq="D").date
    store.upsert_daily(
        pd.DataFrame(
            {"ticker": "NVDA", "day": days, "scorer": "vader", "n_posts": 1, "mean_score": 0.0,
             "weighted_score": 0.0, "bull_ratio": 0.0, "bear_ratio": 0.0, "net_ratio": 0.0}
        )
    )
    # Data ended long ago; "last 7 days" means the last 7 days that have data.
    out = store.daily("NVDA", "vader", days=7)
    assert len(out) == 7
    assert out.day.max().date() == days[-1]

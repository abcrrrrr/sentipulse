"""End-to-end on the bundled sample file with VADER (no network, no model download)."""

from pathlib import Path

from sentipulse.aggregate import daily_aggregate
from sentipulse.scoring import get_scorer
from sentipulse.sources import JsonlSource
from sentipulse.store import Store
from sentipulse.tickers import resolve

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_nvda.jsonl"


def test_offline_pipeline(tmp_path):
    store = Store(tmp_path / "t.duckdb")
    asset = resolve("NVDA")
    posts = list(JsonlSource(SAMPLE).fetch(asset, days=30, limit=1000))
    assert len(posts) > 50
    assert store.upsert_posts(posts) == len(posts)
    # idempotent
    assert store.upsert_posts(posts) == len(posts)

    unscored = store.unscored_posts("NVDA", "vader")
    assert len(unscored) == len(posts)
    scores = get_scorer("vader").score_batch(unscored)
    store.upsert_scores(scores)
    assert store.unscored_posts("NVDA", "vader") == []

    # days=None: the sample is fixed-date data, so a now()-relative window would rot.
    scored = store.scored_posts("NVDA", "vader", days=None)
    daily = daily_aggregate(scored, "vader")
    assert daily.n_posts.sum() == len(posts)
    store.upsert_daily(daily)
    out = store.daily("NVDA", "vader", days=None)
    assert len(out) == len(daily)
    assert out.net_ratio.between(-1, 1).all()
    store.close()

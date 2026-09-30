from datetime import datetime, timezone

import pandas as pd

from sentipulse.aggregate import add_signals, daily_aggregate


def _df():
    t = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    rows = [
        ("NVDA", t, 100, "positive", 0.9),
        ("NVDA", t, 0, "negative", -0.8),
        ("NVDA", t, 0, "neutral", 0.0),
        ("NVDA", t.replace(day=11), 5, "positive", 0.5),
    ]
    return pd.DataFrame(rows, columns=["ticker", "created_at", "upvotes", "label", "score"])


def test_daily_aggregate_basic():
    d = daily_aggregate(_df(), "vader")
    assert len(d) == 2
    day1 = d.iloc[0]
    assert day1.n_posts == 3
    assert abs(day1.mean_score - (0.9 - 0.8) / 3) < 1e-9
    assert abs(day1.net_ratio - (1 / 3 - 1 / 3)) < 1e-9
    # upvote weighting pulls toward the 100-upvote positive post
    assert day1.weighted_score > day1.mean_score
    assert day1.scorer == "vader"


def test_add_signals_columns():
    d = add_signals(daily_aggregate(_df(), "vader"))
    for c in ["net_ma_short", "net_ma_long", "attention_z"]:
        assert c in d.columns


def test_empty():
    assert daily_aggregate(pd.DataFrame(), "vader").empty

from datetime import date, datetime, timezone

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


def _daily(n_posts: dict[int, int]) -> pd.DataFrame:
    rows = [
        {"ticker": "NVDA", "day": date(2026, 9, d), "scorer": "vader", "n_posts": n,
         "net_ratio": 0.1}
        for d, n in n_posts.items()
    ]
    return pd.DataFrame(rows)


def test_attention_fills_missing_days_with_zero_posts():
    d = add_signals(_daily({1: 10, 2: 10, 4: 10}))
    assert list(d.day) == [date(2026, 9, i) for i in range(1, 5)]
    assert d.set_index("day").loc[date(2026, 9, 3), "n_posts"] == 0


def test_attention_baseline_excludes_today():
    d = add_signals(_daily({1: 10, 2: 12, 3: 10, 4: 12, 5: 50}))
    # Baseline is days 1-4 (mean 11, std ~1.15); a spike to 50 is ~34 sigma.
    # If today leaked into its own baseline the z-score would be under 2.
    assert d.iloc[-1].attention_z > 10


def test_empty():
    assert daily_aggregate(pd.DataFrame(), "vader").empty

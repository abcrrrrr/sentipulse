from datetime import datetime, timezone

import pandas as pd
import pytest
from typer.testing import CliRunner

from sentipulse.agreement import agreement_stats, sweep_band
from sentipulse.cli import app
from sentipulse.models import Post, Score
from sentipulse.store import Store


def _paired(labels_a, labels_b, scores_a=None, scores_b=None) -> pd.DataFrame:
    n = len(labels_a)
    return pd.DataFrame(
        {
            "post_id": [f"t3_{i}" for i in range(n)],
            "text": [f"post {i}" for i in range(n)],
            "label_a": labels_a,
            "score_a": scores_a or [0.0] * n,
            "label_b": labels_b,
            "score_b": scores_b or [0.0] * n,
        }
    )


def test_perfect_agreement():
    labels = ["positive", "negative", "neutral", "positive"]
    s = agreement_stats(_paired(labels, labels, [0.9, -0.8, 0.0, 0.5], [0.8, -0.9, 0.1, 0.6]))
    assert s.n == 4
    assert s.match_rate == 1.0
    assert s.kappa == pytest.approx(1.0)
    assert s.score_corr > 0.9


def test_kappa_corrects_for_chance():
    a = ["positive", "positive", "negative", "neutral"]
    b = ["positive", "negative", "negative", "neutral"]
    s = agreement_stats(_paired(a, b))
    assert s.match_rate == 0.75
    # p_o = 0.75, p_e = .5*.25 + .25*.5 + .25*.25 = 0.3125
    assert s.kappa == pytest.approx((0.75 - 0.3125) / (1 - 0.3125))
    # rows = scorer A, columns = scorer B
    assert s.confusion.loc["positive", "negative"] == 1


def test_empty_pairing():
    s = agreement_stats(_paired([], []))
    assert s.n == 0


def test_band_sweep_finds_band_that_separates_neutral():
    paired = _paired(
        labels_a=["positive"] * 4,  # ignored: the sweep relabels from score_a
        labels_b=["positive", "neutral", "negative", "neutral"],
        scores_a=[0.3, 0.1, -0.3, 0.05],
    )
    sweep = sweep_band(paired, bands=[0.05, 0.15, 0.4])
    assert list(sweep.band) == [0.05, 0.15, 0.4]
    best = sweep.loc[sweep.kappa.idxmax()]
    assert best.band == 0.15
    assert best.kappa == pytest.approx(1.0)


# ---- store + CLI -------------------------------------------------------------


def _seed(store: Store):
    t = datetime.now(timezone.utc)
    posts = [
        Post(id=f"t3_{i}", source="reddit", ticker=tk, created_at=t, text=f"post {i}")
        for i in range(3)
        for tk in ("NVDA", "AMD")
    ]
    store.upsert_posts(posts)

    def s(pid, tk, scorer, label, score):
        return Score(post_id=pid, ticker=tk, scorer=scorer, label=label, score=score)

    store.upsert_scores(
        [
            s("t3_0", "NVDA", "vader", "positive", 0.6),
            s("t3_1", "NVDA", "vader", "negative", -0.4),
            s("t3_2", "NVDA", "vader", "neutral", 0.0),  # no claude score: excluded
            s("t3_0", "NVDA", "claude", "positive", 0.7),
            s("t3_1", "NVDA", "claude", "positive", 0.5),
            s("t3_0", "AMD", "claude", "negative", -0.5),  # other ticker: excluded
        ]
    )


def test_paired_scores_only_includes_posts_scored_by_both(tmp_path):
    store = Store(tmp_path / "t.duckdb")
    _seed(store)
    p = store.paired_scores("NVDA", "vader", "claude", days=None)
    assert sorted(p.post_id) == ["t3_0", "t3_1"]
    assert set(p.columns) >= {"text", "label_a", "score_a", "label_b", "score_b"}


def test_agreement_cli(tmp_path):
    db = tmp_path / "t.duckdb"
    store = Store(db)
    _seed(store)
    store.close()
    result = CliRunner().invoke(
        app, ["agreement", "NVDA", "--a", "vader", "--b", "claude", "--db", str(db)]
    )
    assert result.exit_code == 0, result.output
    assert "n=2" in result.output
    assert "kappa" in result.output
    assert "Best band" in result.output


def test_agreement_cli_with_single_pair(tmp_path):
    db = tmp_path / "t.duckdb"
    store = Store(db)
    t = datetime.now(timezone.utc)
    store.upsert_posts([Post(id="t3_0", source="reddit", ticker="NVDA", created_at=t, text="x")])
    store.upsert_scores(
        [
            Score(post_id="t3_0", ticker="NVDA", scorer="vader", label="positive", score=0.5),
            Score(post_id="t3_0", ticker="NVDA", scorer="claude", label="positive", score=0.4),
        ]
    )
    store.close()
    result = CliRunner().invoke(
        app, ["agreement", "NVDA", "--a", "vader", "--b", "claude", "--db", str(db)]
    )
    assert result.exit_code == 0, result.output
    assert "n=1" in result.output

"""Compare two scorers on the posts both have scored (Phase 2 calibration).

Typical use: A = finbert (every post), B = claude (the daily QC sample).
Label match rate alone flatters a scorer that calls everything neutral, so
Cohen's kappa is reported too: agreement beyond what the two label
distributions would produce by chance (1 = perfect, 0 = chance level).

`sweep_band` answers "where should the neutral band sit?": it relabels A's
signed score with `label_from_score(score, band)` for each candidate band and
measures agreement with B's labels.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .scoring.base import label_from_score

LABELS = ["positive", "neutral", "negative"]
DEFAULT_BANDS = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]


@dataclass
class Agreement:
    n: int
    match_rate: float
    kappa: float
    score_corr: float
    confusion: pd.DataFrame  # rows = scorer A's label, columns = scorer B's label


def cohen_kappa(a: pd.Series, b: pd.Series) -> float:
    if len(a) == 0:
        return float("nan")
    p_o = float((a.to_numpy() == b.to_numpy()).mean())
    pa = a.value_counts(normalize=True)
    pb = b.value_counts(normalize=True)
    p_e = float(sum(pa.get(lbl, 0.0) * pb.get(lbl, 0.0) for lbl in LABELS))
    if p_e == 1.0:  # both scorers used a single identical label throughout
        return 1.0 if p_o == 1.0 else float("nan")
    return (p_o - p_e) / (1.0 - p_e)


def agreement_stats(paired: pd.DataFrame) -> Agreement:
    """`paired` needs columns label_a, score_a, label_b, score_b."""
    n = len(paired)
    confusion = pd.crosstab(
        pd.Categorical(paired["label_a"], categories=LABELS),
        pd.Categorical(paired["label_b"], categories=LABELS),
        rownames=["a"],
        colnames=["b"],
        dropna=False,
    )
    if n == 0:
        return Agreement(0, float("nan"), float("nan"), float("nan"), confusion)
    corr = (
        float(np.corrcoef(paired["score_a"], paired["score_b"])[0, 1])
        if n > 1 and paired["score_a"].std() > 0 and paired["score_b"].std() > 0
        else float("nan")
    )
    return Agreement(
        n=n,
        match_rate=float((paired["label_a"] == paired["label_b"]).mean()),
        kappa=cohen_kappa(paired["label_a"], paired["label_b"]),
        score_corr=corr,
        confusion=confusion,
    )


def sweep_band(paired: pd.DataFrame, bands: list[float] | None = None) -> pd.DataFrame:
    """Agreement with B's labels when A's labels come from `label_from_score(score_a, band)`."""
    rows = []
    for band in bands or DEFAULT_BANDS:
        relabeled = paired["score_a"].map(lambda s, b=band: label_from_score(s, band=b))
        rows.append(
            {
                "band": band,
                "match_rate": float((relabeled == paired["label_b"]).mean()),
                "kappa": cohen_kappa(relabeled, paired["label_b"]),
                "pct_neutral_a": float((relabeled == "neutral").mean()),
            }
        )
    return pd.DataFrame(rows)


def top_disagreements(paired: pd.DataFrame, k: int = 10) -> pd.DataFrame:
    """Posts where the two scores are furthest apart: the ones worth reading."""
    gap = (paired["score_a"] - paired["score_b"]).abs()
    return paired.assign(gap=gap).sort_values("gap", ascending=False).head(k)

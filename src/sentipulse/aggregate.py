"""Turn per-post scores into a daily per-ticker time series.

Design notes:
- weighted_score weights by log1p(upvotes): a 2,000-upvote thread should
  matter more than a 0-upvote comment, but not 2,000x more.
- net_ratio = (bull - bear) / n is usually the most stable single signal;
  mean_score is noisier on low-volume days.
- n_posts is itself a feature (attention spikes precede moves more reliably
  than sign does). Always store it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_aggregate(scored: pd.DataFrame, scorer: str, min_posts: int = 1) -> pd.DataFrame:
    """`scored` needs columns: ticker, created_at, upvotes, label, score."""
    if scored.empty:
        return pd.DataFrame()
    df = scored.copy()
    df["day"] = pd.to_datetime(df["created_at"], utc=True).dt.date
    df["w"] = np.log1p(df["upvotes"].clip(lower=0))
    df["is_bull"] = (df["label"] == "positive").astype(float)
    df["is_bear"] = (df["label"] == "negative").astype(float)

    def _agg(g: pd.DataFrame) -> pd.Series:
        w = g["w"].to_numpy()
        s = g["score"].to_numpy()
        wsum = w.sum()
        return pd.Series(
            {
                "n_posts": len(g),
                "mean_score": float(s.mean()),
                "weighted_score": float((w * s).sum() / wsum) if wsum > 0 else float(s.mean()),
                "bull_ratio": float(g["is_bull"].mean()),
                "bear_ratio": float(g["is_bear"].mean()),
            }
        )

    out = df.groupby(["ticker", "day"]).apply(_agg, include_groups=False).reset_index()
    out["net_ratio"] = out["bull_ratio"] - out["bear_ratio"]
    out["scorer"] = scorer
    out = out[out["n_posts"] >= min_posts]
    return out.sort_values(["ticker", "day"]).reset_index(drop=True)


def add_signals(daily: pd.DataFrame, short: int = 3, long: int = 14) -> pd.DataFrame:
    """Rolling smoothing + z-scored attention for one ticker/scorer series.

    Windows are calendar days: days with no posts are inserted with n_posts=0
    (sentiment columns stay NaN). attention_z compares today's volume with the
    previous `long` days only, so a spike can't dilute its own baseline.
    """
    if daily.empty:
        return daily
    d = daily.copy()
    d["day"] = pd.to_datetime(d["day"])
    d = d.set_index("day").sort_index()
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="D"))
    d["n_posts"] = d["n_posts"].fillna(0).astype(int)
    for col in ("ticker", "scorer"):
        if col in d:
            d[col] = d[col].ffill()
    d.index.name = "day"
    d = d.reset_index()
    d["day"] = d["day"].dt.date

    d["net_ma_short"] = d["net_ratio"].rolling(short, min_periods=1).mean()
    d["net_ma_long"] = d["net_ratio"].rolling(long, min_periods=1).mean()
    baseline = d["n_posts"].shift(1).rolling(long, min_periods=2)
    vol_std = baseline.std().replace(0, np.nan)
    d["attention_z"] = ((d["n_posts"] - baseline.mean()) / vol_std).fillna(0.0)
    return d

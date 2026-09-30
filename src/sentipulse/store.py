"""DuckDB storage. Single file, zero ops, pandas-native, fast enough for years
of daily data. Swap for Snowflake later by reimplementing this module."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .config import settings
from .models import Post, Score

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR PRIMARY KEY,
    source VARCHAR,
    ticker VARCHAR,
    created_at TIMESTAMPTZ,
    author VARCHAR,
    text VARCHAR,
    url VARCHAR,
    community VARCHAR,
    upvotes INTEGER,
    num_comments INTEGER,
    is_comment BOOLEAN
);
CREATE TABLE IF NOT EXISTS scores (
    post_id VARCHAR,
    scorer VARCHAR,
    label VARCHAR,
    score DOUBLE,
    confidence DOUBLE,
    scored_at TIMESTAMP,
    PRIMARY KEY (post_id, scorer)
);
CREATE TABLE IF NOT EXISTS daily (
    ticker VARCHAR,
    day DATE,
    scorer VARCHAR,
    n_posts INTEGER,
    mean_score DOUBLE,
    weighted_score DOUBLE,
    bull_ratio DOUBLE,
    bear_ratio DOUBLE,
    net_ratio DOUBLE,
    PRIMARY KEY (ticker, day, scorer)
);
CREATE TABLE IF NOT EXISTS prices (
    ticker VARCHAR,
    day DATE,
    close DOUBLE,
    volume DOUBLE,
    PRIMARY KEY (ticker, day)
);
"""


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or settings.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.path))
        self.con.execute(SCHEMA)

    # ---- writes ---------------------------------------------------------
    def upsert_posts(self, posts: list[Post]) -> int:
        if not posts:
            return 0
        df = pd.DataFrame([p.model_dump() for p in posts])
        self.con.register("df_posts", df)
        self.con.execute("INSERT OR REPLACE INTO posts SELECT * FROM df_posts")
        self.con.unregister("df_posts")
        return len(df)

    def upsert_scores(self, scores: list[Score]) -> int:
        if not scores:
            return 0
        df = pd.DataFrame([s.model_dump() for s in scores])
        self.con.register("df_scores", df)
        self.con.execute("INSERT OR REPLACE INTO scores SELECT * FROM df_scores")
        self.con.unregister("df_scores")
        return len(df)

    def upsert_daily(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = ["ticker", "day", "scorer", "n_posts", "mean_score", "weighted_score",
                "bull_ratio", "bear_ratio", "net_ratio"]
        self.con.register("df_daily", df[cols])
        self.con.execute("INSERT OR REPLACE INTO daily SELECT * FROM df_daily")
        self.con.unregister("df_daily")
        return len(df)

    def upsert_prices(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self.con.register("df_prices", df[["ticker", "day", "close", "volume"]])
        self.con.execute("INSERT OR REPLACE INTO prices SELECT * FROM df_prices")
        self.con.unregister("df_prices")
        return len(df)

    # ---- reads ----------------------------------------------------------
    def unscored_posts(self, ticker: str, scorer: str, limit: int = 5000) -> list[Post]:
        rows = self.con.execute(
            """
            SELECT p.* FROM posts p
            LEFT JOIN scores s ON s.post_id = p.id AND s.scorer = ?
            WHERE p.ticker = ? AND s.post_id IS NULL
            ORDER BY p.created_at DESC LIMIT ?
            """,
            [scorer, ticker, limit],
        ).df()
        return [Post(**r) for r in rows.to_dict("records")]

    def scored_posts(self, ticker: str, scorer: str, days: int = 30) -> pd.DataFrame:
        return self.con.execute(
            """
            SELECT p.id, p.source, p.ticker, p.created_at, p.upvotes, p.is_comment,
                   p.community, p.text, p.url, s.label, s.score, s.confidence
            FROM posts p JOIN scores s ON s.post_id = p.id
            WHERE p.ticker = ? AND s.scorer = ?
              AND p.created_at >= now() - (? * INTERVAL '1 day')
            """,
            [ticker, scorer, days],
        ).df()

    def daily(self, ticker: str, scorer: str, days: int = 90) -> pd.DataFrame:
        return self.con.execute(
            """
            SELECT d.*, pr.close
            FROM daily d LEFT JOIN prices pr ON pr.ticker = d.ticker AND pr.day = d.day
            WHERE d.ticker = ? AND d.scorer = ?
              AND d.day >= current_date - ?
            ORDER BY d.day
            """,
            [ticker, scorer, days],
        ).df()

    def tickers(self) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT DISTINCT ticker FROM posts ORDER BY 1").fetchall()]

    def close(self):
        self.con.close()

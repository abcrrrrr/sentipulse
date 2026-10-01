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
    id VARCHAR,
    source VARCHAR,
    ticker VARCHAR,
    created_at TIMESTAMPTZ,
    author VARCHAR,
    text VARCHAR,
    url VARCHAR,
    community VARCHAR,
    upvotes INTEGER,
    num_comments INTEGER,
    is_comment BOOLEAN,
    -- One thread can be about several assets, so a post is stored once per ticker.
    PRIMARY KEY (id, ticker)
);
CREATE TABLE IF NOT EXISTS scores (
    post_id VARCHAR,
    ticker VARCHAR,
    scorer VARCHAR,
    label VARCHAR,
    score DOUBLE,
    confidence DOUBLE,
    scored_at TIMESTAMPTZ,
    PRIMARY KEY (post_id, ticker, scorer)
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
-- Daily attention numbers (no sentiment): Wikipedia views, ApeWisdom mentions, ...
CREATE TABLE IF NOT EXISTS attention (
    ticker VARCHAR,
    day DATE,
    source VARCHAR,
    metric VARCHAR,
    value DOUBLE,
    PRIMARY KEY (ticker, day, source, metric)
);
-- Paid X reads per UTC day, so the budget holds across separate runs.
CREATE TABLE IF NOT EXISTS x_reads (
    day DATE PRIMARY KEY,
    reads INTEGER
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
        self.con.execute("INSERT OR REPLACE INTO posts BY NAME SELECT * FROM df_posts")
        self.con.unregister("df_posts")
        return len(df)

    def upsert_scores(self, scores: list[Score]) -> int:
        if not scores:
            return 0
        df = pd.DataFrame([s.model_dump() for s in scores])
        self.con.register("df_scores", df)
        self.con.execute(
            "INSERT OR REPLACE INTO scores BY NAME SELECT * FROM df_scores"
        )
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

    def upsert_attention(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        self.con.register("df_attention", df[["ticker", "day", "source", "metric", "value"]])
        self.con.execute("INSERT OR REPLACE INTO attention BY NAME SELECT * FROM df_attention")
        self.con.unregister("df_attention")
        return len(df)

    # ---- reads ----------------------------------------------------------
    def unscored_posts(self, ticker: str, scorer: str, limit: int = 5000) -> list[Post]:
        rows = self.con.execute(
            """
            SELECT p.* FROM posts p
            LEFT JOIN scores s ON s.post_id = p.id AND s.ticker = p.ticker AND s.scorer = ?
            WHERE p.ticker = ? AND s.post_id IS NULL
            ORDER BY p.created_at DESC LIMIT ?
            """,
            [scorer, ticker, limit],
        ).df()
        return [Post(**r) for r in rows.to_dict("records")]

    def scored_posts(self, ticker: str, scorer: str, days: int | None = 30) -> pd.DataFrame:
        """Scored posts from the last `days` days; `days=None` means all history."""
        return self.con.execute(
            """
            SELECT p.id, p.source, p.ticker, p.created_at, p.upvotes, p.is_comment,
                   p.community, p.text, p.url, s.label, s.score, s.confidence
            FROM posts p JOIN scores s ON s.post_id = p.id AND s.ticker = p.ticker
            WHERE p.ticker = ? AND s.scorer = ?
              AND (?::INTEGER IS NULL OR p.created_at >= now() - (? * INTERVAL '1 day'))
            """,
            [ticker, scorer, days, days],
        ).df()

    def daily(self, ticker: str, scorer: str, days: int | None = 90) -> pd.DataFrame:
        """The last `days` days of daily rows (counted back from the latest day with
        data, not from today), joined to closes. `days=None` means all history."""
        return self.con.execute(
            """
            SELECT d.*, pr.close
            FROM daily d LEFT JOIN prices pr ON pr.ticker = d.ticker AND pr.day = d.day
            WHERE d.ticker = ? AND d.scorer = ?
              AND (?::INTEGER IS NULL OR d.day > (
                  SELECT max(day) FROM daily WHERE ticker = d.ticker AND scorer = d.scorer
              ) - ?::INTEGER)
            ORDER BY d.day
            """,
            [ticker, scorer, days, days],
        ).df()

    def paired_scores(
        self, ticker: str, scorer_a: str, scorer_b: str, days: int | None = 30
    ) -> pd.DataFrame:
        """Posts scored by both scorers, side by side (suffixes _a / _b)."""
        return self.con.execute(
            """
            SELECT p.id AS post_id, p.created_at, p.community, p.text, p.url,
                   a.label AS label_a, a.score AS score_a,
                   b.label AS label_b, b.score AS score_b
            FROM posts p
            JOIN scores a ON a.post_id = p.id AND a.ticker = p.ticker AND a.scorer = ?
            JOIN scores b ON b.post_id = p.id AND b.ticker = p.ticker AND b.scorer = ?
            WHERE p.ticker = ?
              AND (?::INTEGER IS NULL OR p.created_at >= now() - (? * INTERVAL '1 day'))
            ORDER BY p.created_at
            """,
            [scorer_a, scorer_b, ticker, days, days],
        ).df()

    def attention(self, ticker: str, days: int | None = 90) -> pd.DataFrame:
        """Long-format attention rows; window counted back from the latest day with data."""
        return self.con.execute(
            """
            SELECT * FROM attention a
            WHERE a.ticker = ?
              AND (?::INTEGER IS NULL OR a.day > (
                  SELECT max(day) FROM attention WHERE ticker = a.ticker
              ) - ?::INTEGER)
            ORDER BY a.day, a.source, a.metric
            """,
            [ticker, days, days],
        ).df()

    def x_reads_today(self) -> int:
        row = self.con.execute(
            "SELECT reads FROM x_reads WHERE day = (now() AT TIME ZONE 'UTC')::DATE"
        ).fetchone()
        return row[0] if row else 0

    def add_x_reads(self, n: int) -> None:
        self.con.execute(
            """
            INSERT INTO x_reads VALUES ((now() AT TIME ZONE 'UTC')::DATE, ?)
            ON CONFLICT (day) DO UPDATE SET reads = reads + excluded.reads
            """,
            [n],
        )

    def tickers(self) -> list[str]:
        rows = self.con.execute(
            "SELECT ticker FROM posts UNION SELECT ticker FROM attention ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]

    def close(self):
        self.con.close()

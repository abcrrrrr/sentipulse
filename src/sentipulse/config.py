"""Environment-driven configuration. Load once, import everywhere."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Subreddits searched per asset class. Add/remove freely; this is the main
# lever for coverage vs. noise.
STOCK_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "options",
    "StockMarket",
    "ValueInvesting",
]
CRYPTO_SUBREDDITS = [
    "CryptoCurrency",
    "CryptoMarkets",
    "Bitcoin",
    "ethereum",
    "solana",
    "altcoin",
]


@dataclass
class Settings:
    reddit_client_id: str = field(default_factory=lambda: os.getenv("REDDIT_CLIENT_ID", ""))
    reddit_client_secret: str = field(
        default_factory=lambda: os.getenv("REDDIT_CLIENT_SECRET", "")
    )
    reddit_user_agent: str = field(
        default_factory=lambda: os.getenv("REDDIT_USER_AGENT", "python:sentipulse:0.1")
    )
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"))
    x_bearer_token: str = field(default_factory=lambda: os.getenv("X_BEARER_TOKEN", ""))
    x_daily_read_budget: int = field(
        default_factory=lambda: int(os.getenv("X_DAILY_READ_BUDGET", "500"))
    )
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("SENTIPULSE_DB", "data/sentipulse.duckdb"))
    )

    @property
    def reddit_configured(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def x_configured(self) -> bool:
        return bool(self.x_bearer_token)


settings = Settings()

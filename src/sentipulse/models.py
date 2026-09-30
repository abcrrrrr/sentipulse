"""Core data types shared by sources, scorers and the store."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["reddit", "x"]
Label = Literal["positive", "negative", "neutral"]


class Post(BaseModel):
    """One unit of text from a social source (a submission or a comment)."""

    id: str
    source: Source
    ticker: str
    created_at: datetime
    author: str = ""
    text: str
    url: str = ""
    community: str = ""  # subreddit or X list/hashtag context
    upvotes: int = 0
    num_comments: int = 0
    is_comment: bool = False


class Score(BaseModel):
    """Sentiment score for one post from one scorer."""

    post_id: str
    scorer: str  # "vader" | "finbert" | "claude"
    label: Label
    # Signed score in [-1, 1]: p(positive) - p(negative) for model scorers.
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    scored_at: datetime = Field(default_factory=datetime.utcnow)

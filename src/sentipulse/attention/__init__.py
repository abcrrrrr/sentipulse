"""Attention series: how much an asset is being looked at or talked about, with no sentiment.

Each source returns a long-format DataFrame with ATTENTION_COLUMNS, stored in the
`attention` table keyed by (ticker, day, source, metric). Unlike `sources/`, these
yield daily numbers, not posts, so they need no Reddit access and no scoring.
"""

from __future__ import annotations

import pandas as pd

ATTENTION_COLUMNS = ["ticker", "day", "source", "metric", "value"]
USER_AGENT = "sentipulse/0.1 (https://github.com/abcrrrrr/sentipulse; personal research)"


def empty_attention() -> pd.DataFrame:
    return pd.DataFrame(columns=ATTENTION_COLUMNS)

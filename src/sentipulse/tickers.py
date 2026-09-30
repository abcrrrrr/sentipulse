"""Ticker / asset resolution and text matching.

The hard problem in social sentiment is not the model, it's attribution:
"$A" and "AI" match everything, and crypto is discussed by name far more
than by symbol. This module owns that logic so it can be tested in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Asset:
    ticker: str
    kind: str  # "stock" | "crypto"
    names: tuple[str, ...] = field(default_factory=tuple)  # full names / aliases
    price_symbol: str = ""  # yfinance symbol, e.g. "BTC-USD"

    @property
    def yf_symbol(self) -> str:
        return self.price_symbol or self.ticker


# Seed registry. Extend via `register()` or a YAML file later.
_REGISTRY: dict[str, Asset] = {}


def register(asset: Asset) -> Asset:
    _REGISTRY[asset.ticker.upper()] = asset
    return asset


for _a in [
    Asset("NVDA", "stock", ("nvidia",)),
    Asset("TSLA", "stock", ("tesla",)),
    Asset("AAPL", "stock", ("apple",)),
    Asset("AMD", "stock", ("advanced micro devices",)),
    Asset("PLTR", "stock", ("palantir",)),
    Asset("GME", "stock", ("gamestop",)),
    Asset("MSTR", "stock", ("microstrategy", "strategy inc")),
    Asset("COIN", "stock", ("coinbase",)),
    Asset("BTC", "crypto", ("bitcoin",), "BTC-USD"),
    Asset("ETH", "crypto", ("ethereum", "ether"), "ETH-USD"),
    Asset("SOL", "crypto", ("solana",), "SOL-USD"),
    Asset("DOGE", "crypto", ("dogecoin",), "DOGE-USD"),
    Asset("XRP", "crypto", ("ripple",), "XRP-USD"),
]:
    register(_a)


def resolve(symbol: str) -> Asset:
    """Return the registered Asset, or a bare stock Asset for unknown symbols."""
    key = symbol.upper().lstrip("$")
    if key in _REGISTRY:
        return _REGISTRY[key]
    return Asset(key, "stock")


def search_queries(asset: Asset) -> list[str]:
    """Queries to send to a source's search endpoint."""
    q = [f"${asset.ticker}", asset.ticker]
    q += list(asset.names)
    # Short tickers are ambiguous as bare words; require the cashtag form.
    if len(asset.ticker) <= 2:
        q = [f"${asset.ticker}"] + list(asset.names)
    return q


def mentions(text: str, asset: Asset) -> bool:
    """True if `text` plausibly discusses `asset`.

    Rules: cashtag always counts; bare ticker counts only for length >= 3
    (to avoid A, AI, GO, ...); names match case-insensitively as whole words.
    """
    t = text
    if re.search(rf"\${re.escape(asset.ticker)}\b", t, flags=re.IGNORECASE):
        return True
    if len(asset.ticker) >= 3 and re.search(rf"\b{re.escape(asset.ticker)}\b", t):
        return True
    for name in asset.names:
        if re.search(rf"\b{re.escape(name)}\b", t, flags=re.IGNORECASE):
            return True
    return False


CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")


def extract_cashtags(text: str) -> set[str]:
    return {m.upper() for m in CASHTAG_RE.findall(text)}

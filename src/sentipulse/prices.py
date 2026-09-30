"""Daily closes via yfinance so sentiment can be plotted against price."""

from __future__ import annotations

import pandas as pd

from .tickers import Asset


def fetch_prices(asset: Asset, days: int = 90) -> pd.DataFrame:
    import yfinance as yf

    hist = yf.Ticker(asset.yf_symbol).history(period=f"{max(days, 5)}d", auto_adjust=True)
    if hist.empty:
        return pd.DataFrame(columns=["ticker", "day", "close", "volume"])
    out = hist.reset_index()[["Date", "Close", "Volume"]]
    out.columns = ["day", "close", "volume"]
    out["day"] = pd.to_datetime(out["day"]).dt.date
    out["ticker"] = asset.ticker
    return out[["ticker", "day", "close", "volume"]]

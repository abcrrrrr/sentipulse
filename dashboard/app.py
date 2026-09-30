"""Streamlit dashboard: sentiment vs. price per ticker.

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from sentipulse.aggregate import add_signals
from sentipulse.charts import sentiment_price_figure
from sentipulse.store import Store

st.set_page_config(page_title="SentiPulse", layout="wide")
st.title("SentiPulse — retail sentiment vs. price")

store = Store()
tickers = store.tickers()
if not tickers:
    st.info("No data yet. Run `sentipulse run NVDA` first.")
    st.stop()

c1, c2, c3 = st.columns([2, 2, 1])
ticker = c1.selectbox("Ticker", tickers)
scorer = c2.selectbox("Scorer", ["finbert", "vader", "claude"])
days = c3.slider("Days", 14, 365, 90)

d = add_signals(store.daily(ticker, scorer, days=days))
if d.empty:
    st.warning(f"No daily rows for {ticker} / {scorer}.")
    st.stop()

latest = d.iloc[-1]
k1, k2, k3, k4 = st.columns(4)
prev = d.net_ratio.iloc[-2] if len(d) > 1 else float("nan")
k1.metric(
    "Net ratio (bull − bear)",
    f"{latest.net_ratio:+.2f}",
    f"{latest.net_ratio - prev:+.2f}" if pd.notna(prev) else None,
)
k2.metric("3-day smoothed", f"{latest.net_ma_short:+.2f}")
k3.metric("Posts today", int(latest.n_posts), f"z={latest.attention_z:+.1f}")
k4.metric("Close", f"{latest.close:,.2f}" if pd.notna(latest.close) else "—")

fig = sentiment_price_figure(d)
st.plotly_chart(fig, width="stretch")

st.subheader("Recent posts")
posts = store.scored_posts(ticker, scorer, days=3).sort_values("upvotes", ascending=False)
st.dataframe(
    posts[["created_at", "community", "label", "score", "upvotes", "text", "url"]].head(50),
    width="stretch",
    hide_index=True,
    column_config={
        "url": st.column_config.LinkColumn("link"),
        "text": st.column_config.TextColumn(width="large"),
    },
)

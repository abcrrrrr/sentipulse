"""Streamlit dashboard: sentiment vs. price per ticker.

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from sentipulse.aggregate import add_signals
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
k1.metric("Net ratio (bull − bear)", f"{latest.net_ratio:+.2f}", f"{latest.net_ratio - d.net_ratio.iloc[-2]:+.2f}" if len(d) > 1 else None)
k2.metric("3-day smoothed", f"{latest.net_ma_short:+.2f}")
k3.metric("Posts today", int(latest.n_posts), f"z={latest.attention_z:+.1f}")
k4.metric("Close", f"{latest.close:,.2f}" if latest.close == latest.close else "—")

fig = make_subplots(specs=[[{"secondary_y": True}]], rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.7, 0.3], vertical_spacing=0.05)
fig.add_trace(go.Scatter(x=d.day, y=d.net_ma_short, name="Net sentiment (3d)", line=dict(width=2)), row=1, col=1)
fig.add_trace(go.Scatter(x=d.day, y=d.net_ratio, name="Net sentiment (raw)", mode="markers", marker=dict(size=5, opacity=0.5)), row=1, col=1)
fig.add_trace(go.Scatter(x=d.day, y=d.close, name="Close", line=dict(dash="dot")), row=1, col=1, secondary_y=True)
fig.add_trace(go.Bar(x=d.day, y=d.n_posts, name="Posts", opacity=0.6), row=2, col=1)
fig.update_yaxes(title_text="net ratio", range=[-1, 1], row=1, col=1)
fig.update_yaxes(title_text="price", row=1, col=1, secondary_y=True)
fig.update_yaxes(title_text="posts", row=2, col=1)
fig.update_layout(height=600, legend=dict(orientation="h", y=1.08), margin=dict(t=40, b=20))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Recent posts")
posts = store.scored_posts(ticker, scorer, days=3).sort_values("upvotes", ascending=False)
st.dataframe(
    posts[["created_at", "community", "label", "score", "upvotes", "text", "url"]].head(50),
    use_container_width=True,
    hide_index=True,
    column_config={"url": st.column_config.LinkColumn("link"), "text": st.column_config.TextColumn(width="large")},
)

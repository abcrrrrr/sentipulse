"""Plotly figures for the dashboard. Kept out of dashboard/app.py so they can be tested.

Requires the `dashboard` extra (plotly).
"""

from __future__ import annotations

import pandas as pd


def sentiment_price_figure(d: pd.DataFrame):
    """Net sentiment + close on top (price on a secondary axis), post volume below.

    `d` is the output of `add_signals` joined with prices.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.05,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    fig.add_trace(
        go.Scatter(x=d.day, y=d.net_ma_short, name="Net sentiment (3d)", line={"width": 2}),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=d.day, y=d.net_ratio, name="Net sentiment (raw)", mode="markers",
            marker={"size": 5, "opacity": 0.5},
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=d.day, y=d.close, name="Close", line={"dash": "dot"}, connectgaps=True),
        row=1, col=1, secondary_y=True,
    )
    fig.add_trace(go.Bar(x=d.day, y=d.n_posts, name="Posts", opacity=0.6), row=2, col=1)
    fig.update_yaxes(title_text="net ratio", range=[-1, 1], row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="price", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="posts", row=2, col=1)
    fig.update_layout(height=600, legend={"orientation": "h", "y": 1.08}, margin={"t": 40, "b": 20})
    return fig

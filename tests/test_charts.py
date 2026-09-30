from datetime import date, timedelta

import pandas as pd
import pytest

pytest.importorskip("plotly")

from sentipulse.charts import sentiment_price_figure


def test_figure_builds_with_price_and_volume_panels():
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(5)]
    d = pd.DataFrame(
        {
            "day": days,
            "net_ratio": [0.1, 0.2, -0.1, 0.0, 0.3],
            "net_ma_short": [0.1, 0.15, 0.07, 0.03, 0.07],
            "n_posts": [10, 12, 8, 0, 20],
            "close": [100.0, 101.0, 99.0, None, 104.0],
        }
    )
    fig = sentiment_price_figure(d)
    assert {t.name for t in fig.data} == {
        "Net sentiment (3d)",
        "Net sentiment (raw)",
        "Close",
        "Posts",
    }

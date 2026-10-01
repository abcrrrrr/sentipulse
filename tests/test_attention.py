"""Attention sources (Wikipedia page views, ApeWisdom) against fake HTTP clients."""

from datetime import date, datetime, timezone

import pandas as pd
from typer.testing import CliRunner

from sentipulse.attention import apewisdom, wikipedia
from sentipulse.attention.apewisdom import ApeWisdom
from sentipulse.attention.wikipedia import WikipediaPageviews
from sentipulse.cli import app
from sentipulse.store import Store
from sentipulse.tickers import Asset, all_assets, resolve


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


# ---- Wikipedia ---------------------------------------------------------------


def _wiki_payload(views: dict[str, int]) -> dict:
    return {
        "items": [
            {"article": "Nvidia", "timestamp": f"{d.replace('-', '')}00", "views": v}
            for d, v in views.items()
        ]
    }


def test_every_registered_asset_has_a_wikipedia_title():
    assert all(a.wiki_title for a in all_assets())


def test_wikipedia_daily_views():
    calls = []

    def http_get(url, headers, timeout):
        calls.append((url, headers))
        return _Resp(200, _wiki_payload({"2026-09-28": 6000, "2026-09-29": 6500}))

    src = WikipediaPageviews(http_get=http_get)
    df = src.fetch(resolve("NVDA"), days=2, today=date(2026, 9, 30))

    assert list(df.columns) == ["ticker", "day", "source", "metric", "value"]
    assert list(df.day) == [date(2026, 9, 28), date(2026, 9, 29)]
    assert list(df.value) == [6000, 6500]
    assert set(df.source) == {"wikipedia"} and set(df.metric) == {"views"}
    url, headers = calls[0]
    # Ends yesterday (today is incomplete); Wikimedia requires a descriptive User-Agent.
    assert url.endswith("/user/Nvidia/daily/20260928/20260929")
    assert "sentipulse" in headers["User-Agent"]


def test_wikipedia_title_is_url_encoded():
    calls = []

    def http_get(url, headers, timeout):
        calls.append(url)
        return _Resp(404)

    df = WikipediaPageviews(http_get=http_get).fetch(resolve("TSLA"), days=1)
    assert "/Tesla%2C_Inc./daily/" in calls[0]
    assert df.empty  # 404 = no data, not a crash


def test_wikipedia_skips_assets_without_title():
    def http_get(url, headers, timeout):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    df = WikipediaPageviews(http_get=http_get).fetch(Asset("XYZ", "stock"), days=5)
    assert df.empty


# ---- ApeWisdom ---------------------------------------------------------------


def _ape_page(page: int, pages: int, rows: list[tuple[str, int, int, int]]) -> dict:
    return {
        "count": 1000,
        "pages": pages,
        "current_page": page,
        "results": [
            {"rank": r, "ticker": t, "name": t, "mentions": m, "upvotes": u}
            for t, r, m, u in rows
        ],
    }


def _ape_server(pages: dict[str, list[dict]]):
    calls = []

    def http_get(url, headers, timeout):
        calls.append(url)
        filt, page = url.rstrip("/").split("/filter/")[1].split("/page/")
        return _Resp(200, pages[filt][int(page) - 1])

    return http_get, calls


def test_apewisdom_finds_ticker_and_caches_listing():
    stocks = [
        _ape_page(1, 2, [("MU", 1, 1259, 7019), ("NVDA", 4, 86, 311)]),
        _ape_page(2, 2, [("PLTR", 120, 5, 12)]),
    ]
    http_get, calls = _ape_server({"all-stocks": stocks})
    src = ApeWisdom(http_get=http_get)
    snap = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)

    nvda = src.fetch(resolve("NVDA"), now=snap)
    pltr = src.fetch(resolve("PLTR"), now=snap)

    got = nvda.set_index("metric").value
    assert (got["mentions"], got["upvotes"], got["rank"]) == (86, 311, 4)
    assert set(nvda.day) == {date(2026, 10, 1)}
    assert pltr.set_index("metric").value["mentions"] == 5
    assert len(calls) == 2  # both pages fetched once, shared by both tickers


def test_apewisdom_unlisted_ticker_counts_as_zero_mentions():
    http_get, _ = _ape_server({"all-stocks": [_ape_page(1, 1, [("MU", 1, 1259, 7019)])]})
    df = ApeWisdom(http_get=http_get).fetch(resolve("GME"))
    got = df.set_index("metric").value
    assert (got["mentions"], got["upvotes"]) == (0, 0)
    assert "rank" not in got


def test_apewisdom_uses_crypto_filter_for_crypto():
    # ApeWisdom suffixes crypto tickers with ".X".
    http_get, calls = _ape_server({"all-crypto": [_ape_page(1, 1, [("BTC.X", 1, 300, 900)])]})
    df = ApeWisdom(http_get=http_get).fetch(resolve("BTC"))
    assert "/filter/all-crypto/page/1" in calls[0]
    assert df.set_index("metric").value["mentions"] == 300


def test_apewisdom_failure_records_nothing():
    def http_get(url, headers, timeout):
        return _Resp(503)

    # A failed listing must not be mistaken for "zero mentions".
    assert ApeWisdom(http_get=http_get).fetch(resolve("NVDA")).empty


# ---- store + CLI -------------------------------------------------------------


def test_store_attention_upsert_is_idempotent(tmp_path):
    store = Store(tmp_path / "t.duckdb")
    df = pd.DataFrame(
        {
            "ticker": "NVDA",
            "day": [date(2026, 9, 28), date(2026, 9, 29)],
            "source": "wikipedia",
            "metric": "views",
            "value": [6000.0, 6500.0],
        }
    )
    assert store.upsert_attention(df) == 2
    store.upsert_attention(df.assign(value=[1.0, 2.0]))
    out = store.attention("NVDA", days=None)
    assert list(out.value) == [1.0, 2.0]


def test_attention_cli(tmp_path, monkeypatch):
    def wiki_get(url, headers, timeout):
        return _Resp(200, _wiki_payload({"2026-09-28": 6000, "2026-09-29": 6500}))

    ape_get, _ = _ape_server({"all-stocks": [_ape_page(1, 1, [("NVDA", 4, 86, 311)])]})
    monkeypatch.setattr(wikipedia, "_default_get", wiki_get)
    monkeypatch.setattr(apewisdom, "_default_get", ape_get)

    db = tmp_path / "t.duckdb"
    result = CliRunner().invoke(app, ["attention", "NVDA", "--days", "2", "--db", str(db)])
    assert result.exit_code == 0, result.output

    store = Store(db)
    out = store.attention("NVDA", days=None)
    assert set(zip(out.source, out.metric)) >= {
        ("wikipedia", "views"),
        ("apewisdom", "mentions"),
    }


def test_run_without_reddit_keys_still_collects_attention(tmp_path, monkeypatch):
    from sentipulse.config import settings

    monkeypatch.setattr(settings, "reddit_client_id", "")
    monkeypatch.setattr(
        wikipedia, "_default_get",
        lambda url, headers, timeout: _Resp(200, _wiki_payload({"2026-09-29": 6500})),
    )
    ape_get, _ = _ape_server({"all-stocks": [_ape_page(1, 1, [("NVDA", 4, 86, 311)])]})
    monkeypatch.setattr(apewisdom, "_default_get", ape_get)

    db = tmp_path / "t.duckdb"
    result = CliRunner().invoke(app, ["run", "NVDA", "--no-with-prices", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert not Store(db).attention("NVDA", days=None).empty

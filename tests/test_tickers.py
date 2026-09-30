from sentipulse.tickers import extract_cashtags, mentions, resolve, search_queries


def test_resolve_known_and_unknown():
    assert resolve("btc").kind == "crypto"
    assert resolve("$BTC").yf_symbol == "BTC-USD"
    assert resolve("XYZ").kind == "stock"


def test_mentions_cashtag_and_name():
    nvda = resolve("NVDA")
    assert mentions("loading $nvda calls", nvda)
    assert mentions("Nvidia earnings tonight", nvda)
    assert mentions("NVDA to the moon", nvda)
    assert not mentions("I like apples", nvda)


def test_short_tickers_need_cashtag():
    a = resolve("A")
    assert not mentions("A great day for stocks", a)
    assert mentions("bought $A today", a)
    assert search_queries(a)[0] == "$A"


def test_extract_cashtags():
    assert extract_cashtags("$NVDA and $amd vs $spy") == {"NVDA", "AMD", "SPY"}

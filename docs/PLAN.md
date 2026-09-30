# Social Sentiment Pipeline — Plan

*Reddit (+ optional X) sentiment time series for a stock or crypto asset. September 2026; source-risk section updated 30 September 2026.*

## Goal

For any ticker (NVDA, BTC, …), produce a daily series of retail sentiment and attention that can be charted against price and later tested as a signal. Scope for v1 is deliberately narrow: one free source, one local model, one file database, one dashboard.

## Decisions taken

Reddit only for v1, but with access treated as a risk rather than a given (see *Data source risk* below). Reddit's Data API is free for non-commercial use within 100 requests/minute per OAuth client, which is far more than a daily collector needs, but since November 2025 new access requires manual approval. X has no free read tier any more: since February 2026 new developers are on pay-per-use credits at roughly $0.005 per post read (2M reads/month cap, no streaming, 7-day search window only); the legacy Basic ($200/mo) and Pro ($5,000/mo) tiers are closed to new sign-ups. X is therefore an optional module gated behind a bearer token and a daily read budget, to be turned on only after the Reddit pipeline has proven useful.

Scoring is FinBERT on every post plus a Claude-scored sample. FinBERT (ProsusAI/finbert) runs locally on CPU at tens of posts per second with no per-call cost, but it was trained on analyst-style financial text and misreads retail sarcasm and memes. Claude scores a random sample of 25–50 posts per ticker per day (a few cents) to give a calibration check against FinBERT and a sarcasm-aware label. VADER with a finance slang lexicon is the zero-dependency baseline used in tests.

Output is a daily time series in DuckDB with a Streamlit dashboard. DuckDB is a single file, pandas-native, and fast enough for years of daily data; the `store.py` module is the only thing to rewrite if this later moves to Snowflake or Databricks.

## Architecture

```
sources/reddit.py ─┐
sources/x.py (opt) ─┼─► Post ─► store.posts ─► scoring/{finbert,claude,vader} ─► store.scores
sources/jsonl.py ──┘                                                                │
                                                                                     ▼
prices.py (yfinance) ─► store.prices ──────────────► aggregate.py ─► store.daily ─► dashboard
```

Tables: `posts` (raw text, upvotes, community), `scores` keyed by (post_id, scorer) so several scorers coexist, `daily` keyed by (ticker, day, scorer), `prices`.

Daily metrics: `n_posts`, `mean_score`, `weighted_score` (weights = log1p(upvotes)), `bull_ratio`, `bear_ratio`, `net_ratio` (= bull − bear; usually the most stable single number). The dashboard adds 3- and 14-day rolling means and `attention_z`, post volume relative to its 14-day baseline. Attention spikes tend to be more informative than sign, so `n_posts` is always stored.

## The hard part is attribution, not the model

Ticker matching is the main source of garbage. Rules in `tickers.py`: a `$cashtag` always matches; a bare ticker matches only when it is three or more characters (avoids A, AI, GO, IT); full names match as whole words, case-insensitive; crypto is discussed by name far more than by symbol, so names are mandatory in the registry. Comments inherit the topic of the thread they belong to and are not required to mention the ticker explicitly.

## Data source risk

*Status as of 30 September 2026.* Reddit access is no longer self-service, and the project must not depend on a single gatekeeper.

- **Approval gate (since November 2025).** Under Reddit's Responsible Builder Policy, every new OAuth client needs manual approval before it can call the Data API. You file a request (developer / researcher / moderator) and wait. Reported waits run from days to weeks, some requests get no answer, and small personal projects are the most-rejected category. Approved credentials keep working.
- **Planned wind-down (announced 5 August 2026).** Reddit said it will gradually restrict the public Data API and require third-party apps to move to its Developer Platform (Devvit). There is no cut-off date, and Reddit said nothing changes in 2026.
- **Devvit is not a substitute for this project.** Devvit apps are TypeScript only (no Python on the roadmap), run inside Reddit, and are installed per subreddit by its moderators. Calls to external servers need per-domain review. The platform is built for tools that live inside Reddit, not for exporting text to an external model and database.
- **What this means.**
  - Apply for Data API access now, because approved credentials are the ones stated to keep working.
  - Keep everything downstream of `BaseSource` source-agnostic, which it already is.
  - Line up at least one source that needs nobody's approval.

### Alternative sources considered

| Source | Signal | Access (Sept 2026) | Cost | Verdict |
|---|---|---|---|---|
| **Bluesky** (`app.bsky.feed.searchPosts`) | Retail posts, cashtags used informally | Open. A free account and app password are enough; search needs authentication since Aug 2026. Points-based rate limit (~5,000 points/hour). | $0 | **Primary fallback.** Smaller finance crowd than Reddit; volume per ticker needs measuring. |
| **Wikipedia Pageviews API** | Attention only (no sentiment) | Open, no key | $0 | **Add.** Cheap, independent attention series to set against `n_posts`; published work links page-view spikes to returns. |
| **Finnhub / Marketaux news** | News headlines, ticker-tagged | Free API key. Finnhub 60 calls/min; Marketaux 100 calls/day | $0 on free tiers | **Add as a separate "news" series.** FinBERT was trained on exactly this kind of text, so it is the best-scored source we have. |
| Alpha Vantage news sentiment | Pre-scored news | Free key, 25 calls/day | $0 | Too tight for 10 tickers daily; useful as a cross-check only. |
| X | Retail posts | Pay-per-use, no approval wait | ~$0.005/read | Already built (Phase 5). The only large retail source that can be switched on today without waiting for approval. |
| Stocktwits | Retail posts with self-labelled bull/bear tags | **Closed to new API registrations** (review in progress) | n/a | Ideal data, but not available. Re-check periodically. |
| Google Trends | Search attention | Official API is an application-gated alpha | n/a | Skip. Unofficial scrapers break often and sit in a terms-of-service grey area. |

Scraping (Reddit's unauthenticated `.json` endpoints, Stocktwits' web endpoints, or third-party scraper services) is out of scope: it breaks without warning and conflicts with the platforms' terms.

## Phased build

Phase 1 (done): scaffold with Reddit collector, three scorers, DuckDB store, CLI, dashboard, offline tests on a bundled sample file.

Phase 1.5 (done): fixes from code review (per-ticker post keys, calendar-day attention, persistent X budget, structured Claude output, dashboard crash) and the `sentipulse agreement` command for comparing FinBERT with Claude.

Phase 2, first two weeks of real data: **file the Reddit Data API access request on day one**, because it can take weeks. Once approved, create a Reddit script app, run `sentipulse run` daily for five to ten tickers, and backfill by running with `--days 30` (Reddit search's time filter is coarse, so backfill depth is limited to about a month). Compare FinBERT and Claude labels on the sample with `sentipulse agreement`; tune the neutral band in `label_from_score`; decide whether comment expansion adds signal or noise.

Phase 2b, source independence (can start while the Reddit request is pending): a Bluesky source (`sources/bluesky.py`, app-password auth), a Wikipedia page-view attention series, and a news source (Finnhub or Marketaux) stored as its own `source` so news and social sentiment are never mixed in one number. Success criterion: at least one social source producing ≥20 posts/day for most tickers without Reddit.

Phase 3, hygiene: bot and spam filtering (account age, repeated text across threads, karma floor), crosspost de-duplication, and a per-subreddit weight so r/wallstreetbets does not swamp r/investing.

Phase 4, ops: cron or GitHub Actions schedule, alert when `attention_z > 2` or `net_ma_short` flips sign, and a weekly Claude-written summary of *why* sentiment moved.

Phase 5, optional X module: enable with a bearer token and a small budget (500 reads/day ≈ $2.50/day); measure whether X adds anything beyond Reddit before spending more.

Phase 6, research: lead/lag of `net_ratio` and `attention_z` versus next-day and next-week returns, per ticker and pooled; export the daily table to Snowflake for joining with other data.

## Cost envelope

Reddit $0 once approved. Bluesky, Wikipedia page views and the free news tiers are $0. FinBERT $0 (one-time ~440 MB download). Claude sample on Sonnet 5.5 ($2 / $10 per million input / output tokens): about 40 posts × 10 tickers × 30 days at ~300 tokens each ≈ 3.6M input tokens/month, roughly $10–20/month including output. yfinance $0. X, if enabled, is the only meaningful line item and is capped by `X_DAILY_READ_BUDGET`.

## Why build it in Claude Code

This is a good fit for Claude Code: it is a multi-file Python project that needs a terminal for installing packages, running tests, running the collector, and iterating on real data. `CLAUDE.md` in the repo root tells Claude Code the layout, the offline-testing rule, and the roadmap, so each new session starts with the same context. Use Cowork (this session) for planning, research, and reviewing results; use Claude Code for the code changes and daily iteration.

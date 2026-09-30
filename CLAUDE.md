# SentiPulse — guidance for Claude Code

Retail sentiment time series for stocks/crypto. Reddit is the v1 source; X is an
optional, budget-capped module. Read `docs/PLAN.md` for the roadmap and the
reasoning behind design choices before proposing architecture changes.

## Layout
- `src/sentipulse/sources/` — collectors. Each yields `Post` objects. `jsonl.py` is the
  offline/test source; `reddit.py` (PRAW) is live; `x.py` is optional pay-per-use.
- `src/sentipulse/tickers.py` — asset registry + mention matching. **Most false positives
  come from here, not from the model.** Short tickers require a `$cashtag`.
- `src/sentipulse/scoring/` — `vader` (baseline, no download), `finbert` (default in
  prod), `claude` (QC sample). All return `Score` with a signed score in [-1, 1].
- `src/sentipulse/store.py` — DuckDB, four tables: posts, scores, daily, prices.
  Scores are keyed by (post_id, scorer) so multiple scorers coexist.
- `src/sentipulse/aggregate.py` — daily roll-up + rolling signals.
- `src/sentipulse/agreement.py` — scorer-vs-scorer calibration (kappa, band sweep).
- `src/sentipulse/cli.py` — Typer commands; `run` is the daily job.
- `dashboard/app.py` — Streamlit.

## Commands
```
pip install -e ".[all]"            # or ".[dev]" for tests only
pytest -q                          # offline, ~1s, no network or model download
sentipulse run NVDA BTC --claude-sample 40
sentipulse collect NVDA --jsonl data/sample_nvda.jsonl --days 30   # offline replay
sentipulse agreement NVDA          # finbert vs claude: kappa, confusion, neutral-band sweep
streamlit run dashboard/app.py
```

## Conventions
- Tests must stay offline: use `JsonlSource` + `vader`, or inject a fake client (`RedditSource(reddit=...)`,
  `XSource(..., http_get=...)`, `ClaudeScorer(client=...)`); never hit Reddit/X/Anthropic/yfinance.
- Never add a scorer that mutates `posts`; scores are append-only per (post_id, scorer).
- New sources implement `BaseSource.fetch(asset, days, limit)` and set `Post.source`.
- Keep `.env` out of git. Secrets come only from `config.settings`.
- X reads cost money: any change to `sources/x.py` must preserve the daily budget guard.
- Prefer `ruff` clean, line length 100.

## Roadmap (see docs/PLAN.md)
1. ✅ Scaffold: Reddit → VADER/FinBERT → DuckDB → Streamlit
2. Backfill ~30 days per ticker (Reddit search depth limit); compare FinBERT vs Claude sample; tune `label_from_score` bands
2b. Source independence while Reddit access is pending: Bluesky source, Wikipedia page-view attention,
   news (Finnhub/Marketaux) as a separate `source`. Reddit access is approval-gated and being wound down;
   Devvit is not a substitute (TypeScript, in-Reddit only). See docs/PLAN.md "Data source risk".
3. Bot/spam filter (author age, repeated text, karma) and de-dup of crossposts
4. Scheduler (cron / GitHub Actions) + alerting on `attention_z > 2`
5. Optional X module behind `X_BEARER_TOKEN`
6. Research: lead/lag of `net_ratio` and `attention_z` vs next-day returns; export to Snowflake

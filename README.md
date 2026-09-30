# SentiPulse

Daily retail-sentiment time series for any stock or crypto asset, built from Reddit
(X optional), scored locally with FinBERT and spot-checked with Claude, stored in DuckDB,
and charted against price in Streamlit.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env            # add Reddit client id/secret (free "script" app)
pytest -q                       # offline sanity check

sentipulse run NVDA BTC         # collect → FinBERT → aggregate → prices
sentipulse report NVDA
streamlit run dashboard/app.py
```

No Reddit keys yet? Replay the bundled sample:

```bash
sentipulse collect NVDA --jsonl data/sample_nvda.jsonl --days 30 --limit 1000
sentipulse score NVDA --scorer vader
sentipulse aggregate NVDA --scorer vader
sentipulse report NVDA --scorer vader
```

## What you get

`daily` table per ticker/day/scorer: `n_posts`, `mean_score`, `weighted_score`
(log-upvote weighted), `bull_ratio`, `bear_ratio`, `net_ratio`. The dashboard adds
3/14-day smoothing and an attention z-score (post volume vs. its 14-day baseline).

## Data sources and cost

| Source | Access | Cost | Notes |
|---|---|---|---|
| Reddit | Free "script" app, OAuth | $0 for personal/research use, 100 req/min | Default. Six stock + six crypto subs. |
| X | Pay-per-use credits | ~$0.005 per post read; no free read tier since Feb 2026 | Optional. `X_DAILY_READ_BUDGET` caps spend. |
| Anthropic | API key | Pennies/day at 25-50 posts sampled per ticker | Quality check + sarcasm-aware labels. |
| Yahoo Finance | yfinance | $0 | Daily closes for overlay. |

## Scheduling

`scripts/daily.sh` runs the job for a list of tickers. Cron example (7pm ET, after close):

```
0 23 * * * cd /path/to/sentipulse && ./scripts/daily.sh >> logs/daily.log 2>&1
```

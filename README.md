# SentiPulse

Daily retail-sentiment time series for any stock or crypto asset, built from Reddit
(X optional), scored locally with FinBERT and spot-checked with Claude, stored in DuckDB,
and charted against price in Streamlit.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all]"
cp .env.example .env            # add Reddit client id/secret (needs approved API access)
pytest -q                       # offline sanity check

sentipulse run NVDA BTC         # collect → FinBERT → aggregate → prices
sentipulse report NVDA
streamlit run dashboard/app.py
```

No Reddit keys? (Reddit rejected ours; see docs/PLAN.md.) Attention data needs no keys at all:

```bash
sentipulse attention NVDA TSLA BTC ETH --days 90   # Wikipedia page views + ApeWisdom mentions
streamlit run dashboard/app.py
```

To try the sentiment side offline, replay the bundled sample:

```bash
sentipulse collect NVDA --jsonl data/sample_nvda.jsonl --days 30 --limit 1000
sentipulse score NVDA --scorer vader
sentipulse aggregate NVDA --scorer vader
sentipulse report NVDA --scorer vader
```

## Calibrating FinBERT against Claude

Once a few days of `--claude-sample` scores exist:

```bash
sentipulse agreement NVDA --a finbert --b claude --days 30
```

This prints the match rate, Cohen's kappa, score correlation and a confusion matrix
for the posts both scorers labelled. It then sweeps the neutral band that FinBERT's
signed score is labelled with, and prints the posts where the two disagree most.

## What you get

`daily` table per ticker/day/scorer: `n_posts`, `mean_score`, `weighted_score`
(log-upvote weighted), `bull_ratio`, `bear_ratio`, `net_ratio`. The dashboard adds
3/14-day smoothing and an attention z-score (post volume vs. its 14-day baseline).

## Data sources and cost

| Source | Access | Cost | Notes |
|---|---|---|---|
| Reddit | OAuth "script" app, **after manual approval** | $0 for non-commercial use, 100 req/min | Default. New access needs approval (weeks), and Reddit plans to wind down the Data API. See docs/PLAN.md, *Data source risk*. |
| X | Pay-per-use credits | ~$0.005 per post read; no free read tier since Feb 2026 | Optional. `X_DAILY_READ_BUDGET` caps spend. |
| Wikipedia page views | Public REST API | $0, no key | Attention; years of history, so it backfills. |
| ApeWisdom | Public REST API | $0, no key | Reddit/4chan mention counts (no text); daily snapshot. |
| Anthropic | API key | Pennies/day at 25-50 posts sampled per ticker | Quality check + sarcasm-aware labels. |
| Yahoo Finance | yfinance | $0 | Daily closes for overlay. |

## Scheduling

`scripts/daily.sh` runs the job for a list of tickers. Cron example (7pm ET, after close):

```
0 23 * * * cd /path/to/sentipulse && ./scripts/daily.sh >> logs/daily.log 2>&1
```

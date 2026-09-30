"""Command-line entry point.

    sentipulse collect NVDA --days 1
    sentipulse score NVDA --scorer finbert
    sentipulse score NVDA --scorer claude --sample 50
    sentipulse aggregate NVDA
    sentipulse prices NVDA
    sentipulse report NVDA
    sentipulse agreement NVDA      # finbert vs claude on the shared sample
    sentipulse run NVDA BTC        # collect → score → aggregate → prices, all in one
"""

from __future__ import annotations

import logging
import random

import typer

from .aggregate import add_signals, daily_aggregate
from .models import Post
from .scoring import get_scorer
from .store import Store
from .tickers import resolve

app = typer.Typer(no_args_is_help=True, add_completion=False)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentipulse")


def _source(name: str, jsonl: str | None, store: Store):
    if jsonl:
        from .sources import JsonlSource

        return JsonlSource(jsonl)
    if name == "reddit":
        from .sources import RedditSource

        return RedditSource()
    if name == "x":
        from .sources import XSource

        return XSource(store)
    raise typer.BadParameter(f"unknown source {name}")


@app.command()
def collect(
    tickers: list[str],
    days: int = typer.Option(1, help="Look-back window in days"),
    limit: int = typer.Option(300, help="Max posts per ticker per source"),
    source: str = typer.Option("reddit", help="reddit | x"),
    jsonl: str = typer.Option(None, help="Read from a JSONL file instead of the live API"),
    db: str = typer.Option(None, help="DuckDB path (default from .env)"),
):
    """Fetch posts mentioning each ticker and store them."""
    store = Store(db)
    src = _source(source, jsonl, store)
    for t in tickers:
        asset = resolve(t)
        posts: list[Post] = list(src.fetch(asset, days=days, limit=limit))
        n = store.upsert_posts(posts)
        log.info("%s: stored %d posts from %s", asset.ticker, n, src.name)
    store.close()


@app.command()
def score(
    tickers: list[str],
    scorer: str = typer.Option("finbert", help="vader | finbert | claude"),
    sample: int = typer.Option(0, help="Score only a random sample of N unscored posts (0 = all)"),
    seed: int = typer.Option(42),
    db: str = typer.Option(None),
):
    """Score stored posts that this scorer has not seen yet."""
    store = Store(db)
    sc = get_scorer(scorer)
    for t in tickers:
        asset = resolve(t)
        posts = store.unscored_posts(asset.ticker, sc.name)
        if sample and len(posts) > sample:
            random.Random(seed).shuffle(posts)
            posts = posts[:sample]
        if not posts:
            log.info("%s: nothing to score for %s", asset.ticker, sc.name)
            continue
        n = store.upsert_scores(sc.score_batch(posts))
        log.info("%s: scored %d posts with %s", asset.ticker, n, sc.name)
    store.close()


@app.command()
def aggregate(
    tickers: list[str],
    scorer: str = typer.Option("finbert"),
    days: int = typer.Option(90),
    db: str = typer.Option(None),
):
    """Rebuild the daily time series from per-post scores."""
    store = Store(db)
    for t in tickers:
        asset = resolve(t)
        scored = store.scored_posts(asset.ticker, scorer, days=days)
        daily = daily_aggregate(scored, scorer)
        n = store.upsert_daily(daily)
        log.info("%s: wrote %d daily rows (%s)", asset.ticker, n, scorer)
    store.close()


@app.command()
def prices(tickers: list[str], days: int = typer.Option(90), db: str = typer.Option(None)):
    """Pull daily closes from Yahoo Finance for overlay charts."""
    from .prices import fetch_prices

    store = Store(db)
    for t in tickers:
        asset = resolve(t)
        n = store.upsert_prices(fetch_prices(asset, days=days))
        log.info("%s: stored %d price rows", asset.ticker, n)
    store.close()


@app.command()
def report(
    ticker: str,
    scorer: str = typer.Option("finbert"),
    days: int = typer.Option(14),
    db: str = typer.Option(None),
):
    """Print the recent daily series with smoothed signals."""
    import pandas as pd

    store = Store(db)
    asset = resolve(ticker)
    d = add_signals(store.daily(asset.ticker, scorer, days=days))
    store.close()
    if d.empty:
        typer.echo(f"No daily data for {asset.ticker} / {scorer}. Run collect -> score -> aggregate.")
        raise typer.Exit(1)
    cols = ["day", "n_posts", "net_ratio", "net_ma_short", "weighted_score", "attention_z", "close"]
    with pd.option_context("display.width", 140, "display.float_format", "{:.3f}".format):
        typer.echo(d[cols].to_string(index=False))


@app.command()
def agreement(
    ticker: str,
    a: str = typer.Option("finbert", help="Scorer that labels every post"),
    b: str = typer.Option("claude", help="Reference scorer (usually the Claude sample)"),
    days: int = typer.Option(30),
    show: int = typer.Option(5, help="How many top disagreements to print"),
    db: str = typer.Option(None),
):
    """Compare two scorers on the posts both have scored, and suggest a neutral band."""
    import pandas as pd

    from .agreement import agreement_stats, sweep_band, top_disagreements

    store = Store(db)
    asset = resolve(ticker)
    paired = store.paired_scores(asset.ticker, a, b, days=days)
    store.close()
    stats = agreement_stats(paired)
    if stats.n == 0:
        typer.echo(f"No posts scored by both {a} and {b} for {asset.ticker}.")
        raise typer.Exit(1)

    typer.echo(
        f"{asset.ticker}: {a} vs {b}, n={stats.n}  match={stats.match_rate:.1%}  "
        f"kappa={stats.kappa:.2f}  score corr={stats.score_corr:.2f}"
    )
    typer.echo(f"\nConfusion (rows={a}, cols={b}):\n{stats.confusion.to_string()}")

    sweep = sweep_band(paired)
    best = sweep.loc[sweep.kappa.idxmax()]
    with pd.option_context("display.float_format", "{:.3f}".format):
        typer.echo(f"\nNeutral band sweep ({a} relabeled from its score):")
        typer.echo(sweep.to_string(index=False))
    typer.echo(f"Best band for agreement with {b}: {best.band:.2f} (kappa {best.kappa:.2f})")

    if show:
        typer.echo(f"\nTop {show} disagreements:")
        for r in top_disagreements(paired, show).itertuples():
            text = " ".join(r.text.split())[:140]
            typer.echo(f"  {a}={r.score_a:+.2f} {b}={r.score_b:+.2f}  {text}")


@app.command()
def run(
    tickers: list[str],
    days: int = typer.Option(1),
    scorer: str = typer.Option("finbert"),
    claude_sample: int = typer.Option(0, help="Also score N posts with Claude for QC"),
    with_prices: bool = typer.Option(True),
    db: str = typer.Option(None),
):
    """Daily job: collect → score → (claude sample) → aggregate → prices."""
    collect(tickers, days=days, limit=300, source="reddit", jsonl=None, db=db)
    score(tickers, scorer=scorer, sample=0, seed=42, db=db)
    if claude_sample:
        score(tickers, scorer="claude", sample=claude_sample, seed=42, db=db)
        aggregate(tickers, scorer="claude", days=90, db=db)
    aggregate(tickers, scorer=scorer, days=90, db=db)
    if with_prices:
        prices(tickers, days=90, db=db)


if __name__ == "__main__":
    app()

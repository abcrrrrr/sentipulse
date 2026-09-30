#!/usr/bin/env bash
# Daily collection job. Edit TICKERS; run from repo root with the venv active.
set -euo pipefail
TICKERS="${TICKERS:-NVDA TSLA PLTR BTC ETH SOL}"
sentipulse run $TICKERS --days 1 --scorer finbert --claude-sample 40

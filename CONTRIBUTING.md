# Contributing

Thanks for your interest in improving this project. Contributions that make the tools more accurate, clearer, or easier to run are welcome.

## Ground rules

1. **No investment-advice framing.** Docs and UI text should stay educational/operational. Keep [DISCLAIMER.md](DISCLAIMER.md) intact.
2. **Shared math stays shared.** Indicator and nine-rules changes go in `ta_indicators.py`, not copy-pasted into only one CLI.
3. **Do not commit secrets** (API keys, private watchlists with account data, personal logs).
4. **Do not commit large generated data** by default (`*.json` history, logs)—see `.gitignore`.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install yfinance pandas numpy lxml
```

Optional: point data at a test directory:

```bash
export MARKET_BREADTH_DIR="/tmp/marketbreadth-test"
mkdir -p "$MARKET_BREADTH_DIR"
```

## Making changes

1. Fork / branch from the default branch.
2. Prefer small, focused commits.
3. Update the relevant README(s) and [CHANGELOG.md](CHANGELOG.md) when behavior changes.
4. Run a minimal validation path (see below).

## Validation checklist

```bash
python3 -m py_compile ta_indicators.py stock_screener.py OvtLyrMimic.py market_breadth_collector.py
bash -n getTodaysStockScreenerData.sh

# After a successful breadth collect:
python3 market_breadth_collector.py
python3 stock_screener.py --sector "Utilities" --top-stocks 5
python3 stock_screener.py --watchlist
python3 OvtLyrMimic.py --briefing
```

Confirm that `rules_passed` for the same ticker is consistent between screener JSON and OvtLyr.

## Pull request tips

- Describe **what** changed and **why** (accuracy, performance, docs).
- Note any new dependencies or cron implications.
- Avoid drive-by reformatting of unrelated files.

## Code of conduct (lightweight)

Be respectful. Assume good intent. Harassment or spam will be rejected.

## License

Contributions are accepted under the same [CC0 1.0](LICENSE) dedication as the rest of the project unless you state otherwise before merge.

# Contributing

Thanks for your interest in improving this project. Contributions that make the tools more accurate, clearer, or easier to run are welcome.

## Ground rules

1. **No investment-advice framing.** Docs and UI text should stay educational/operational. Keep [DISCLAIMER.md](DISCLAIMER.md) intact.
2. **Shared math stays shared.** Indicator and nine-rules changes go in `ta_indicators.py`, not copy-pasted into only one CLI.
3. **Do not commit secrets** (API keys, private watchlists with account data, personal logs). Prefer a sample/placeholder path in `getStockScreenerData.bat` if you share a personal `LOG=` location.
4. **Do not commit large generated data** by default (`*.json` history, logs)—see `.gitignore`.
5. **ASCII-safe runtime output.** User-facing `print()` / CLI help that may run under Windows cp1252 should avoid characters above U+00FF (em dash `—`, arrows `→`, √, σ, ≈, checkmarks, etc.). Use `-`, `->`, `sqrt()`, `1-sigma`, `x`, `PASS`/`FAIL`. Markdown docs may still use Unicode.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install yfinance pandas numpy lxml
```

Optional: point data at a test directory:

```bash
export MARKET_BREADTH_DIR="/tmp/marketbreadth-test"
mkdir -p "$MARKET_BREADTH_DIR"
```

On Windows PowerShell:

```powershell
$env:MARKET_BREADTH_DIR = "C:\Temp\marketbreadth-test"
```

## Making changes

1. Fork / branch from the default branch.
2. Prefer small, focused commits.
3. Update the relevant README(s) and [CHANGELOG.md](CHANGELOG.md) when behavior changes.
4. If you change the daily pipeline, keep **`getTodaysStockScreenerData.sh` and `getStockScreenerData.bat` in step order** (or document intentional divergence).
5. Run a minimal validation path (see below).

## Validation checklist

```bash
python3 -m py_compile ta_indicators.py stock_screener.py nine_rules_gate.py nine_rules_independent.py market_breadth_collector.py
bash -n getTodaysStockScreenerData.sh

# After a successful breadth collect:
python3 market_breadth_collector.py
python3 stock_screener.py --sector "Utilities" --top-stocks 5
python3 stock_screener.py --watchlist
python3 nine_rules_gate.py --briefing
```

Confirm that `rules_passed` for the same ticker is consistent between screener JSON and nine-rules gate.

On Windows, also confirm that redirecting a briefing to a file does not raise `UnicodeEncodeError`:

```bat
python stock_screener.py --opportunities > nul
python nine_rules_gate.py --briefing > nul
```

## Pull request tips

- Describe **what** changed and **why** (accuracy, performance, docs, Windows encoding).
- Note any new dependencies or cron / Task Scheduler implications.
- Avoid drive-by reformatting of unrelated files.

## Code of conduct (lightweight)

Be respectful. Assume good intent. Harassment or spam will be rejected.

## License

Contributions are accepted under the same [CC0 1.0](LICENSE) dedication as the rest of the project unless you state otherwise before merge.

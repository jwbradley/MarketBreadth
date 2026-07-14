# Changelog

All notable changes to this project are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).  
Versions are informal tags for a personal/public toolkit (not necessarily PyPI releases).

---

## [2.0.0] — 2026-07-14

### Architecture (Option C)

- Added **`ta_indicators.py`**: shared Wilder RSI, EMA/MACD/ATR/BB, divergence, nine rules, and sector composite ranking.
- **`stock_screener.py`** and **`OvtLyrMimic.py`** both consume the shared module so scores and rules stay aligned.

### Accuracy

- Sector selection uses a **multi-metric composite** (not single-day A/D alone).
- Within-sector stock selection ranks by **relative strength + liquidity** (not CSV/alphabetical order).
- Default **$20M** average dollar-volume floor (`SCREENER_MIN_DOLLAR_VOL`).
- Nine-rules **Rule 3 / Rule 4** use real market and sector breadth (no longer hardcoded pass in the screener).
- Thesis-aware signals: **Momentum Buy**, **Reversal Watch**, **RS in Weak Sector**, etc.
- Watchlist export prefers top-sector names; weak-sector entries are filtered more tightly.

### Orchestration

- **`getTodaysStockScreenerData.sh`**: soft-fail per step, clearer daily report order, **`--opportunities`** section before full tables, OvtLyr as final gate.
- New CLI: `stock_screener.py --opportunities`.

### Documentation

- Expanded README suite, **BEST_PRACTICES.md**, **DISCLAIMER.md**, **CONTRIBUTING.md**, this changelog.

---

## [1.x] — 2026-06

### Added

- `market_breadth_collector.py` — S&P 500 and GICS sector breadth.
- `stock_screener.py` — technical scores for top/bottom sectors.
- `OvtLyrMimic.py` — nine-rules analysis (initially separate indicator math).
- Daily bash orchestrator and initial READMEs.

---

## Disclaimer

Changes improve engineering consistency and selection logic only. They do **not** guarantee trading profits. See [DISCLAIMER.md](DISCLAIMER.md).

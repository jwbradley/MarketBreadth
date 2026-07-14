# Changelog

All notable changes to this project are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).  
Versions are informal tags for a personal/public toolkit (not necessarily PyPI releases).

---

## [2.2.0] — 2026-07-14

### Renamed (no commercial brand references)

Removed former **OvtLyr / OVTLYR / Mimic*** names so the project does not imply affiliation with any commercial charting site. Functionality is unchanged; only identifiers, paths, and docs were rebranded.

| Before | After |
|--------|--------|
| `OvtLyrMimic.py` | `nine_rules_gate.py` |
| `OvtLyrMimic4.py` | `nine_rules_independent.py` |
| `README-OvtLyrMimic.md` | `README-nine_rules.md` |
| `ovtlyr_watchlist.json` | `nine_rules_watchlist.json` |
| `logs/MimicOVTLR-DailyOutput.log` | `logs/nine_rules_independent.log` |
| Result field `ovtlyr_signal` | `nine_rules_signal_label` |

Daily runners (`.sh` / `.bat`) call the new script names. Watchlist loaders still accept the **legacy** `ovtlyr_watchlist.json` filename if the new file is not present (temporary compatibility).

### Documentation

- README suite, BEST_PRACTICES, CONTRIBUTING, and this changelog updated for the new names.
- Explicit note: independent educational checklist; not affiliated with third-party commercial platforms.

---

## [2.1.1] — 2026-07-14

### Windows / encoding

- **ASCII-safe CLI text** in user-facing `print` paths for `stock_screener.py`, `nine_rules_gate.py`, and `nine_rules_independent.py`. Python 3.12 on Windows often uses **cp1252** for stdout; characters above U+00FF (e.g. em dash `—`, arrows `→`, √, σ, ≈, × in some contexts) raise `UnicodeEncodeError` when redirected to a log file or console.
- Replacements used in output: `->` / `-` for arrows and em dashes; `sqrt()` / `1-sigma` / `x` / `~` / `+/-` instead of √ / σ / × / ≈ / ± where those appeared in formula notes.

### Added

- **`getStockScreenerData.bat`**: Windows daily orchestrator aligned with the Linux shell pipeline (collect → screen → brief, including `--opportunities` and `nine_rules_independent.py`). Edit the `LOG=` path before first run; assumes `python` on `PATH` and scripts in the working directory (or your usual layout next to GoldenRatios tools).

### Documentation

- README, BEST_PRACTICES, and CONTRIBUTING note Linux vs Windows runners and the ASCII stdout convention.

### Notes / known differences

| | Linux (`getTodaysStockScreenerData.sh`) | Windows (`getStockScreenerData.bat`) |
|--|----------------------------------------|--------------------------------------|
| Soft-fail per step | Yes (`run_step` / `run_report`) | No (batch continues only if each `@python` is allowed to fail silently with `@`; check the log) |
| Venv | Activates `GoldenRatios/.venv` | Uses system / PATH `python` |
| Paths | Hardcoded under `~/myPrograms/KSI/` | Hardcoded `LOG=` OneDrive path in the sample bat—**edit for your machine** |
| Layout | Runs from KSI parent (MarketBreadth + GoldenRatios) | Expects you to run from a directory where the listed `.py` modules resolve |
| Exit code | Non-zero if any step failed | Batch does not aggregate failure count |

Markdown docs may still use Unicode for readability; **runtime CLI strings** should stay ASCII-safe so Windows logging does not crash.

---

## [2.1.0] — 2026-07-14

### Added

- **`nine_rules_independent.py`**: independent nine-rules re-score with layered universe (core book ∪ personal `tickers.txt` ∪ screener watchlist ∪ CLI). Optional overlap report vs funnel names. Uses shared `ta_indicators` when available.
- Daily pipeline step in **`getTodaysStockScreenerData.sh`**: runs v4 with `--union-watchlist --briefing`; full report → `logs/nine_rules_independent.log`.

---

## [2.0.0] — 2026-07-14

### Architecture (Option C)

- Added **`ta_indicators.py`**: shared Wilder RSI, EMA/MACD/ATR/BB, divergence, nine rules, and sector composite ranking.
- **`stock_screener.py`** and **`nine_rules_gate.py`** both consume the shared module so scores and rules stay aligned.

### Accuracy

- Sector selection uses a **multi-metric composite** (not single-day A/D alone).
- Within-sector stock selection ranks by **relative strength + liquidity** (not CSV/alphabetical order).
- Default **$20M** average dollar-volume floor (`SCREENER_MIN_DOLLAR_VOL`).
- Nine-rules **Rule 3 / Rule 4** use real market and sector breadth (no longer hardcoded pass in the screener).
- Thesis-aware signals: **Momentum Buy**, **Reversal Watch**, **RS in Weak Sector**, etc.
- Watchlist export prefers top-sector names; weak-sector entries are filtered more tightly.

### Orchestration

- **`getTodaysStockScreenerData.sh`**: soft-fail per step, clearer daily report order, **`--opportunities`** section before full tables, nine-rules gate as final gate.
- New CLI: `stock_screener.py --opportunities`.

### Documentation

- Expanded README suite, **BEST_PRACTICES.md**, **DISCLAIMER.md**, **CONTRIBUTING.md**, this changelog.

---

## [1.x] — 2026-06

### Added

- `market_breadth_collector.py` — S&P 500 and GICS sector breadth.
- `stock_screener.py` — technical scores for top/bottom sectors.
- `nine_rules_gate.py` — nine-rules analysis (initially separate indicator math).
- Daily bash orchestrator and initial READMEs.

---

## Disclaimer

Changes improve engineering consistency and selection logic only. They do **not** guarantee trading profits. See [DISCLAIMER.md](DISCLAIMER.md).

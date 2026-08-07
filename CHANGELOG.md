# Changelog

All notable changes to this project are documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).  
Versions are informal tags for a personal/public toolkit (not necessarily PyPI releases).

---

## [2.4.0] — 2026-08-07

### Screener takeaways (two-axis scoring)

- **`ta_indicators.py`**: additive scoring and bar-hygiene APIs:
  - `session_fraction_elapsed()` — U-shaped session fraction for pro-rating intraday volume
  - `drop_partial_bar()` — still available; opt-in via `use_complete_bars=True`
  - **`use_complete_bars` defaults to `False`** so hourly mid-session runs keep live prices
  - `_Budget` normalizer — each score term declares achievable min/max (fixes fixed-divisor saturation)
  - `setup_quality_score()` / `entry_timing_score()` / `entry_label()` / `extension_flag()`
  - ATR floors (0.5% extension, 0.75% stops), ±8 ATR extension cap, `NO-VOL` flag
  - Stops, targets, risk %, R:R (`rr_ratio` is `None` / shown as `open` at new highs)
  - Rules 6 and 7 made discriminating: dollar-volume + participation; absolute + relative ATR
- **`stock_screener.py`**:
  - Earnings calendar map + `ER+Nd` tagging (soft-fail if calendar unavailable)
  - History: one record per trading day, `runs_today`, `intraday[]`, `days_on_list` / `is_new`
  - Honest `_asof_line` for intraday vs close
  - `--min-setup` floor for `--opportunities` and `--watchlist`
  - Action-bucketed `--opportunities` (actionable / extended / building / new / earnings soon)

### Documentation

- Expanded [README-stock_screener.md](README-stock_screener.md) and [README-ta_indicators.md](README-ta_indicators.md).
- Main [README.md](README.md), [BEST_PRACTICES.md](BEST_PRACTICES.md), and this changelog updated for setup/entry, earnings, and pipeline.

---

## [2.3.0] — 2026-07-31 / 2026-08-05

### Added

- **`earnings_expected_move.py`**: ATM straddle-implied move for names reporting over the next few sessions. Selects the **first option expiration after the report** (not the nearest pre-earnings expiry). Quality labels (GOOD / WIDE / STALE / …), RICH / CHEAP / DILUTED vs realized history, JSON snapshot.
- **`README-earnings_expected_move.md`**: plain-language glossary, CLI, column reference, pipeline notes, `lxml`/venv guidance (expanded 2026-08-06 for non-options readers).

### Orchestration

- **`getStockScreenerData.bat`**: appends `earnings_expected_move.py --briefing`; uses `cd /d "%~dp0"` so launch cwd does not matter.
- **`getTodaysStockScreenerData.sh`**: same briefing step so Linux daily log matches Windows order.

### Notes

- Requires `lxml` for Yahoo earnings-date history (Hist Avg / Verdict). Without it, straddles still price; history columns show `N/A`.
- Calendar / quote failures degrade; they do not abort the daily run.

---

## [2.2.1] — 2026-07-14

### Windows encoding (follow-up)

- Removed remaining non-ASCII from **runtime** Python / shell strings: verbose `Y`/`N` rule marks (was check/cross), `+/-` (was ±), `->` / `-` (was arrows / em dashes), set-union wording as `+` (was ∪), `~` (was ≈).
- `.py`, `.sh`, and `.bat` sources under MarketBreadth are pure ASCII so `PYTHONIOENCODING=cp1252` redirects do not raise `UnicodeEncodeError` on any CLI path (including `--verbose` and `--help` text).

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
| Layout | Runs from KSI parent (MarketBreadth + GoldenRatios) | Bat cds to its own directory (`%~dp0`); modules resolve from there |
| Exit code | Non-zero if any step failed | Batch does not aggregate failure count |

Markdown docs may still use Unicode for readability; **runtime CLI strings** should stay ASCII-safe so Windows logging does not crash.

---

## [2.1.0] — 2026-07-14

### Added

- **`nine_rules_independent.py`**: independent nine-rules re-score with layered universe (core book ∪ personal `tickers.txt` ∪ screener watchlist ∪ CLI). Optional overlap report vs funnel names. Uses shared `ta_indicators` when available.
- Daily pipeline step in **`getTodaysStockScreenerData.sh`**: runs with `--union-watchlist --briefing`; full report → `logs/nine_rules_independent.log`.

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
- Thesis-aware signals (later refined into setup/entry labels in 2.4.0).
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

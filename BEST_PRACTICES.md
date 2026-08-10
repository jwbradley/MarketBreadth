# Best Practices

Practical guidance for running the Market Breadth suite so results are more reliable and easier to interpret. This is operational advice, not investment advice. See [DISCLAIMER.md](DISCLAIMER.md).

---

## 1. Treat the pipeline as a funnel

```
Regime / macro  →  Sector breadth  →  Stock candidates  →  Nine-rules gate  →  Earnings EM
```

| Layer | Tool | Use it for |
|-------|------|------------|
| Macro (optional) | GoldenRatios collectors | Risk-on / metals regime context |
| Sector map | `market_breadth_collector.py` | Where participation is strong or weak |
| Candidates | `stock_screener.py` | Who looks interesting *inside* those sectors |
| Checklist | `nine_rules_gate.py` | Binary pass/fail on a short watchlist |
| Event risk | `earnings_expected_move.py` | How large a move options price for upcoming reports |

Do not skip straight to action labels (`BUY NOW`, `STRONG BUY`) without reading sector and market breadth first.

`ta_indicators.py` is a **shared library** imported by the screener and nine-rules tools. Do **not** add it as a step in the daily shell/batch runners.

---

## 2. Prefer one clean post-close run

- US cash equity session closes **16:00 ET** (15:00 CT).
- Yahoo Finance and similar feeds often need **30–90 minutes** to settle official daily bars.
- Prefer a daily job around **16:30–17:45 CT** (or local equivalent after your market’s close).
- Morning runs (e.g. 07:30 / 08:30) are useful as a **re-report of the prior close**, not as “today’s open edge.”

### Hourly / intraday runs

If you schedule mid-session (e.g. Windows Task Scheduler every hour):

- The screener **keeps the live bar** so prices stay current.
- Volume is **pro-rated** by session fraction so Rule 6 is not failed for clock reasons alone.
- Reports should say “intraday snapshot,” not “as of close.”
- History is collapsed to **one record per calendar day** so `days_on_list` / `NEW` stay meaningful.

If the latest bar date is not the session you expect, treat labels as stale until the next successful collect.

---

## 3. Use the shared indicator path

- `stock_screener.py`, `nine_rules_gate.py`, and (when available) `nine_rules_independent.py` use **`ta_indicators.py`**.
- Do not fork a second RSI/MACD implementation in ad-hoc scripts; scores and rules will diverge.
- If you change indicator math, change it once in `ta_indicators.py` and re-run both tools.
- Changes to that module should be **additive** (new keys / kwargs with defaults). See [README-ta_indicators.md](README-ta_indicators.md).

---

## 4. Interpret setup and entry separately

Read **two** numbers, not one blended score:

| Axes / label | Typical context | How to use |
|--------------|-----------------|------------|
| **High setup + high entry** (`BUY NOW`, `BUY / SCALE IN`) | Strong sector, aligned trend, price not a chase | Primary long focus *if* breadth and liquidity agree |
| **High setup + low entry** (`STRONG - WAIT FOR PULLBACK`) | Great vehicle, extended / overbought | Own the thesis; wait for pullback; note stop distance |
| **Moderate setup** (`WATCH`, `SPECULATIVE ENTRY`) | Mixed structure | Secondary; smaller size or more confirmation |
| **`REVERSAL WATCH` / `RS LEADER *`** | Weak sector, mean-reversion or relative leadership | Different thesis from top-sector momentum |
| **`AVOID` / `AVOID / SHORT BIAS`** | Structure weak | Skip for long bias |

Legacy field `score` is a 70/30 blend of setup/entry for older consumers. Prefer `setup_score` and `entry_score`.

Primary daily focus should be **high-setup names in strong sectors** with acceptable entry (or an explicit plan to wait). Weak-sector setups are optional and different trades.

Raise the bar with `stock_screener.py --min-setup N` (default 60) on `--opportunities` and `--watchlist`.

---

## 5. Liquidity and universe

- Default liquidity floor: **$20M** average dollar volume (20-day). Override with `SCREENER_MIN_DOLLAR_VOL` if needed.
- Universe is **S&P 500 constituents** (auto-refreshed periodically). Mid/small-cap opportunities are out of scope unless you extend the list.
- Alphabet order is **not** used for “top stocks”; ranking is RS + liquidity. Trust the pre-rank step.

---

## 6. Sector ranking is multi-metric

Sectors are ranked by a **composite** (participation, thrust, A/D, up/down volume, net highs/lows)—not a single noisy 1-day A/D print.

Still:

- One day of strong breadth can reverse the next session.
- Prefer multi-day history (`market_breadth_history.json` / CSV) for trend of breadth, not only `*_latest.json`.

---

## 7. Keep the watchlist short

- Export with `stock_screener.py --watchlist` (setup floor via `--min-setup`, top per sector).
- Run `nine_rules_gate.py` on that list, not the entire S&P 500.
- If more than ~15–20 names pass, raise `--min-setup` or restrict focus to top-sector only.
- Respect `ER+Nd` / earnings warnings on the watchlist; size down or wait through the report.

---

## 8. Earnings event risk

- Screener tags names reporting within 7 calendar days (`ER+Nd`).
- `earnings_expected_move.py --briefing` prices ATM straddles on the **first expiry after the report** (not the nearest pre-earnings expiry).
- Daily runners pass **`--include-large-caps 10`**: S&P 500 + watchlist **plus** non-index names with a **known** market cap ≥ $10B. That is how RKLB-class reporters appear without dumping SPACs into the table.
  - Do **not** replace this with `--all-calendar --min-market-cap 10` — that drops small index names and admits unknown-cap blank-check shells.
  - Manual default (flag omitted) still yields only universe names (~9 rows).
- **RICH / CHEAP** is context vs history, not a trade signal. Install **`lxml`** in the active venv or Hist Avg / Verdict show `N/A`.
- Prefer live options quotes when possible; pre-open runs often show STALE / WIDE quality.
- Expect a longer earnings step after large-caps (~3–4 min cold vs ~30s for ~9 names); warm `market_cache` helps on re-runs.

Details: [README-earnings_expected_move.md](README-earnings_expected_move.md).

---

## 9. Shared disk cache

The four analysis tools share **`market_cache.py`** so SPY bars, the Nasdaq calendar, and earnings history are not re-fetched four times in one batch.

| Concern | Guidance |
|---------|----------|
| Default | Cache **on** under `$DATA_DIR/.market_cache/` |
| Still-forming bar | **Never** cached — only closed daily bars (partial-bar rule for TA) |
| Force refresh | `--no-cache` on the tool, or `MARKET_CACHE_DISABLE=1` |
| Housekeeping | `python3 market_cache.py --stats` / `--purge` / `--purge-all` |
| Requirements | `pyarrow` for OHLCV parquet; JSON namespaces work without it |

Do not treat cache hits as a reason to skip a post-close run; TTLs are hours, not days. Full design: [README-market_cache.md](README-market_cache.md).

---

## 10. Orchestration (Linux shell vs Windows batch)

Keep orchestrators thin; keep Python modules separate (Option C).

| | Linux / macOS | Windows |
|--|---------------|---------|
| Runner | `getTodaysStockScreenerData.sh` | `getStockScreenerData.bat` |
| Typical schedule | cron | Task Scheduler |
| Soft-fail per step | Yes | No (inspect the log after the run) |
| Virtualenv | Activates `GoldenRatios/.venv` when present | Uses `python` on `PATH` |
| Log location | `logs/todaysMarketBreadth.log` (+ `logs/errors.log`) | Path in `LOG=` at the top of the `.bat` (**edit this** before first use) |
| Layout assumption | Runs from KSI parent (`MarketBreadth/` + `GoldenRatios/`) | Bat `cd`s to its own directory |

Suggested report order (already in both runners):

1. Macro / ratios status  
2. Breadth briefing  
3. **Best opportunities** (`--opportunities`)  
4. Full screener briefing  
5. Nine-rules gate (`--briefing`)  
6. Independent nine-rules scan (`nine_rules_independent.py --union-watchlist`)  
7. **Earnings expected move** (`earnings_expected_move.py --briefing --include-large-caps 10`)  

Linux: non-zero exit count from the shell script means at least one step failed—wire that to monitoring if you care about uptime. Windows: open the configured log and confirm every “Running:” step completed.

### ASCII-safe CLI output (Windows)

On many Windows installs, Python 3.12 writes stdout as **cp1252**. Characters outside that set (em dash, arrows, √, σ, etc.) can crash a redirected run with `UnicodeEncodeError`. Prefer plain ASCII in **`print()` and argparse descriptions** (`-`, `->`, `sqrt()`, `1-sigma`). Markdown guides may still use Unicode.

---

## 11. Risk management outside the scripts

These tools **do not**:

- Size positions  
- Place orders  
- Enforce stops  
- Account for taxes, dividends, or borrow fees  

Use `risk_pct`, ATR metrics, and liquidity as **inputs** to your own risk rules. Cap risk per name and per day independently of any score. Treat `R:R` of `open` as “no measured overhead supply,” not a free lunch.

---

## 12. Data hygiene

- Refresh constituents if the list is stale (`market_breadth_collector.py --update-constituents`).
- Do not commit large history JSON/CSV, personal logs, or `.market_cache/` to a public repo (see `.gitignore`).
- Respect Yahoo Finance (and any other provider) rate limits and terms of service — the shared cache reduces redundant hits.
- Re-run after holidays; empty or weekend data is expected to look odd.

---

## 13. Validation before trusting a change

After editing indicators or scores:

1. `python3 -m py_compile ta_indicators.py market_cache.py stock_screener.py nine_rules_gate.py nine_rules_independent.py market_breadth_collector.py earnings_expected_move.py`
2. Run breadth collect once.
3. Run screener on one sector (`--sector "Utilities" --top-stocks 5`).
4. Confirm `rules_passed` on the same ticker matches between screener output and `nine_rules_gate.py`.
5. Spot-check a few labels against the setup/entry table (e.g. setup 90 / entry 50 → `BUY / SCALE IN`, not `BUY NOW`).
6. Spot-check earnings: `earnings_expected_move.py --briefing --include-large-caps 10` should add known large non-index names without SPAC shells; default (no flag) should match the smaller universe.
7. On Windows: redirect a briefing to a file and confirm no `UnicodeEncodeError`.
8. Only then run the full daily script (`.sh` or `.bat`).

---

## 14. What not to do

- Do not treat setup 100, entry 100, or “STRONG BUY” as certainty.
- Do not average contradictory systems (mean-reversion + trend) into one action without labeling the thesis.
- Do not force entries into `CHASE` / low-entry high-setup names just because setup looks great.
- Do not hardcode secrets or paid API keys into the repo.
- Do not present outputs as personalized financial advice when sharing publicly.

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | Project overview and pipeline |
| [INTERPRETATION_GUIDE.md](INTERPRETATION_GUIDE.md) | How to read the daily log and output files |
| [README-stock_screener.md](README-stock_screener.md) | Screener details |
| [README-nine_rules.md](README-nine_rules.md) | Nine rules tools |
| [README-ta_indicators.md](README-ta_indicators.md) | Shared indicator library |
| [README-market_cache.md](README-market_cache.md) | Shared TTL disk cache |
| [README-earnings_expected_move.md](README-earnings_expected_move.md) | Earnings straddle report |
| [DISCLAIMER.md](DISCLAIMER.md) | Legal / risk disclaimer |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

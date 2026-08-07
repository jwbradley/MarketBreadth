# Market Breadth Collector & Stock Screener

Daily toolkit for a **quick, structured view** of US large-cap market participation and a short list of candidate opportunities—driven by sector breadth, then individual technicals (setup quality vs entry timing), a shared nine-rules checklist, and an optional earnings expected-move report.

| Layer | Script | Purpose |
|-------|--------|---------|
| Sector breadth | `market_breadth_collector.py` | A/D, % above DMAs, volume, thrust for S&P 500 + 11 GICS sectors |
| Shared TA | `ta_indicators.py` | Library only (no CLI): indicators, two-axis scores, nine rules, sector rank |
| Stock screen | `stock_screener.py` | RS + liquidity ranking, **setup / entry** scores, action labels, ER tags |
| Rules gate | `nine_rules_gate.py` | Nine-rules pass/fail on the exported watchlist |
| Independent scan | `nine_rules_independent.py` | Re-score core book ∪ watchlist (overlap report) |
| Earnings move | `earnings_expected_move.py` | Straddle-implied move for names reporting soon |
| Daily run (Linux) | `getTodaysStockScreenerData.sh` | Cron orchestrator (soft-fail, one log) |
| Daily run (Windows) | `getStockScreenerData.bat` | Same pipeline order for Task Scheduler / console |

`ta_indicators.py` is **imported** by the screener and nine-rules tools; it is not a separate step in the daily runners.

Optional macro companions (separate package): GoldenRatios GSR / market-ratios collectors.

---

## Documentation map

| Doc | Contents |
|-----|----------|
| [BEST_PRACTICES.md](BEST_PRACTICES.md) | How to run and interpret the suite day to day |
| [README-stock_screener.md](README-stock_screener.md) | Screener CLI, two-axis scoring, opportunities, history |
| [README-ta_indicators.md](README-ta_indicators.md) | Shared library API, partial bar, scoring contract |
| [README-nine_rules.md](README-nine_rules.md) | Nine-rules gate and independent scan |
| [README-earnings_expected_move.md](README-earnings_expected_move.md) | Earnings straddle / implied move report |
| [Expected-Move-Guide.md](Expected-Move-Guide.md) | Options expected-move / IV concepts |
| [DISCLAIMER.md](DISCLAIMER.md) | Full risk / no-advice disclaimer |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [SECURITY.md](SECURITY.md) | Security notes |

---

## Architecture (Option C)

Collectors and CLIs stay **separate**. Indicator math is **unified** in `ta_indicators.py` (imported, not orchestrated).

```
market_breadth_collector.py
        │
        ▼  market_breadth_latest.json
ta_indicators.py  ◄── shared TA + setup/entry scores + nine rules + sector rank
        │
        ├── stock_screener.py
        │      → setup/entry scores, --opportunities, --watchlist, ER tags, history
        │         │
        │         ▼  nine_rules_watchlist.json
        ├── nine_rules_gate.py           → same rules math, short-list gate
        ├── nine_rules_independent.py    → core ∪ watchlist re-score
        └── earnings_expected_move.py    → straddle EM for upcoming reports
                 (also feeds ER tags into the screener via shared calendar helper)

getTodaysStockScreenerData.sh  → Linux: collect → screen → report → nine rules → earnings
getStockScreenerData.bat       → Windows: same step order (edit LOG= path)
```

---

## What breadth collection does

Downloads about one year of daily prices for S&P 500 constituents, then calculates for the index and each GICS sector:

| Indicator | What it measures |
|-----------|------------------|
| Advance/Decline ratio | Up vs down names today |
| A/D line (cumulative) | Participation trend |
| % above 50 / 200 DMA | Short- and long-term trend health |
| Up/down volume ratio | Conviction behind the move |
| 52-week highs / lows / net | Breakout vs breakdown breadth |
| Breadth thrust (Zweig-style) | 10-day EMA of advancing %; rare thrust signals flagged |

### Why it matters (context, not certainty)

- Index up + narrowing breadth → fragile leadership  
- Index down + breadth holding → often healthier pullback  
- Extreme sector A/D or thrust → rotation or oversold/overbought context  

Sectors for the **screener** are chosen by a **multi-metric composite** (not one-day A/D alone). Details: [README-ta_indicators.md](README-ta_indicators.md).

---

## Requirements

```bash
pip install yfinance pandas numpy lxml
```

- Python 3.8+ recommended  
- Network access for Yahoo Finance, the public S&P 500 constituent CSV, and (for earnings history) Nasdaq calendar endpoints  
- **`lxml`** is required for Yahoo earnings-date history used by `earnings_expected_move.py` (Hist Avg / Verdict); straddles still price without it  
- No API key for the default setup  

On the Linux host used with the daily script, prefer the shared venv:

```bash
source ~/myPrograms/KSI/GoldenRatios/.venv/bin/activate
# or call GoldenRatios/.venv/bin/python3 directly
```

---

## Quick start

```bash
# 1. Sector breadth
python3 market_breadth_collector.py

# 2. Screen top/bottom sectors (composite), rank stocks by RS + liquidity
python3 stock_screener.py --sectors 3

# 3. Human-readable opportunities + full tables
python3 stock_screener.py --opportunities
python3 stock_screener.py --briefing

# 4. Watchlist + nine-rules gate (setup floor default 60)
python3 stock_screener.py --watchlist
python3 nine_rules_gate.py --briefing

# 5. Optional: earnings straddle report (next few sessions)
python3 earnings_expected_move.py --briefing
```

Or one daily job:

**Linux / macOS (bash):**

```bash
./getTodaysStockScreenerData.sh
# Log: logs/todaysMarketBreadth.log
# Independent nine-rules full dump: logs/nine_rules_independent.log
# Errors / step detail: logs/errors.log
```

**Windows (cmd / Task Scheduler):**

```bat
REM 1) Edit LOG= inside getStockScreenerData.bat to a path on your machine
REM 2) Script cds to its own directory so .py modules resolve from any caller cwd
getStockScreenerData.bat
```

Both runners follow the same order: GoldenRatios collectors (if present) → breadth → screener → watchlist → briefings → nine-rules gate → nine_rules_independent → **earnings expected move**. The Linux script soft-fails per step and activates `GoldenRatios/.venv`; the `.bat` does not—see [BEST_PRACTICES.md](BEST_PRACTICES.md) and [CHANGELOG.md](CHANGELOG.md).

### Scheduled runs (example, weekdays)

Prefer **post-close** when daily bars have settled (often ~16:30–17:45 CT):

```cron
45 17 * * 1-5 /home/YOU/path/MarketBreadth/getTodaysStockScreenerData.sh >> /home/YOU/path/MarketBreadth/logs/errors.log 2>&1
```

On Windows, schedule `getStockScreenerData.bat` with Task Scheduler after the cash close (and optionally hourly intraday). Set **Start in** if needed; the bat uses `cd /d "%~dp0"`. Ensure `python` is on the task’s `PATH`.

Hourly mid-session runs keep the **live bar** and pro-rate volume; reports label the basis as an intraday snapshot rather than “as of close.” Morning runs can re-print the prior close; they are not a substitute for a settled session.

### Windows stdout encoding

Python 3.12 on Windows often defaults stdout to **cp1252**. Fancy Unicode in `print()` (em dashes, arrows, Greek letters, checkmarks) can raise `UnicodeEncodeError` when output is redirected to a log. CLI strings in this repo are kept **ASCII-safe** for that reason. Markdown docs may still use Unicode for readability.

---

## Breadth CLI

```bash
python3 market_breadth_collector.py              # collect
python3 market_breadth_collector.py --status     # table
python3 market_breadth_collector.py --briefing   # markdown
python3 market_breadth_collector.py --csv        # history export
python3 market_breadth_collector.py --update-constituents
```

### Output files (local; usually gitignored)

| File | Purpose |
|------|---------|
| `market_breadth_latest.json` | Latest breadth snapshot |
| `market_breadth_history.json` | Daily breadth history |
| `sp500_constituents.csv` | Constituents + GICS (refreshed periodically) |
| `stock_screener_results.json` | Per-stock technicals, setup/entry scores, flags |
| `stock_screener_history.json` | One record per trading day (tenure / NEW / runs_today) |
| `nine_rules_watchlist.json` | Short list for nine-rules gate |
| `earnings_expected_move_latest.json` | Latest earnings straddle snapshot |

Environment overrides: `MARKET_BREADTH_DIR` or `GSR_DATA_DIR`.  
Liquidity floor for screener: `SCREENER_MIN_DOLLAR_VOL` (default `20000000`).  
Setup floor for opportunities/watchlist: `stock_screener.py --min-setup` (default `60`).

---

## Interpreting opportunities

1. **Regime** — S&P % above 50-DMA and A/D line trend from breadth.  
2. **Where** — Strong sectors by multi-metric composite score.  
3. **Who** — High RS, liquid names (not alphabetical “leaders”).  
4. **Setup vs entry** — Read **both** axes:
   - High setup + high entry → `BUY NOW` / `BUY / SCALE IN` (actionable now)  
   - High setup + low entry → `STRONG - WAIT FOR PULLBACK` (thesis OK, price extended)  
   - Weak sector variants use mean-reversion labels (`RS LEADER *`, `REVERSAL WATCH`)  
5. **Gate** — Nine rules on the watchlist only.  
6. **Earnings** — `ER+Nd` flags and the earnings expected-move table; technicals do not survive an earnings gap.

Start with `stock_screener.py --opportunities` (action buckets), then the full briefing.  
Read [BEST_PRACTICES.md](BEST_PRACTICES.md) before sizing any idea from this toolkit.

For options expected-move / IV concepts: [Expected-Move-Guide.md](Expected-Move-Guide.md) and [README-earnings_expected_move.md](README-earnings_expected_move.md).

---

## Project layout

```
MarketBreadth/
├── market_breadth_collector.py
├── ta_indicators.py              # shared library (import only)
├── stock_screener.py
├── nine_rules_gate.py
├── nine_rules_independent.py
├── earnings_expected_move.py
├── getTodaysStockScreenerData.sh   # Linux/macOS daily runner
├── getStockScreenerData.bat        # Windows daily runner (edit LOG=)
├── README.md
├── README-stock_screener.md
├── README-nine_rules.md
├── README-ta_indicators.md
├── README-earnings_expected_move.md
├── Expected-Move-Guide.md
├── BEST_PRACTICES.md
├── DISCLAIMER.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE                 # CC0 1.0
└── logs/                   # gitignored
```

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `ModuleNotFoundError: yfinance` | `pip install yfinance pandas numpy lxml` |
| Empty / weekend data | Markets closed; wait for a session |
| Stale constituents | `--update-constituents` |
| Screener vs nine-rules gate disagree | Ensure both import `ta_indicators.py`; re-run watchlist after screen |
| Hist Avg / Verdict always `N/A` | Install `lxml` into the **same** Python/venv that runs `earnings_expected_move.py` |
| Slow full run | Normal: full SPX download + multi-sector pre-rank |
| Step failed in daily script (Linux) | Check `logs/errors.log`; other steps may still have completed |
| `UnicodeEncodeError` on Windows | Use current CLI code (ASCII-safe prints). Or set `PYTHONIOENCODING=utf-8` / use a UTF-8 console |
| `.bat` log missing / wrong place | Edit `LOG=` in `getStockScreenerData.bat` to a writable path on your machine |
| `.bat` cannot find `.py` | Bat cds to its own folder; if still broken, set Task Scheduler **Start in** to that directory |
| Eight identical hourly runs | Expected only if bars are dropped; current default keeps the live bar (`use_complete_bars=False`) |

---

## License

[CC0 1.0 Universal](LICENSE) — public domain dedication for the software and project docs.  
Third-party data remains subject to its providers’ terms (e.g. Yahoo Finance).

---

## Disclaimer

This software is for **educational and informational purposes only**. It is **not** investment advice, a solicitation, or a recommendation to buy or sell any security.

- These tools are **not guaranteed to make money**.
- **Past performance is not indicative of future results.**
- Historical prices, technical indicators, breadth statistics, setup/entry scores, and labels such as “BUY NOW” or “STRONG BUY” are **not guarantees** of future prices or outcomes.
- Market data may be delayed, incomplete, or incorrect.
- You alone are responsible for your trading and investment decisions. Consider consulting a licensed financial professional.

**Full text:** [DISCLAIMER.md](DISCLAIMER.md)

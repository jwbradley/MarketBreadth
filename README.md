# Market Breadth Collector & Stock Screener

Daily toolkit for a **quick, structured view** of US large-cap market participation and a short list of candidate opportunities—driven by sector breadth, then individual technicals, then a shared nine-rules checklist.

| Layer | Script | Purpose |
|-------|--------|---------|
| Sector breadth | `market_breadth_collector.py` | A/D, % above DMAs, volume, thrust for S&P 500 + 11 GICS sectors |
| Shared TA | `ta_indicators.py` | One indicator + nine-rules library (used by screener & OvtLyr) |
| Stock screen | `stock_screener.py` | RS + liquidity ranking, composite scores, thesis-aware signals |
| Rules gate | `OvtLyrMimic.py` | Nine-rules pass/fail on the exported watchlist |
| Daily run | `getTodaysStockScreenerData.sh` | Cron orchestrator (soft-fail, one log) |

Optional macro companions (separate package): GoldenRatios GSR / market-ratios collectors.

---

## Documentation map

| Doc | Contents |
|-----|----------|
| [BEST_PRACTICES.md](BEST_PRACTICES.md) | How to run and interpret the suite day to day |
| [README-stock_screener.md](README-stock_screener.md) | Screener CLI, scoring, opportunities |
| [README-OvtLyrMimic.md](README-OvtLyrMimic.md) | Nine rules tool |
| [README-ta_indicators.md](README-ta_indicators.md) | Shared library API |
| [Expected-Move-Guide.md](Expected-Move-Guide.md) | Options expected-move / IV concepts |
| [DISCLAIMER.md](DISCLAIMER.md) | Full risk / no-advice disclaimer |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [SECURITY.md](SECURITY.md) | Security notes |

---

## Architecture (Option C)

Collectors and CLIs stay **separate**. Indicator math is **unified**.

```
market_breadth_collector.py
        │
        ▼  market_breadth_latest.json
ta_indicators.py  ◄── shared rank + TA + nine rules
        │
        ├── stock_screener.py  → scores, signals, --opportunities, --watchlist
        │         │
        │         ▼  ovtlyr_watchlist.json
        └── OvtLyrMimic.py     → same rules math, short-list gate

getTodaysStockScreenerData.sh  → cron: collect → screen → report
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
- Network access for Yahoo Finance and the public S&P 500 constituent CSV  
- No API key for the default setup  

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

# 4. Watchlist + nine-rules gate
python3 stock_screener.py --watchlist
python3 OvtLyrMimic.py --briefing
```

Or one daily job:

```bash
./getTodaysStockScreenerData.sh
# Log: logs/todaysMarketBreadth.log
# Errors / step detail: logs/errors.log
```

### Cron (example, weekdays)

Prefer **post-close** when daily bars have settled (often ~16:30–17:45 CT):

```cron
45 17 * * 1-5 /home/YOU/path/MarketBreadth/getTodaysStockScreenerData.sh >> /home/YOU/path/MarketBreadth/logs/errors.log 2>&1
```

Morning runs can re-print the prior close; they are not a substitute for a settled session.

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
| `market_breadth_history.json` | Daily history |
| `sp500_constituents.csv` | Constituents + GICS (refreshed periodically) |
| `stock_screener_results.json` | Per-stock technicals and scores |
| `ovtlyr_watchlist.json` | Short list for OvtLyr |

Environment overrides: `MARKET_BREADTH_DIR` or `GSR_DATA_DIR`.  
Liquidity floor for screener: `SCREENER_MIN_DOLLAR_VOL` (default `20000000`).

---

## Interpreting opportunities

1. **Regime** — S&P % above 50-DMA and A/D line trend from breadth.  
2. **Where** — Strong sectors by composite score.  
3. **Who** — High RS, liquid names (not alphabetical “leaders”).  
4. **Setup** — Momentum vs reversal labels (different theses).  
5. **Gate** — Nine rules on the watchlist only.

Read [BEST_PRACTICES.md](BEST_PRACTICES.md) before sizing any idea from this toolkit.

For options expected-move / implied-volatility concepts, see [Expected-Move-Guide.md](Expected-Move-Guide.md).

---

## Project layout

```
MarketBreadth/
├── market_breadth_collector.py
├── ta_indicators.py
├── stock_screener.py
├── OvtLyrMimic.py
├── getTodaysStockScreenerData.sh
├── README.md
├── README-stock_screener.md
├── README-OvtLyrMimic.md
├── README-ta_indicators.md
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
| Screener vs OvtLyr disagree | Ensure both import `ta_indicators.py`; re-run watchlist after screen |
| Slow full run | Normal: full SPX download + multi-sector pre-rank |
| Step failed in daily script | Check `logs/errors.log`; other steps may still have completed |

---

## License

[CC0 1.0 Universal](LICENSE) — public domain dedication for the software and project docs.  
Third-party data remains subject to its providers’ terms (e.g. Yahoo Finance).

---

## Disclaimer

This software is for **educational and informational purposes only**. It is **not** investment advice, a solicitation, or a recommendation to buy or sell any security.

- These tools are **not guaranteed to make money**.
- **Past performance is not indicative of future results.**
- Historical prices, technical indicators, breadth statistics, composite scores, and labels such as “Momentum Buy” or “STRONG BUY” are **not guarantees** of future prices or outcomes.
- Market data may be delayed, incomplete, or incorrect.
- You alone are responsible for your trading and investment decisions. Consider consulting a licensed financial professional.

**Full text:** [DISCLAIMER.md](DISCLAIMER.md)

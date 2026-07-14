# Stock Screener — Technical Analysis of Sector Leaders

Automated technical analysis that:

1. Loads sector breadth from `market_breadth_latest.json`
2. Picks strongest / weakest sectors via a **multi-metric composite**
3. Pre-ranks names in each sector by **relative strength + liquidity** (not alphabet)
4. Scores candidates with shared indicators from `ta_indicators.py`
5. Applies the **same nine rules** used by `nine_rules_gate.py`
6. Emits thesis-aware signals and optional watchlist / opportunities briefings

---

## Requirements

```bash
pip install yfinance pandas numpy
```

Requires a recent `market_breadth_latest.json` (run `market_breadth_collector.py` first).

---

## Usage

```bash
# Full analysis: top 2 + bottom 2 sectors by composite (default)
python3 stock_screener.py

# Top/bottom 3 sectors
python3 stock_screener.py --sectors 3

# Deep-score more names per sector
python3 stock_screener.py --top-stocks 20

# One sector only
python3 stock_screener.py --sector "Energy"

# Markdown tables (all screened sectors)
python3 stock_screener.py --briefing

# Short “best opportunities” section (primary daily view)
python3 stock_screener.py --opportunities

# CSV export
python3 stock_screener.py --csv

# Watchlist for nine_rules_gate
python3 stock_screener.py --watchlist
```

### Recommended workflow

```bash
python3 market_breadth_collector.py
python3 stock_screener.py --sectors 3
python3 stock_screener.py --opportunities
python3 stock_screener.py --watchlist
python3 nine_rules_gate.py --briefing
```

---

## How sectors are chosen

Sectors are ranked with `rank_sectors()` in `ta_indicators.py`:

| Input | Role |
|-------|------|
| % above 50-DMA | Participation / trend health |
| Breadth thrust | Multi-day advance intensity |
| A/D ratio | Mapped daily breadth |
| Up/down volume | Conviction |
| Net 52-week highs − lows | Breakout vs breakdown |

This is more stable than sorting only on **one-day A/D**.

---

## How stocks are chosen inside a sector

1. Download history for the sector’s S&P names.  
2. Drop names below the liquidity floor (default **$20M** 20-day average dollar volume).  
3. Rank remaining by a blend of **20d RS vs SPY**, **60d RS**, and log liquidity.  
4. Deep-score the top candidates (`--top-stocks`, with a pre-screen buffer).

Override liquidity:

```bash
export SCREENER_MIN_DOLLAR_VOL=50000000   # $50M
```

---

## Indicators (via `ta_indicators.py`)

| Area | Metrics |
|------|---------|
| Trend | SMA 20/50/200, EMA 10/20/50/100, alignment flags, trend score 0–3 |
| Momentum | Wilder RSI(14), MACD + signal + hist |
| Volatility / volume | Bollinger %B, ATR %, volume ratio, dollar volume |
| Relative | 20d (and 60d) return vs SPY |
| Warnings | Bearish / bullish RSI–price divergence |

See [README-ta_indicators.md](README-ta_indicators.md).

---

## Nine rules

Computed with **real** market and sector `% above 50-DMA` when breadth JSON is present.  
Rules 3 and 4 are no longer stubbed as always true.

| Rules passed | Typical reading |
|--------------|-----------------|
| 8–9 | Strong alignment |
| 6–7 | Mostly positive |
| 4–5 | Mixed |
| 0–3 | Multiple flags against |

nine-rules gate maps the same counts to STRONG BUY / BUY / NEUTRAL / SELL/AVOID.

---

## Composite score (0–100)

Heuristic blend of trend, EMA stack, RSI (tilted by sector type), MACD, Bollinger, ATR, volume, RS vs SPY, divergence, and sector A/D context.

**Top sectors** favor trend/momentum RSI bands.  
**Bottom sectors** lean slightly toward washout / reversal cues.

Scores are a ranking aid, not a probability of profit.

---

## Signals (thesis-aware)

| Sector type | Examples | Meaning |
|-------------|----------|---------|
| Top | `Momentum Buy`, `Buy`, `Neutral`, `Weak`, `Avoid` | Continuation-oriented |
| Bottom | `Reversal Watch`, `RS in Weak Sector`, `Watch`, `Avoid / Short Bias` | Secondary / different thesis |

`--opportunities` prints **Momentum** and **Weak-sector setups** separately so they are not mixed into one “buy list.”

---

## Output

| File / flag | Description |
|-------------|-------------|
| `stock_screener_results.json` | Full run payload |
| `--briefing` | Markdown tables per sector |
| `--opportunities` | Short best-ideas section |
| `--watchlist` → `nine_rules_watchlist.json` | Input for nine-rules gate |
| `--csv` | Flat spreadsheet export |

---

## Performance notes

- Pre-ranking a full sector is heavier than scoring 10 alphabetical names.  
- Full `--sectors 3` can take several minutes depending on network and Yahoo rate limits.  
- SPY is downloaded once per run for relative strength.

---

## Companion tools

| Script | Role |
|--------|------|
| `market_breadth_collector.py` | Must run first |
| `ta_indicators.py` | Shared math |
| `nine_rules_gate.py` | Nine-rules gate on watchlist |
| `getTodaysStockScreenerData.sh` | Daily orchestration (Linux/macOS) |
| `getStockScreenerData.bat` | Daily orchestration (Windows; edit `LOG=`) |

CLI strings use ASCII-safe punctuation so Windows cp1252 log redirects do not fail (see [CHANGELOG.md](CHANGELOG.md) §2.1.1).

Also: [BEST_PRACTICES.md](BEST_PRACTICES.md) · [CHANGELOG.md](CHANGELOG.md)

---

## Disclaimer

This software is for **educational and informational purposes only**. It is **not** investment advice.

- These tools are **not guaranteed to make money**.
- **Past performance is not indicative of future results.**
- Indicators, scores, and signals (including “Momentum Buy” or high numeric scores) are **not guarantees** of future prices.
- You alone are responsible for your decisions. Data may be wrong or delayed.

**Full text:** [DISCLAIMER.md](DISCLAIMER.md)

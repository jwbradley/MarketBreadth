# OvtLyrMimic — OVTLYR Nine Rules Analysis

Python implementation of the OVTLYR Nine Rules trading framework. Evaluates stocks against 9 criteria covering trend, momentum, breadth, volume, volatility, and divergence to generate buy/sell signals.

Now fully integrated with the market breadth collector and stock screener for real data instead of estimates.

---

## What It Does

For each stock, evaluates 9 independent rules and generates a signal:

| Rules Passed | Signal | Meaning |
|-------------|--------|---------|
| 8-9 / 9 | STRONG BUY | All major criteria aligned — high conviction |
| 6-7 / 9 | BUY | Mostly positive — reasonable entry |
| 4-5 / 9 | NEUTRAL | Mixed signals — no clear edge |
| 0-3 / 9 | SELL/AVOID | Multiple criteria failing — stay away |

---

## The Nine Rules

| Rule | Name | What It Checks |
|------|------|----------------|
| 1 | Trend Confirmation | Price > 10 EMA > 20 EMA > 50 EMA (full stacking) |
| 2 | Signal Alignment | Price above 20 EMA + positive 5-day momentum |
| 3 | Market Breadth | S&P 500 % above 50-DMA > 50% (real data from breadth collector) |
| 4 | Sector Strength | Sector % above 50-DMA > 50% (real data from breadth collector) |
| 5 | Behavioral Sentiment | RSI between 40-70 (strength without overextension) |
| 6 | Liquidity/Volume | Current volume > 80% of 20-day average |
| 7 | Position Sizing (ATR) | ATR < 8% of price (manageable volatility) |
| 8 | Multi-Timeframe | Price above both 20 EMA (short) and 100 EMA (long) |
| 9 | No Contradictions | No bearish divergence (price up + RSI down + overbought) |

---

## Requirements

```bash
pip install yfinance pandas numpy
```

Optional (for real breadth data):
- `market_breadth_latest.json` from `market_breadth_collector.py`
- `ovtlyr_watchlist.json` from `stock_screener.py --watchlist`

Without these files, the script falls back to estimates (SPY position as breadth proxy).

---

## Usage

### From Auto-Generated Watchlist (recommended)

```bash
# Full pipeline: breadth → screener → watchlist → OVTLYR
python3 market_breadth_collector.py
python3 stock_screener.py
python3 stock_screener.py --watchlist
python3 OvtLyrMimic.py
```

### Manual Ticker List

```bash
# Analyze specific tickers
python3 OvtLyrMimic.py --tickers AAPL MSFT NVDA AMD TSLA

# Magnificent Seven
python3 OvtLyrMimic.py --tickers AAPL AMZN GOOGL MSFT META NVDA TSLA
```

### Custom Watchlist File

```bash
python3 OvtLyrMimic.py --watchlist my_stocks.json
```

### Output Formats

```bash
# Summary table (default)
python3 OvtLyrMimic.py

# Markdown briefing for reports
python3 OvtLyrMimic.py --briefing

# Verbose — show each rule's pass/fail details per stock
python3 OvtLyrMimic.py --verbose
```

---

## Data Integration

### With Market Breadth Collector

When `market_breadth_latest.json` exists, the script uses **real data** for Rules 3 and 4:

- **Rule 3 (Market Breadth):** Uses actual S&P 500 % above 50-DMA (e.g., 63.8%)
- **Rule 4 (Sector Strength):** Uses actual sector % above 50-DMA per stock's sector

Without the file, it falls back to estimating breadth from SPY's position vs its 50 EMA.

### With Stock Screener Watchlist

When `ovtlyr_watchlist.json` exists, the script:
- Auto-loads the top-scored stocks from the screener
- Inherits market breadth percentage
- Gets per-stock sector breadth for Rule 4
- No manual ticker entry needed

---

## Output Examples

### Summary Table

```
==========================================================================================
Ticker   Sector                       Signal       Rules    RS/SPY   Pass%
------------------------------------------------------------------------------------------
BKNG     Consumer Discretionary       STRONG BUY   9/9     +7.0%    100%
LNT      Utilities                    STRONG BUY   8/9     +8.0%    89%
AEP      Utilities                    STRONG BUY   8/9     +9.7%    89%
EA       Communication Services       STRONG BUY   8/9     +4.2%    89%
CCL      Consumer Discretionary       BUY          6/9     +4.3%    67%
==========================================================================================

Signal Distribution:
  STRONG BUY: 9
  BUY: 8
  NEUTRAL: 0
  SELL/AVOID: 0

Total Analyzed: 17
```

### Markdown Briefing (--briefing)

```
## OVTLYR Nine Rules Analysis (2026-06-26)

| Ticker |                    Sector |       Signal | Rules |  RS/SPY |
|--------|--------------------------|--------------|-------|---------|
|   BKNG |  Consumer Discretionary  |   STRONG BUY |   9/9 |  +7.0%  |
|    LNT |                Utilities |   STRONG BUY |   8/9 |  +8.0%  |
|   AMZN |  Consumer Discretionary  |  SELL/AVOID  |   3/9 | -14.7%  |
```

### Verbose (--verbose)

```
============================================================
  BKNG — STRONG BUY (9/9)
============================================================
  [+] Rule 1: Trend Confirmation
      Price: $4521.30, 10EMA: $4480.12, 20EMA: $4350.88, 50EMA: $4100.55
  [+] Rule 2: Signal Alignment
      Above 20EMA: True, 5-day momentum: True
  [+] Rule 3: Market Breadth
      Breadth: 63.8% above 50-DMA (threshold: 50%)
  [+] Rule 4: Sector Strength
      Sector breadth: 57.4% above 50-DMA (threshold: 50%)
  ...
```

---

## Watchlist JSON Format

If creating a custom watchlist, use this structure:

```json
{
  "generated": "2026-06-26 07:54:59",
  "source_date": "2026-06-25",
  "market_breadth_pct": 63.8,
  "stocks": [
    {
      "ticker": "AAPL",
      "sector": "Information Technology",
      "sector_breadth_pct": 59.5
    },
    {
      "ticker": "XOM",
      "sector": "Energy",
      "sector_breadth_pct": 19.0
    }
  ]
}
```

Only `ticker` is required. `sector` and `sector_breadth_pct` are optional (enables Rules 3/4 with real data).

---

## Differences from v1

| Feature | v1 (original) | v2 (current) |
|---------|--------------|--------------|
| Stock list | Hardcoded arrays in script | JSON watchlist (auto-generated or manual) |
| Market breadth (Rule 3) | Estimated from SPY vs 50 EMA | Real data from market_breadth_collector |
| Sector breadth (Rule 4) | Hardcoded default (55%) | Real sector A/D data per stock |
| Relative Strength | Not included | 20-day RS vs SPY displayed |
| Input modes | Script edit only | CLI args, watchlist file, or pipeline |
| Output | Text dump only | Summary table, markdown briefing, verbose details |
| Integration | Standalone | Full pipeline with breadth + screener |
| Signal threshold | 7+ = Strong Buy | 8+ = Strong Buy (more selective) |

---

## How to Interpret

### Strong Buy (8-9 rules)

All major technical dimensions agree:
- Trend is up (EMAs stacked bullishly)
- Momentum is positive (price above EMAs, rising)
- Market and sector are healthy (breadth > 50%)
- Volume confirms the move
- No warnings (divergence, volatility)

**Action:** High-conviction entry opportunity. Size appropriately using ATR.

### Buy (6-7 rules)

Most dimensions positive but 2-3 minor concerns:
- Maybe sector is slightly weak (Rule 4 failing)
- Or RSI is getting extended (Rule 5 failing)
- Or volume is below average (Rule 6 failing)

**Action:** Valid entry but monitor the failing rules. Smaller position size.

### Neutral (4-5 rules)

Mixed signals — half the rules pass, half fail:
- Might be in transition (trend changing)
- Or market breadth is deteriorating while stock holds up

**Action:** Wait for clarity. No edge here.

### Sell/Avoid (0-3 rules)

Multiple dimensions failing:
- Trend is broken
- Momentum negative
- Often means breadth AND technicals both weak

**Action:** Stay away. If already holding, evaluate exit.

---

## Complete Pipeline

```
market_breadth_collector.py
    │
    ├── market_breadth_latest.json  (sector A/D ratios, % above DMA)
    │
    ▼
stock_screener.py
    │
    ├── stock_screener_results.json (full technicals per stock)
    │
    ├── stock_screener.py --watchlist
    │       └── ovtlyr_watchlist.json (top stocks with sector context)
    │
    ▼
OvtLyrMimic.py
    │
    └── Nine Rules analysis with real breadth data
        ├── Summary table
        ├── Markdown briefing (--briefing)
        └── Verbose rule details (--verbose)
```

---

## Companion Scripts

| Script | Purpose |
|--------|---------|
| `market_breadth_collector.py` | Sector-level breadth data (run first) |
| `stock_screener.py` | Individual stock technicals + watchlist generation |
| `OvtLyrMimic.py` | This script — Nine Rules analysis |
| `market_ratios_collector.py` | Gold/Silver, Dow/Gold, S&P/Gold ratios |

---

## License

Personal use. Based on publicly available OVTLYR framework concepts. Data sourced from Yahoo Finance.

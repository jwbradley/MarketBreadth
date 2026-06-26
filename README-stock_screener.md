# Stock Screener — Technical Analysis of Sector Leaders

Automated technical analysis tool that identifies the strongest and weakest S&P 500 sectors (from market breadth data), then performs deep analysis on individual stocks within those sectors using multiple indicators, relative strength, divergence detection, and a rule-based scoring system.

---

## What It Does

1. Reads `market_breadth_latest.json` to identify top 2 + bottom 2 sectors by A/D ratio
2. Fetches 1 year of price/volume data for top stocks in each sector
3. Calculates 13+ technical indicators per stock
4. Compares each stock's performance against SPY (relative strength)
5. Detects bullish/bearish divergences
6. Factors sector breadth into individual stock scores
7. Applies a 9-rule pass/fail system (OVTLYR-inspired)
8. Generates a composite score (0-100) and actionable signal

---

## Requirements

```bash
pip install yfinance pandas numpy
```

Also requires `market_breadth_latest.json` — run `market_breadth_collector.py` first.

---

## Usage

```bash
# Full analysis: top 2 + bottom 2 sectors, 10 stocks each
python3 stock_screener.py

# Top/bottom 3 sectors
python3 stock_screener.py --sectors 3

# Analyze 20 stocks per sector
python3 stock_screener.py --top-stocks 20

# Analyze a specific sector
python3 stock_screener.py --sector "Energy"

# Markdown briefing for reports
python3 stock_screener.py --briefing

# Export to CSV for spreadsheet analysis
python3 stock_screener.py --csv
```

### Workflow (run in sequence)

```bash
# 1. Collect breadth (identifies top/bottom sectors)
python3 market_breadth_collector.py

# 2. Screen individual stocks in those sectors
python3 stock_screener.py

# 3. View results
python3 stock_screener.py --briefing
```

---

## Indicators Calculated Per Stock

### Trend Indicators

| Indicator | Description |
|-----------|-------------|
| SMA 20/50/200 | Simple Moving Averages for long-term trend |
| EMA 10/20/50 | Exponential Moving Averages for faster trend confirmation |
| Trend Score (0-3) | Count of SMAs the price is above |
| EMA Alignment | Whether price > 10 EMA > 20 EMA > 50 EMA (bullish stacking) |
| MA Alignment | Whether 20 SMA > 50 SMA > 200 SMA |
| Multi-Timeframe | Price above both 20 EMA (short-term) and 100 EMA (long-term) |

### Momentum Indicators

| Indicator | Description |
|-----------|-------------|
| RSI (14-day) | Relative Strength Index — overbought (>70) / oversold (<30) |
| MACD | 12/26 EMA crossover — direction and momentum |
| MACD Signal | 9-period EMA of MACD — crossover triggers |
| MACD Histogram | MACD minus Signal — momentum acceleration |

### Volatility & Volume

| Indicator | Description |
|-----------|-------------|
| Bollinger %B | Position within 20-day Bollinger Bands (0=lower, 1=upper) |
| ATR (14-day) | Average True Range as % of price — risk per trade |
| Volume Ratio | Today's volume vs 20-day average — institutional conviction |
| Avg Daily Volume | Liquidity screen (can you get in/out?) |

### Relative & Contextual

| Indicator | Description |
|-----------|-------------|
| Relative Strength vs SPY | 20-day return minus SPY's 20-day return — alpha generation |
| Bearish Divergence | Price rising + RSI falling + RSI > 65 — warning signal |
| Bullish Divergence | Price falling + RSI rising + RSI < 35 — opportunity signal |
| Sector A/D Ratio | Breadth data factored into score — sector tailwind/headwind |

---

## 9-Rule Pass/Fail System

Inspired by the OVTLYR Nine Rules framework. Each stock is evaluated against 9 criteria:

| Rule | Criteria | What It Checks |
|------|----------|----------------|
| 1 | EMA Trend Confirmation | Price > 10 EMA > 20 EMA > 50 EMA |
| 2 | Signal Alignment | Price above 20 EMA + positive 5-day momentum |
| 3 | Market Breadth | (Contextual — from breadth data) |
| 4 | Sector Strength | (Contextual — sector A/D ratio) |
| 5 | RSI Optimal Zone | RSI between 40-70 (not overbought/oversold) |
| 6 | Volume Sufficient | Volume ratio > 0.8x average |
| 7 | Manageable Volatility | ATR < 8% of price |
| 8 | Multi-Timeframe | Price above both 20 EMA and 100 EMA |
| 9 | No Contradictions | No bearish divergence present |

**Interpretation:**
- 8-9 rules passed → Strong alignment across all dimensions
- 6-7 rules passed → Mostly positive, minor concerns
- 4-5 rules passed → Mixed signals, proceed with caution
- 0-3 rules passed → Multiple red flags

---

## Composite Score (0-100)

The score combines all indicators with contextual weighting:

| Factor | Max Impact | Logic |
|--------|-----------|-------|
| Trend alignment (SMA) | +/- 15 | More DMAs above = higher |
| EMA alignment | +7 | Full EMA stacking bonus |
| Multi-timeframe | +5 | Short + long agree |
| RSI | +/- 12 | Oversold = opportunity, overbought = risk |
| MACD direction | +/- 6 | Bullish crossover positive |
| Bollinger position | +/- 8 | Oversold bounce vs extended |
| ATR/Volatility | +/- 5 | Low vol safer, high vol riskier |
| Volume | +/- 5 | High volume = conviction |
| Relative Strength vs SPY | +/- 8 | Outperforming = alpha |
| Divergence | +/- 8 | Warnings penalized, opportunities rewarded |
| Sector breadth | +/- 6 | Strong sector = tailwind |

### Signal Interpretation

| Score | Signal | Meaning |
|-------|--------|---------|
| 70-100 | Strong Buy | Multiple indicators + rules aligned bullish |
| 60-69 | Buy | Mostly positive technicals |
| 40-59 | Neutral | Mixed signals, no clear edge |
| 30-39 | Weak | Deteriorating technicals |
| 0-29 | Avoid | Multiple indicators bearish |

---

## Output

### Briefing (--briefing)

```
## Stock Screener (2026-06-25)

### STRONGEST: Utilities (Sector A/D: 6.75)

| Ticker |    Price | Score | Rules | Trend |   RSI |   MACD |  RS/SPY |  ATR% |    Flags |     Signal |
|--------|----------|-------|-------|-------|-------|--------|---------|-------|----------|------------|
|    LNT | $  76.19 |    86 |   8/9 |   3/3 |  74.2 |   Bull |   +8.0% |  1.7% |      EMA | Strong Buy |
|    AEP | $ 137.00 |    86 |   8/9 |   3/3 |  75.3 |   Bull |   +9.7% |  1.8% |      EMA | Strong Buy |

### WEAKEST: Consumer Discretionary (Sector A/D: 0.34)

| Ticker |    Price | Score | Rules | Trend |   RSI |   MACD |  RS/SPY |  ATR% |    Flags |     Signal |
|--------|----------|-------|-------|-------|-------|--------|---------|-------|----------|------------|
|   ABNB | $ 141.88 |    86 |   7/9 |   3/3 |  62.5 |   Bull |   +7.9% |  3.1% |      EMA | Strong Buy |
|   AMZN | $ 227.01 |    31 |   5/9 |   0/3 |  29.6 |   Bear |  -14.7% |  3.7% |        - |       Weak |
```

### Flags Explained

| Flag | Meaning |
|------|---------|
| `EMA` | Full EMA alignment (price > 10 > 20 > 50) — strong trend |
| `DIV-` | Bearish divergence detected (price up, RSI down) — caution |
| `DIV+` | Bullish divergence detected (price down, RSI up) — potential reversal |
| `-` | No special flags |

### Output Files

| File | Description |
|------|-------------|
| `stock_screener_results.json` | Full analysis with all indicators per stock |
| `stock_screener_results.csv` | Flat export for spreadsheets (via `--csv`) |

---

## How to Read the Results

### For Top Sectors (buy candidates)

Look for stocks with:
- Score 70+ with 8-9 rules passed
- EMA flag (trend fully aligned)
- RS/SPY positive (outperforming the market)
- Low ATR% (manageable risk)
- No DIV- flag

### For Bottom Sectors (avoid/value hunt)

Two strategies:
1. **Avoid:** Stocks with Score < 40, RS/SPY deeply negative, DIV- flag
2. **Contrarian value:** Stocks in weak sectors with high rules count + bullish divergence (DIV+) — these are potential reversals

### Red Flags

- `DIV-` + RSI > 65 + Score dropping → distribution phase, likely to fall further
- RS/SPY < -10% → massively underperforming; needs a catalyst to reverse
- ATR% > 6% → very volatile; position size accordingly
- Rules < 4/9 → most criteria failing; stay away unless contrarian thesis is strong

---

## Comparison to OvtLyrMimic.py

| Feature | OvtLyrMimic.py | stock_screener.py |
|---------|---------------|-------------------|
| Stocks analyzed | Manual list (Mag 7 + custom) | Auto-selected from breadth data |
| Market breadth | Estimated from SPY position | Real breadth data from collector |
| Sector breadth | Placeholder | Real A/D ratio integrated into score |
| Relative strength | Not included | 20-day vs SPY |
| ATR | Calculated for info only | Factored into score + displayed |
| Divergence | Rule 9 only | Flagged visually + scored |
| Output | Text dump per stock | Sorted table with signals |
| Scoring | 9 rules binary (pass/fail) | Hybrid: composite score + 9 rules |
| Sector selection | Manual | Automatic from breadth data |

---

## Performance

- ~3-5 seconds per stock (1-year data fetch + calculation)
- 10 stocks × 4 sectors = ~2-3 minutes total
- 20 stocks × 4 sectors = ~5-6 minutes total

---

## Watchlist Generation (--watchlist)

Exports the top-scored stocks in a format that `OvtLyrMimic.py` can consume:

```bash
# Generate watchlist (default: score >= 60, top 5 per sector)
python3 stock_screener.py --watchlist

# Custom output path
python3 stock_screener.py --watchlist /path/to/my_watchlist.json
```

Output (`ovtlyr_watchlist.json`):
```json
{
  "generated": "2026-06-26 07:54:59",
  "source_date": "2026-06-25",
  "min_score": 60,
  "market_breadth_pct": 63.8,
  "stocks": [
    {"ticker": "BKNG", "sector": "Consumer Discretionary", "sector_type": "bottom", "score": 85, "rules_passed": 9},
    {"ticker": "LNT", "sector": "Utilities", "sector_type": "top", "score": 86, "rules_passed": 8}
  ]
}
```

This feeds directly into `OvtLyrMimic.py` for the full Nine Rules analysis with real breadth context.

---

## Complete Pipeline

```
market_breadth_collector.py    (sector breadth → identifies strongest/weakest)
         ↓
stock_screener.py              (individual stock technicals → scores + signals)
         ↓
stock_screener.py --watchlist  (exports top stocks → ovtlyr_watchlist.json)
         ↓
OvtLyrMimic.py                (9-rule pass/fail analysis with real breadth data)
```

---

## Companion Scripts

| Script | Purpose |
|--------|---------|
| `market_breadth_collector.py` | Sector-level breadth (must run first) |
| `stock_screener.py` | This script — individual stock technicals |
| `OvtLyrMimic.py` | OVTLYR Nine Rules analysis (consumes watchlist) |
| `market_ratios_collector.py` | Gold/Silver, Dow/Gold, S&P/Gold ratios |
| `gsr_data_collector.py` | Gold/silver from FRED (1968+) |
| `update_gsr_chart.py` | Chart generation |

---

## License

Personal use. Data sourced from Yahoo Finance under their terms of service.

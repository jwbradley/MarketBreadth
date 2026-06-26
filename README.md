# Market Breadth Collector & Stock Screener

Daily market breadth indicator calculator for the S&P 500 and all 11 GICS sectors, plus a technical analysis screener that drills into individual stocks within the strongest and weakest sectors.

| Script | Purpose |
|--------|---------|
| `market_breadth_collector.py` | Sector-level breadth (A/D, DMA%, volume, thrust) |
| `stock_screener.py` | Individual stock technicals (RSI, MACD, Bollinger, DMA alignment) |

---

## What It Does

Downloads 1 year of daily price and volume data for all 503 S&P 500 constituents (~17 seconds), then calculates:

| Indicator | What It Measures |
|-----------|-----------------|
| Advance/Decline Ratio | How many stocks went up vs down today |
| A/D Line (cumulative) | Running total of net advances — trend shows sustained participation |
| % Above 50-DMA | Short-term trend health (are most stocks in uptrends?) |
| % Above 200-DMA | Long-term trend health (are most stocks above their yearly average?) |
| Up/Down Volume Ratio | Total volume in advancing stocks vs declining stocks — institutional conviction |
| 52-week Highs | Stocks making new highs (broad strength) |
| 52-week Lows | Stocks making new lows (broad weakness) |
| Net Highs - Lows | Difference between new highs and new lows — divergence from index warns of pullback |
| Breadth Thrust (Zweig) | 10-day EMA of advancing % — extreme surges (from <40% to >61.5% in 10 days) signal new bull markets |

All indicators are calculated for the S&P 500 overall AND each of the 11 GICS sectors individually.

---

## Why It Matters

- **Index up, breadth narrowing** = rally driven by fewer stocks = fragile (potential top)
- **Index down, breadth holding** = healthy pullback, not a breakdown
- **A/D ratio < 0.5 in a sector** = that sector is in broad-based selling
- **% above 50-DMA < 30%** = oversold, potential bounce opportunity
- **% above 50-DMA > 70%** = strong uptrend, ride the wave
- **Up/Down Volume > 2.0** = strong institutional buying power behind the advance
- **Up/Down Volume < 0.5** = heavy institutional selling, even if index isn't down much
- **A/D Line rising while index flat** = hidden strength, accumulation phase
- **A/D Line falling while index rising** = dangerous divergence, fewer stocks participating
- **Breadth Thrust crosses 61.5% from below 40% in 10 days** = rare Zweig buy signal (historically very reliable for major bull runs)

---

## Requirements

```bash
pip install yfinance pandas lxml
```

- Python 3.7+
- No API key required (uses Yahoo Finance)
- Internet connection for data download

---

## Installation

```bash
# Clone or copy the script
cp market_breadth_collector.py /home/pi/scripts/

# Install dependencies
pip install yfinance pandas lxml

# First run (downloads S&P 500 constituent list automatically)
python3 market_breadth_collector.py
```

---

## Usage

```bash
# Collect today's breadth data (default mode)
python3 market_breadth_collector.py

# Show current status (table format)
python3 market_breadth_collector.py --status

# Markdown briefing (for reports, sorted strongest to weakest)
python3 market_breadth_collector.py --briefing

# Export history to CSV (for spreadsheet analysis)
python3 market_breadth_collector.py --csv

# Export to specific path
python3 market_breadth_collector.py --csv /path/to/breadth_export.csv

# Force refresh S&P 500 constituent list
python3 market_breadth_collector.py --update-constituents
```

---

## Output Files

| File | Purpose |
|------|---------|
| `market_breadth_latest.json` | Current day's breadth snapshot (all sectors) |
| `market_breadth_history.json` | Daily history for trend analysis |
| `sp500_constituents.csv` | S&P 500 list with GICS sectors (auto-refreshed monthly) |

### Sample latest.json structure:

```json
{
  "date": "2026-06-23",
  "generated": "2026-06-24 07:28:41",
  "sp500": {
    "total_stocks": 503,
    "advancing": 285,
    "declining": 217,
    "unchanged": 1,
    "ad_ratio": 1.31,
    "above_50dma": 301,
    "pct_above_50dma": 59.8,
    "above_200dma": 311,
    "pct_above_200dma": 62.2,
    "new_52wk_highs": 23,
    "new_52wk_lows": 10
  },
  "sectors": {
    "Information Technology": { ... },
    "Health Care": { ... },
    ...
  }
}
```

---

## Sectors Tracked (11 GICS)

| Sector | Typical Stocks |
|--------|---------------|
| Information Technology | AAPL, MSFT, NVDA, AVGO |
| Health Care | JNJ, UNH, LLY, PFE |
| Financials | JPM, BAC, GS, BRK-B |
| Consumer Discretionary | AMZN, TSLA, HD, MCD |
| Consumer Staples | PG, KO, PEP, COST |
| Energy | XOM, CVX, COP, EOG |
| Industrials | CAT, HON, UNP, GE |
| Materials | LIN, APD, SHW, FCX |
| Utilities | NEE, DUK, SO, D |
| Real Estate | PLD, AMT, CCI, EQIX |
| Communication Services | META, GOOGL, NFLX, DIS |

---

## Cron Setup (Raspberry Pi or Linux)

Run daily after market close (4 PM ET = 3 PM CT):

```bash
# Edit crontab
crontab -e

# Add this line (5:45 PM CT Monday-Friday)
45 17 * * 1-5 /usr/bin/python3 /home/pi/scripts/market_breadth_collector.py >> /home/pi/logs/market_breadth.log 2>&1
```

Create log directory:
```bash
mkdir -p /home/pi/logs
```

### Why 5:45 PM?

- US markets close at 4:00 PM ET (3:00 PM CT)
- Yahoo Finance needs ~30-60 minutes to finalize closing prices
- 5:45 PM CT gives plenty of buffer for clean data

---

## Standalone PC Setup (Windows)

```cmd
:: Install Python packages
pip install yfinance pandas lxml

:: Run manually
python market_breadth_collector.py

:: Or use Task Scheduler for automation:
:: Program: python.exe
:: Arguments: C:\path\to\market_breadth_collector.py
:: Trigger: Daily at 5:45 PM, weekdays only
```

---

## Interpreting the Output

### Briefing Example:

```
## Market Breadth (2026-06-24)

**S&P 500 Overall:** 359 advancing / 143 declining (A/D ratio: 2.51)
- A/D Line: 4402 (rising)
- Above 50-DMA: 63.7% (320/502)
- Above 200-DMA: 63.5% (317/502)
- Up/Down Volume Ratio: 1.69
- 52-week Highs: 27 | Lows: 3 | Net: 24
- Breadth Thrust: 54.7%

**Sector Breadth (strongest to weakest):**

| Sector                         |     A/D | Ratio |  >50DMA | >200DMA |  UpVol | Net H/L | Thrust |
|--------------------------------|---------|-------|---------|---------|--------|---------|--------|
| Consumer Discretionary         |  45/2   | 22.50 |  66.0% |  51.1% |  3.33 |      +2 |  56.3% |
| Industrials                    |  67/13  |  5.15 |  71.2% |  67.1% |  4.69 |      +6 |  57.3% |
| Health Care                    |  49/10  |  4.90 |  69.5% |  52.5% |  1.16 |      +4 |  57.6% |
| Information Technology         |  52/22  |  2.36 |  60.8% |  63.0% |  2.41 |      +1 |  50.0% |
| Energy                         |   3/18  |  0.17 |  14.3% |  90.5% |  0.08 |      +0 |  41.5% |
```

### Reading the Data:

- **A/D Ratio > 2.0** — Strong bullish breadth (broad participation in the rally)
- **A/D Ratio 1.0-2.0** — Mildly positive breadth
- **A/D Ratio < 0.5** — Heavy selling across the sector
- **>50DMA above 70%** — Healthy short-term uptrend
- **>50DMA below 30%** — Oversold / bearish short-term
- **>200DMA above 70%** — Strong long-term trend
- **>200DMA below 40%** — Bear market territory
- **Net Highs/Lows positive** — Broad strength, more stocks breaking out than breaking down
- **Net Highs/Lows negative** — Broad weakness, breakdown signal
- **Up/Down Volume > 2.0** — Strong conviction behind the move (institutional buying)
- **Up/Down Volume < 0.5** — Sellers dominating volume (institutional distribution)
- **Breadth Thrust > 61.5%** — Overbought short-term but strong momentum
- **Breadth Thrust < 40%** — Oversold, potential reversal setup
- **Zweig Signal (YES)** — Extremely rare bull signal; historically 100% reliable for major advances

### Divergence Signals:

| Signal | What It Means |
|--------|---------------|
| Index rising + fewer stocks above 50 DMA | Rally narrowing, fragile top forming |
| Index rising + A/D Line falling | Dangerous — fewer stocks participating in the rally |
| Index falling + % above 200 DMA holding | Healthy correction, not a breakdown |
| Index new high + Net Highs/Lows deteriorating | Classic pre-correction warning |
| A/D ratio diverging between sectors | Rotation happening (money moving) |
| Defensive sectors A/D high + Tech A/D low | Risk-off rotation (flight to safety) |
| Up/Down Volume high + A/D ratio low | Big money buying a few stocks heavily (narrow leadership) |
| Breadth Thrust surging from oversold | Potential trend reversal — watch for Zweig confirmation |

---

## Stock Screener (stock_screener.py)

Takes the breadth data output and drills into individual stocks within the strongest and weakest sectors. Performs technical analysis on the top 10-20 stocks per sector and generates buy/avoid signals.

### How It Works

1. Reads `market_breadth_latest.json` to identify top 2 + bottom 2 sectors by A/D ratio
2. Fetches 1 year of price/volume history for top stocks in each sector
3. Calculates technical indicators per stock
4. Generates a composite score (0-100) and signal

### Requirements

```bash
pip install yfinance pandas numpy
```

Requires `market_breadth_latest.json` from running `market_breadth_collector.py` first.

### Usage

```bash
# Auto-select top 2 + bottom 2 sectors, 10 stocks each
python3 stock_screener.py

# Top/bottom 3 sectors instead of 2
python3 stock_screener.py --sectors 3

# Analyze 20 stocks per sector
python3 stock_screener.py --top-stocks 20

# Analyze a specific sector
python3 stock_screener.py --sector "Energy"

# Markdown output for reports
python3 stock_screener.py --briefing

# Export to CSV for spreadsheet analysis
python3 stock_screener.py --csv
```

### Indicators Calculated (per stock)

| Indicator | What It Measures |
|-----------|-----------------|
| Price vs 20/50/200 DMA | Trend alignment (above all 3 = strong uptrend) |
| EMA 10/20/50 Alignment | Faster trend confirmation (price > 10 > 20 > 50 EMA = bullish) |
| Multi-Timeframe | Price above both 20 EMA and 100 EMA (short + long agree) |
| Trend Score (0-3) | Count of DMAs the price is above |
| RSI (14-day) | Overbought (>70) / Oversold (<30) |
| MACD + Signal | Momentum direction and crossover |
| Bollinger %B | Position within Bollinger Bands (0=lower, 1=upper) |
| ATR (14-day) | Volatility as % of price — risk per trade |
| Volume Ratio | Today's volume vs 20-day average (conviction) |
| Relative Strength vs SPY | 20-day outperformance vs market benchmark |
| Divergence Detection | Bearish (price up, RSI down) / Bullish (price down, RSI up) |
| Rules Passed (0-9) | OVTLYR-inspired pass/fail count across 9 criteria |
| Sector Breadth Context | Sector A/D ratio boosts/penalizes individual stock scores |

### Composite Score (0-100)

The score weights multiple indicators with sector context:

| Factor | Impact | Logic |
|--------|--------|-------|
| Trend alignment (SMA) | +/- 15 | More DMAs above = higher score |
| EMA alignment | +7 | Bonus if price > 10 > 20 > 50 EMA |
| Multi-timeframe | +5 | Both short and long EMAs agree |
| RSI | +/- 12 | Oversold = opportunity, overbought = risk |
| MACD direction | +/- 6 | Bullish crossover = positive |
| Bollinger position | +/- 8 | Oversold bounce potential vs extended risk |
| ATR/Volatility | +/- 5 | Low vol = safer, high vol = riskier |
| Volume | +/- 5 | High volume confirms the move |
| Relative Strength vs SPY | +/- 8 | Outperforming market = strong alpha |
| Divergence | +/- 8 | Bearish divergence = warning, bullish = opportunity |
| Sector breadth context | +/- 6 | Strong sector A/D ratio = tailwind, weak = headwind |

### Signal Interpretation

| Score | Signal | Meaning |
|-------|--------|---------|
| 70-100 | Strong Buy | Multiple indicators aligned bullish |
| 60-69 | Buy | Mostly positive technicals |
| 40-59 | Neutral | Mixed signals, no clear edge |
| 30-39 | Weak | Deteriorating technicals |
| 0-29 | Avoid | Multiple indicators bearish |

### Output Files

- `stock_screener_results.json` — Full analysis with all indicators per stock
- `stock_screener_results.csv` — Flat export for spreadsheets (via `--csv`)

### Briefing Output Example

```
## Stock Screener (2026-06-25)

### STRONGEST: Utilities (Sector A/D: 6.75)

| Ticker |    Price | Score | Rules | Trend |   RSI |   MACD |  RS/SPY |  ATR% |    Flags |     Signal |
|--------|----------|-------|-------|-------|-------|--------|---------|-------|----------|------------|
|    LNT | $  76.19 |    86 |   8/9 |   3/3 |  74.2 |   Bull |   +8.0% |  1.7% |      EMA | Strong Buy |
|    AEE | $ 114.53 |    86 |   8/9 |   3/3 |  74.2 |   Bull |   +8.3% |  1.8% |      EMA | Strong Buy |
|    AEP | $ 137.00 |    86 |   8/9 |   3/3 |  75.3 |   Bull |   +9.7% |  1.8% |      EMA | Strong Buy |

### WEAKEST: Consumer Discretionary (Sector A/D: 0.34)

| Ticker |    Price | Score | Rules | Trend |   RSI |   MACD |  RS/SPY |  ATR% |    Flags |     Signal |
|--------|----------|-------|-------|-------|-------|--------|---------|-------|----------|------------|
|   ABNB | $ 141.88 |    86 |   7/9 |   3/3 |  62.5 |   Bull |   +7.9% |  3.1% |      EMA | Strong Buy |
|   AMZN | $ 227.01 |    31 |   5/9 |   0/3 |  29.6 |   Bear |  -14.7% |  3.7% |        - |       Weak |
```

### Full Analysis Pipeline

```bash
# Step 1: Collect breadth (identifies top/bottom sectors)
python3 market_breadth_collector.py

# Step 2: Screen individual stocks in those sectors
python3 stock_screener.py

# Step 3: Generate watchlist for OVTLYR analysis
python3 stock_screener.py --watchlist

# Step 4: Run Nine Rules analysis on top stocks
python3 OvtLyrMimic.py

# Step 5: View results
python3 stock_screener.py --briefing
python3 OvtLyrMimic.py --briefing
```

Or chain the full pipeline:
```bash
python3 market_breadth_collector.py && python3 stock_screener.py && python3 stock_screener.py --watchlist && python3 OvtLyrMimic.py
```

---

## Data Source

- **Price data:** Yahoo Finance (free, no API key)
- **S&P 500 list:** GitHub datasets repo (auto-refreshed monthly)
- **History:** Goes back as far as you want (1 year used for DMA/52-week calculations)
- **Frequency:** Daily (business days only)

---

## Environment Variables (Optional)

```bash
# Override data directory (default: same directory as script)
export MARKET_BREADTH_DIR="/home/pi/data/markets"

# Also respects GSR_DATA_DIR if MARKET_BREADTH_DIR not set
export GSR_DATA_DIR="/home/pi/data/metals"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: yfinance` | Run `pip install yfinance pandas lxml` |
| No data returned | Markets may be closed (weekend/holiday) |
| `FutureWarning: pct_change` | Cosmetic warning from pandas; safe to ignore |
| Constituent list stale | Run `--update-constituents` to refresh |
| History file growing too large | Safe to delete and re-run; only latest matters for daily use |
| Script takes >30 seconds | Normal — downloading 503 stocks takes ~17s, calculations ~1s |

---

## Companion Scripts

This script is part of a market data collection suite:

| Script | Purpose |
|--------|---------|
| `market_breadth_collector.py` | This script — S&P 500 breadth by sector |
| `market_ratios_collector.py` | Gold/Silver ratio, Dow/Gold, S&P/Gold |
| `gsr_data_collector.py` | Gold/silver prices from FRED (back to 1968) |
| `update_gsr_chart.py` | Generates GSR chart PNG from collected data |

See [`README-gsr_data_collector.md`](https://github.com/jwbradley/GoldenRatios) for the full suite documentation.

---

## License

Internal use. Data sourced from Yahoo Finance under their terms of service.

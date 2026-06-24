# Market Breadth Collector

Daily market breadth indicator calculator for the S&P 500 and all 11 GICS sectors. Measures the health and participation of the broad market beyond what index levels alone can tell you.

---

## What It Does

Downloads 1 year of daily price data for all 503 S&P 500 constituents (~17 seconds), then calculates:

| Indicator | What It Measures |
|-----------|-----------------|
| Advance/Decline Ratio | How many stocks went up vs down today |
| % Above 50-DMA | Short-term trend health (are most stocks in uptrends?) |
| % Above 200-DMA | Long-term trend health (are most stocks above their yearly average?) |
| 52-week Highs | Stocks making new highs (broad strength) |
| 52-week Lows | Stocks making new lows (broad weakness) |

All indicators are calculated for the S&P 500 overall AND each of the 11 GICS sectors individually.

---

## Why It Matters

- **Index up, breadth narrowing** = rally driven by fewer stocks = fragile (potential top)
- **Index down, breadth holding** = healthy pullback, not a breakdown
- **A/D ratio < 0.5 in a sector** = that sector is in broad-based selling
- **% above 50-DMA < 30%** = oversold, potential bounce opportunity
- **% above 50-DMA > 70%** = strong uptrend, ride the wave

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
## Market Breadth (2026-06-23)

**S&P 500 Overall:** 285 advancing / 217 declining (A/D ratio: 1.31)
- Above 50-DMA: 59.8% (301/503)
- Above 200-DMA: 62.2% (311/503)
- 52-week Highs: 23 | Lows: 10

**Sector Breadth (strongest to weakest):**

| Sector                         |     A/D | Ratio |  >50DMA | >200DMA | Highs | Lows |
|--------------------------------|---------|-------|---------|---------|-------|------|
| Utilities                      |  27/4   |  6.75 |  83.9% |  83.9% |     3 |    0 |
| Real Estate                    |  27/4   |  6.75 |  77.4% |  80.6% |     1 |    0 |
| Consumer Staples               |  29/5   |  5.80 |  60.0% |  62.9% |     1 |    0 |
| Information Technology         |  22/52  |  0.42 |  59.5% |  63.0% |     0 |    3 |
| Materials                      |   4/22  |  0.18 |  57.7% |  65.4% |     0 |    0 |
```

### Reading the Data:

- **A/D Ratio > 2.0** — Strong bullish breadth (broad participation in the rally)
- **A/D Ratio 1.0-2.0** — Mildly positive breadth
- **A/D Ratio < 0.5** — Heavy selling across the sector
- **>50DMA above 70%** — Healthy short-term uptrend
- **>50DMA below 30%** — Oversold / bearish short-term
- **>200DMA above 70%** — Strong long-term trend
- **>200DMA below 40%** — Bear market territory
- **Highs >> Lows** — Broad strength, new highs across the market
- **Lows >> Highs** — Broad weakness, breakdown signal

### Divergence Signals:

| Signal | What It Means |
|--------|---------------|
| Index rising + fewer stocks above 50 DMA | Rally narrowing, fragile top forming |
| Index falling + % above 200 DMA holding | Healthy correction, not a breakdown |
| A/D ratio diverging between sectors | Rotation happening (money moving) |
| Defensive sectors A/D high + Tech A/D low | Risk-off rotation (flight to safety) |

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

See `README-gsr_data_collector.md` for the full suite documentation.

---

## License

Internal use. Data sourced from Yahoo Finance under their terms of service.

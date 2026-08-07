# Stock Screener — Technical Analysis of Sector Leaders

Automated technical analysis tool that identifies the strongest and weakest S&P 500 sectors (from market breadth data), then performs deep analysis on individual stocks within those sectors using multiple indicators, relative strength, divergence detection, and a rule-based scoring system.

All of the math lives in `ta_indicators.py`, a shared library also used by `nine_rules_gate.py` and `nine_rules_independent.py` — see **`README-ta_indicators.md`** for the indicator internals, the `_Budget` normalization contract, and the constraints on editing it.

---

## What It Does

1. Reads `market_breadth_latest.json` to identify top 2 + bottom 2 sectors by A/D ratio
2. Fetches 1 year of price/volume data for top stocks in each sector
3. Calculates 13+ technical indicators per stock
4. Compares each stock's performance against SPY (relative strength)
5. Detects bullish/bearish divergences
6. Factors sector breadth into individual stock scores
7. Applies a 9-rule pass/fail system (OVTLYR-inspired)
8. Scores two independent axes - Setup Quality and Entry Timing - plus stop, risk % and R:R

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

## Two-Axis Scoring

A single composite score conflated two independent questions and hid the case that
matters most: **a great stock at a bad price.** Both now score separately.

### Setup Quality (0-100) - is this a sound vehicle?

Structural only. Deliberately excludes extension and overbought measures.

| Factor | Range | Logic |
|--------|-------|-------|
| Trend alignment (SMA) | +/- 15 | More DMAs above = higher |
| EMA alignment | +7 | Full EMA stacking |
| Multi-timeframe | +5 | Short + long agree |
| MACD direction | +6 / -6 | Bullish crossover positive |
| RS vs SPY (20d) | +/- 9 | Continuous via `tanh` |
| RS vs SPY (60d) | +/- 7 | Continuous via `tanh` |
| Liquidity | -3 / +4 | Continuous on `log10` of 20d dollar volume |
| Relative volatility | -5 / +2 | vs the stock's own 100-day median ATR% |
| Divergence | +/- 8 | Warnings penalized, reversals rewarded |
| Sector breadth | -5 / +6 | Sector tailwind or headwind |

### Entry Timing (0-100) - is *now* a good price?

| Factor | Range | Logic |
|--------|-------|-------|
| Extension from 50-DMA in ATR | +20 / -25 | Primary term; volatility-normalized |
| Extension percentile (own 1y) | +10 / -18 | Stretched vs its own history |
| Bollinger %B | +10 / -15 | Mid-band good, upper band chasing |
| RSI | +8 / -15 | Overbought penalized |
| Volume confirmation | +5 / -3 | Participation on the entry bar |

Both axes are normalized against **the range each name could actually have
reached**, not a fixed divisor. An earlier fixed divisor clipped 18 of 60 names to
exactly 100 and flattened the ranking precisely at the top. Names missing an
optional input (no RS history, no sector breadth) are not judged against points
they never had a chance to earn.

### Action Labels

Derived from the pair, not from an average:

| Setup | Entry | Label |
|-------|-------|-------|
| >= 70 | >= 65 | `BUY NOW` |
| >= 70 | >= 45 | `BUY / SCALE IN` |
| >= 70 | < 45 | `STRONG - WAIT FOR PULLBACK` |
| >= 55 | >= 65 | `SPECULATIVE ENTRY` |
| >= 55 | < 65 | `WATCH` |
| < 55 | any | `AVOID` |

Weak-sector names use a mean-reversion variant: `RS LEADER - ENTRY OK`,
`RS LEADER - EXTENDED`, `REVERSAL WATCH`, `AVOID / SHORT BIAS`.

`score` is retained as a legacy 70/30 blend of the two axes for backward
compatibility. Prefer `setup_score` and `entry_score`.

Use `--min-setup N` (default 60) to set the Setup Quality floor for
`--opportunities` and `--watchlist`.

---

## Risk Metrics

| Field | Meaning |
|-------|---------|
| `stop_price` | 2-ATR stop, or just under a nearby 20-day swing low |
| `stop_basis` | `2atr` or `swing_low_20` |
| `risk_pct` | Distance to stop as % of price - position sizing input |
| `target_price` | 52-week high when it is far enough above to be real resistance |
| `rr_ratio` | Reward:risk. **`None`, shown as `open`** when price is at new highs |

`R:R` of `open` means no measurable overhead supply - a bullish condition, not
missing data. An earlier version substituted a 2R projection here, which made 25
of 60 names print exactly `2.00`: an assumption (2R/1R) wearing the costume of a
measurement.

ATR is floored at 0.5% of price for extension and 0.75% for stops. A stock pinned
in a 0.4% daily range (typically a pending acquisition) otherwise produced a
nonsensical 25 ATR extension and a 0.8% stop. Such names are flagged `NO-VOL`.

---

## Intraday Runs and the Partial Bar

The Windows Task Scheduler job **"Today's Market Screener"** runs hourly, 07:30 to
14:30 CT (08:30-15:30 ET) - **every run is intraday.**

yfinance returns a live, still-accumulating bar for the current session, whose
`Volume` is only the shares traded so far. Comparing that raw figure to a full-day
20-day average understated participation by roughly 6x at 10:30 ET and failed the
volume rule on 53 of 60 names for purely clock-related reasons.

The fix keeps the live bar so **prices stay current**, and pro-rates the volume
comparison by the fraction of the session elapsed (`session_fraction_elapsed()`, a
mildly U-shaped curve reflecting front- and back-loaded volume). The partial bar is
also excluded from the 20-day average so a half day of volume does not drag down
the baseline it is measured against.

Dropping the bar instead would make all eight daily runs report the prior close -
eight identical outputs. `use_complete_bars=True` still does that, which is the
right choice for backtests or exact end-of-day reconciliation.

Reports label the basis honestly: an intraday run prints
`**Data as of:** <date> intraday snapshot, N% of session elapsed (volume pro-rated)`
rather than claiming "as of close".

---

## Screener History

`stock_screener_history.json` holds **one record per trading day**, always the most
recent run of that day, capped at 260 days.

Collapsing by date is what keeps `days_on_list` meaningful under an hourly
schedule - without it an eight-run day would count as eight days of tenure.
`runs_today` records that the earlier runs happened, and `intraday[]` keeps the
within-day series (last 12 runs).

| Field | Meaning |
|-------|---------|
| `days_on_list` | Consecutive trading days on the screen (streak-based) |
| `is_new` | First appearance in the current streak - the `NEW` flag |
| `first_seen` | Earliest recorded appearance |

A name that drops off and returns reads as new again.

---

## Earnings Cross-Reference

Each run pulls the Nasdaq earnings calendar (reusing
`earnings_expected_move.fetch_earnings_calendar`) and tags any screened name
reporting within `EARNINGS_WARN_DAYS` (7) as `ER+Nd`. A calendar failure degrades
to no tags rather than failing the run.

---

## Output

### Briefing (--briefing)

```
## Stock Screener (2026-08-07)

**Market breadth:** 66.7% above 50-DMA
**Indicators as of close:** 2026-08-07

### STRONGEST: Materials | composite: 78.41

| Ticker |    Price | Setup | Entry | Rules |   RSI |  RS/SPY |  x50DMA |     Stop |   R:R | Days |     Flags |                     Action |
|--------|----------|-------|-------|-------|-------|---------|---------|----------|-------|------|-----------|----------------------------|
|    NUE | $ 272.63 |    92 |    54 |   9/9 |  66.1 |  +13.8% |   +2.9A |  $254.48 |  open |    3 |         - |                    BUY NOW |
|   STLD | $ 262.55 |    90 |    82 |   9/9 |  61.4 |   +8.9% |   +1.3A |  $244.31 |  1.41 |    5 |         - |                    BUY NOW |
|   BKNG | $ 214.42 |    96 |    19 |   8/9 |  73.2 |  +18.8% |   +4.3A |  $198.10 |  open |    1 | CHASE,NEW | STRONG - WAIT FOR PULLBACK |
```

### Opportunities (--opportunities)

Groups by what to *do*, not by score:

- **Actionable now** - good setup and good entry
- **Strong but extended** - own the thesis, wait for the price
- **Building / secondary** - moderate setup
- **New to the screen today**
- **Earnings within 7 days**

### Flags Explained

| Flag | Meaning |
|------|---------|
| `CHASE` | > 4.5 ATR above the 50-DMA, or >= 95th percentile of its own year |
| `EXTENDED` | > 3.0 ATR above the 50-DMA, or >= 85th percentile |
| `AT-MEAN` | < 0.5 ATR from the 50-DMA - a base, not a chase |
| `NO-VOL` | ATR collapsed vs its own norm - usually a pending acquisition |
| `DIV-` | Bearish divergence (price up, RSI down) |
| `DIV+` | Bullish divergence (price down, RSI up) |
| `ER+Nd` | Earnings in N days |
| `NEW` | First appearance on the screen in this streak |
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
- Setup 70+ with 8-9 rules passed
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

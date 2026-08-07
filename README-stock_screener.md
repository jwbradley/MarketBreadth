# Stock Screener — Technical Analysis of Sector Leaders

Automated technical analysis tool that identifies the strongest and weakest S&P 500 sectors (from market breadth data), then performs deep analysis on individual stocks within those sectors using multiple indicators, relative strength, divergence detection, and a rule-based scoring system.

All of the math lives in `ta_indicators.py`, a shared library also used by `nine_rules_gate.py` and `nine_rules_independent.py` — see **`README-ta_indicators.md`** for the indicator internals, the `_Budget` normalization contract, and the constraints on editing it.

---

## What It Does

1. Reads `market_breadth_latest.json` and ranks sectors by a **multi-metric composite** (not single-day A/D alone)
2. Pre-ranks names inside each sector by **relative strength + liquidity** (not CSV / alphabetical order)
3. Fetches ~1 year of price/volume data for the top candidates in each sector
4. Calculates indicators via shared `ta_indicators.calculate_from_ohlcv`
5. Compares each stock to SPY (20d and 60d relative strength)
6. Detects bullish/bearish divergences
7. Factors sector breadth into **setup quality**
8. Applies a **9-rule** pass/fail checklist (shared with the nine-rules gate)
9. Scores two independent axes — **Setup Quality** and **Entry Timing** — plus stop, risk %, and R:R
10. Tags upcoming earnings (`ER+Nd`) and maintains day-level history for tenure / `NEW`

---

## Requirements

```bash
pip install yfinance pandas numpy
```

Also requires `market_breadth_latest.json` — run `market_breadth_collector.py` first.  
Earnings tags reuse `earnings_expected_move` when that module is importable; a calendar failure degrades to no tags.

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

# Action-bucketed opportunities (uses --min-setup floor)
python3 stock_screener.py --opportunities
python3 stock_screener.py --opportunities --min-setup 70

# Markdown briefing for reports
python3 stock_screener.py --briefing

# Export to CSV for spreadsheet analysis
python3 stock_screener.py --csv

# Watchlist for nine_rules_gate.py (setup floor default 60)
python3 stock_screener.py --watchlist
python3 stock_screener.py --watchlist --min-setup 65
```

### Workflow (run in sequence)

```bash
# 1. Collect breadth (identifies top/bottom sectors by composite)
python3 market_breadth_collector.py

# 2. Screen individual stocks in those sectors
python3 stock_screener.py --sectors 3

# 3. View results
python3 stock_screener.py --opportunities
python3 stock_screener.py --briefing

# 4. Watchlist + nine-rules gate
python3 stock_screener.py --watchlist
python3 nine_rules_gate.py --briefing
```

Or use the daily orchestrators: `getTodaysStockScreenerData.sh` (Linux) / `getStockScreenerData.bat` (Windows).

---

## Indicators Calculated Per Stock

### Trend Indicators

| Indicator | Description |
|-----------|-------------|
| SMA 20/50/200 | Simple Moving Averages for long-term trend |
| EMA 10/20/50/100 | Exponential Moving Averages for trend confirmation |
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
| ATR vs own median | Current ATR% ÷ 100-day median ATR% (relative volatility) |
| Volume Ratio | Today's volume vs 20-day average (pro-rated if the bar is still forming) |
| Dollar volume (20d) | Liquidity screen (can you get in/out?) |

### Relative & Contextual

| Indicator | Description |
|-----------|-------------|
| Relative Strength vs SPY | 20-day and 60-day return minus SPY |
| Extension from 50-DMA | Percent, ATR units, and own 1y percentile |
| Bearish Divergence | Price rising + RSI falling + RSI > 65 — warning signal |
| Bullish Divergence | Price falling + RSI rising + RSI < 35 — opportunity signal |
| Sector A/D Ratio | Breadth data factored into setup quality |

---

## 9-Rule Pass/Fail System

Educational multi-factor checklist (independent of any commercial platform). Evaluated in shared `ta_indicators.evaluate_nine_rules` so the screener and `nine_rules_gate.py` stay aligned.

| Rule | Criteria | What It Checks |
|------|----------|----------------|
| 1 | EMA Trend Confirmation | Price > 10 EMA > 20 EMA > 50 EMA |
| 2 | Signal Alignment | Price above 20 EMA + positive 5-day momentum |
| 3 | Market Breadth | S&P % above 50-DMA ≥ 50 (fails closed if unknown) |
| 4 | Sector Strength | Sector % above 50-DMA ≥ 50 (fails closed if unknown) |
| 5 | RSI Optimal Zone | RSI between 40–70 |
| 6 | Liquidity / Volume | 20d dollar volume ≥ floor (default $20M) **and** volume ratio > 0.6 |
| 7 | Position Sizing | ATR% < 8 **and** ATR vs own 100d median < 1.5 |
| 8 | Multi-Timeframe | Price above both 20 EMA and 100 EMA |
| 9 | No Contradictions | No bearish divergence present |

**Interpretation:**
- 8–9 rules passed → Strong alignment across dimensions  
- 6–7 rules passed → Mostly positive, minor concerns  
- 4–5 rules passed → Mixed signals  
- 0–3 rules passed → Multiple red flags  

Full rule detail and history of why Rules 6/7 changed: [README-ta_indicators.md](README-ta_indicators.md).

---

## Two-Axis Scoring

A single composite score conflated two independent questions and hid the case that
matters most: **a great stock at a bad price.** Both now score separately.

### Setup Quality (0-100) — is this a sound vehicle?

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

### Entry Timing (0-100) — is *now* a good price?

| Factor | Range | Logic |
|--------|-------|-------|
| Extension from 50-DMA in ATR | +20 / -25 | Primary term; volatility-normalized |
| Extension percentile (own 1y) | +10 / -18 | Stretched vs its own history |
| Bollinger %B | +10 / -15 | Mid-band good, upper band chasing |
| RSI | +8 / -15 | Overbought penalized |
| Volume confirmation | +5 / -3 | Participation on the entry bar |

Both axes are normalized against **the range each name could actually have
reached**, not a fixed divisor. Names missing an optional input (no RS history,
no sector breadth) are not judged against points they never had a chance to earn.

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
compatibility. Prefer `setup_score` and `entry_score`. Ranking uses setup first,
then entry.

Use `--min-setup N` (default 60) to set the Setup Quality floor for
`--opportunities` and `--watchlist`.

---

## Risk Metrics

| Field | Meaning |
|-------|---------|
| `stop_price` | 2-ATR stop, or just under a nearby 20-day swing low |
| `stop_basis` | `2atr` or `swing_low_20` |
| `risk_pct` | Distance to stop as % of price — position sizing input |
| `target_price` | 52-week high when it is far enough above to be real resistance |
| `target_basis` | `52w_high` or `open_no_overhead` |
| `rr_ratio` | Reward:risk. **`None`, shown as `open`** when price is at new highs |

`R:R` of `open` means no measurable overhead supply — a bullish condition, not
missing data. When `target_basis` is `open_no_overhead`, `target_price` may still
hold a 2R projection for display; **do not treat that as measured R:R** — trust
`rr_ratio` / the `open` column.

ATR is floored at 0.5% of price for extension and 0.75% for stops. A stock pinned
in a collapsed range otherwise produced nonsensical extension and stops. Such
names are flagged `NO-VOL`.

---

## Intraday Runs and the Partial Bar

The Windows Task Scheduler job runs hourly, 07:30 to 14:30 CT (08:30–15:30 ET) —
**every of those runs is mid-session.**

yfinance returns a live, still-accumulating bar for the current session, whose
`Volume` is only the shares traded so far. Comparing that raw figure to a full-day
20-day average understated participation and failed the volume rule for clock
reasons.

The fix keeps the live bar so **prices stay current**, and pro-rates the volume
comparison by the fraction of the session elapsed (`session_fraction_elapsed()`, a
mildly U-shaped curve reflecting front- and back-loaded volume). The partial bar is
also excluded from the 20-day average so a half day of volume does not drag down
the baseline it is measured against.

Dropping the bar instead would make all hourly runs report the prior close —
identical outputs. `use_complete_bars=True` still does that, which is the right
choice for backtests or exact end-of-day reconciliation. Scheduled / default path
uses `False`.

Reports label the basis honestly: an intraday run prints an
`intraday snapshot, N% of session elapsed (volume pro-rated)` line rather than
claiming "as of close".

---

## Screener History

`stock_screener_history.json` holds **one record per trading day**, always the most
recent run of that day, capped at 260 days.

Collapsing by date is what keeps `days_on_list` meaningful under an hourly
schedule — without it an eight-run day would count as eight days of tenure.
`runs_today` records that the earlier runs happened, and `intraday[]` keeps the
within-day series (last 12 runs).

| Field | Meaning |
|-------|---------|
| `days_on_list` | Consecutive trading days on the screen (streak-based) |
| `is_new` | First appearance in the current streak — the `NEW` flag |
| `first_seen` | Earliest recorded appearance in history |

A name that drops off and returns reads as new again.

---

## Earnings Cross-Reference

Each run pulls the Nasdaq earnings calendar (reusing
`earnings_expected_move.fetch_earnings_calendar`) and tags any screened name
reporting within `EARNINGS_WARN_DAYS` (7 calendar days) as `ER+Nd`. A calendar
failure degrades to no tags rather than failing the run.

For full straddle / implied-move detail on upcoming reporters, run
`earnings_expected_move.py --briefing` (included in both daily orchestrators).
See [README-earnings_expected_move.md](README-earnings_expected_move.md).

---

## Output

### Briefing (--briefing)

Illustrative layout (numbers are examples; labels must match the setup/entry table):

```
## Stock Screener (2026-08-07)

**Market breadth:** 66.7% above 50-DMA
**Indicators as of close:** 2026-08-07

### STRONGEST: Materials | composite: 78.41

| Ticker |    Price | Setup | Entry | Rules |   RSI |  RS/SPY |  x50DMA |     Stop |   R:R | Days |     Flags |                     Action |
|--------|----------|-------|-------|-------|-------|---------|---------|----------|-------|------|-----------|----------------------------|
|   STLD | $ 262.55 |    90 |    82 |   9/9 |  61.4 |   +8.9% |   +1.3A |  $244.31 |  1.41 |    5 |         - |                    BUY NOW |
|    NUE | $ 272.63 |    92 |    54 |   9/9 |  66.1 |  +13.8% |   +2.9A |  $254.48 |  open |    3 |         - |             BUY / SCALE IN |
|   BKNG | $ 214.42 |    96 |    19 |   8/9 |  73.2 |  +18.8% |   +4.3A |  $198.10 |  open |    1 | CHASE,NEW | STRONG - WAIT FOR PULLBACK |
```

- STLD: setup 90, entry 82 → `BUY NOW`  
- NUE: setup 92, entry 54 → `BUY / SCALE IN` (good vehicle, only moderate entry)  
- BKNG: setup 96, entry 19 → `STRONG - WAIT FOR PULLBACK` + `CHASE`  

### Opportunities (--opportunities)

Groups by what to *do*, not by a single score (setup floor via `--min-setup`):

- **Actionable now** — good setup and good entry (`BUY NOW`, `BUY / SCALE IN`, `RS LEADER - ENTRY OK`)
- **Strong but extended** — own the thesis, wait for the price
- **Building / secondary** — moderate setup or speculative timing
- **New to the screen today**
- **Earnings within 7 days**

### Flags Explained

| Flag | Meaning |
|------|---------|
| `CHASE` | > 4.5 ATR above the 50-DMA, or >= 95th percentile of its own year |
| `EXTENDED` | > 3.0 ATR above the 50-DMA, or >= 85th percentile |
| `AT-MEAN` | < 0.5 ATR from the 50-DMA — a base, not a chase |
| `NO-VOL` | ATR collapsed vs its own norm — usually a pending acquisition |
| `DIV-` | Bearish divergence (price up, RSI down) |
| `DIV+` | Bullish divergence (price down, RSI up) |
| `ER+Nd` | Earnings in N days |
| `NEW` | First appearance on the screen in this streak |
| `-` | No special flags |

### Output Files

| File | Description |
|------|-------------|
| `stock_screener_results.json` | Full analysis with all indicators per stock |
| `stock_screener_history.json` | Day-collapsed tenure history (gitignored) |
| `stock_screener_results.csv` | Flat export for spreadsheets (via `--csv`) |
| `nine_rules_watchlist.json` | Short list for `nine_rules_gate.py` (via `--watchlist`) |

---

## How to Read the Results

### For Top Sectors (buy candidates)

Look for stocks with:
- Setup **70+** with 8–9 rules passed  
- Entry high enough for the intended action (`BUY NOW` needs entry ≥ 65)  
- EMA aligned / multi-timeframe aligned  
- RS/SPY positive  
- Manageable `risk_pct` / no `NO-VOL`  
- No `DIV-` flag  
- No imminent `ER+Nd` unless you explicitly accept gap risk  

### For Bottom Sectors (avoid / value hunt)

Two strategies:
1. **Avoid:** Low setup, deeply negative RS/SPY, `DIV-`, or `AVOID / SHORT BIAS`
2. **Contrarian / leadership:** `RS LEADER - ENTRY OK` or `REVERSAL WATCH` with bullish divergence (`DIV+`) — different thesis from top-sector momentum

### Red Flags

- `DIV-` + RSI > 65 + falling setup → distribution risk  
- RS/SPY < -10% → massively underperforming; needs a catalyst  
- High `risk_pct` or elevated `atr_vs_own_median` → size down  
- Rules < 4/9 → most criteria failing  
- `CHASE` / low entry with high setup → wait; do not force entry into extension  
- `ER+Nd` → technicals may not survive the report  

---

## Screener vs nine-rules tools

| Feature | `stock_screener.py` | `nine_rules_gate.py` |
|---------|---------------------|----------------------|
| Universe | Auto from top/bottom sectors (composite) | Exported watchlist only |
| Scoring | Setup + entry axes, flags, stops | Nine-rules pass/fail (+ optional EM) |
| Sector selection | Automatic multi-metric composite | Inherited from watchlist tags |
| Relative strength | 20d / 60d vs SPY in setup score | Via shared indicators when run |
| Output | Tables, opportunities, history | Per-name rules checklist |

---

## Performance

- ~3–5 seconds per stock (1-year data fetch + calculation)  
- 10 stocks × 4 sectors ≈ 2–3 minutes  
- 20 stocks × 4 sectors ≈ 5–6 minutes  

---

## Watchlist Generation (--watchlist)

Exports high-setup names for `nine_rules_gate.py`. Prefers top-sector names;
bottom-sector entries are filtered more tightly (RS leader / reversal / high rules).

```bash
# Default: setup >= 60, top 5 per sector
python3 stock_screener.py --watchlist

# Higher bar
python3 stock_screener.py --watchlist --min-setup 70

# Custom output path
python3 stock_screener.py --watchlist /path/to/my_watchlist.json
```

Output (`nine_rules_watchlist.json` shape):

```json
{
  "generated": "2026-08-07 15:30:00",
  "source_date": "2026-08-07",
  "min_setup_score": 60,
  "market_breadth_pct": 66.7,
  "stocks": [
    {
      "ticker": "STLD",
      "sector": "Materials",
      "sector_type": "top",
      "setup_score": 90.0,
      "entry_score": 82.0,
      "entry_label": "BUY NOW",
      "rules_passed": 9
    }
  ]
}
```

Then:

```bash
python3 nine_rules_gate.py --briefing
```

---

## Complete Pipeline

```
market_breadth_collector.py       (sector breadth → composite top/bottom)
         ↓
stock_screener.py                 (setup/entry scores, flags, history, ER tags)
         ↓
stock_screener.py --watchlist     → nine_rules_watchlist.json
         ↓
nine_rules_gate.py                (9-rule gate on the short list)
         ↓
nine_rules_independent.py         (optional: core ∪ watchlist re-score)
         ↓
earnings_expected_move.py         (straddle EM for upcoming reports)
```

Daily: `getTodaysStockScreenerData.sh` or `getStockScreenerData.bat`.

---

## Companion Scripts

| Script | Purpose |
|--------|---------|
| `market_breadth_collector.py` | Sector-level breadth (must run first) |
| `ta_indicators.py` | Shared library (import only — not a pipeline step) |
| `stock_screener.py` | This script — individual stock technicals |
| `nine_rules_gate.py` | Nine-rules analysis on the exported watchlist |
| `nine_rules_independent.py` | Independent re-score of core ∪ watchlist |
| `earnings_expected_move.py` | Earnings calendar straddle / implied move |
| `market_ratios_collector.py` | Gold/Silver, Dow/Gold, S&P/Gold ratios (GoldenRatios) |
| `gsr_data_collector.py` | Gold/silver from FRED (GoldenRatios) |
| `update_gsr_chart.py` | Chart generation (GoldenRatios) |

---

## License

[CC0 1.0 Universal](LICENSE) — same as the rest of this project.  
Data sourced from Yahoo Finance and other public endpoints under their terms of service.

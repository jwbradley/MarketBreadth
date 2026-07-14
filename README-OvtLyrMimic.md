# OvtLyrMimic — Nine Rules Analysis

Python checklist inspired by publicly discussed OVTLYR-style “nine rules” ideas.  
**v3** evaluates rules through **`ta_indicators.py`**—the same math as `stock_screener.py`.

This tool is a **short-list gate**, not a full-universe scanner. Prefer feeding it `ovtlyr_watchlist.json` from the screener.

---

## What it does

For each ticker, evaluates nine rules and maps the pass count to a signal:

| Rules passed | Signal | Informal reading |
|--------------|--------|------------------|
| 8–9 / 9 | STRONG BUY | Most checklist items aligned |
| 6–7 / 9 | BUY | Mostly positive |
| 4–5 / 9 | NEUTRAL | Mixed |
| 0–3 / 9 | SELL/AVOID | Multiple failures |

These labels are **checklist summaries**, not promises of profit. See [DISCLAIMER.md](DISCLAIMER.md).

---

## The nine rules

| Rule | Name | Check (shared implementation) |
|------|------|-------------------------------|
| 1 | Trend confirmation | Price > 10 EMA > 20 EMA > 50 EMA |
| 2 | Signal alignment | Price above 20 EMA + 5-day price rising |
| 3 | Market breadth | S&P % above 50-DMA ≥ 50% (from breadth JSON) |
| 4 | Sector strength | Sector % above 50-DMA ≥ 50% |
| 5 | Behavioral sentiment | Wilder RSI between 40 and 70 |
| 6 | Liquidity / volume | Volume &gt; 80% of 20-day average |
| 7 | Position sizing (ATR) | ATR &lt; 8% of price |
| 8 | Multi-timeframe | Price above 20 EMA and 100 EMA |
| 9 | No contradictions | No bearish divergence flag |

Details and library API: [README-ta_indicators.md](README-ta_indicators.md).

---

## Requirements

```bash
pip install yfinance pandas numpy
```

Optional but recommended:

- `market_breadth_latest.json` — real market/sector breadth for rules 3–4  
- `ovtlyr_watchlist.json` — from `stock_screener.py --watchlist`  
- `sp500_constituents.csv` — sector map for bare `--tickers` mode  

Without breadth files, market breadth may fall back to a crude SPY-vs-EMA proxy; sector breadth may fail closed if unknown.

---

## Usage

### From screener watchlist (recommended)

```bash
python3 market_breadth_collector.py
python3 stock_screener.py --sectors 3
python3 stock_screener.py --watchlist
python3 OvtLyrMimic.py
python3 OvtLyrMimic.py --briefing
```

### Manual tickers

```bash
python3 OvtLyrMimic.py --tickers AAPL MSFT NVDA AMD TSLA
```

### Custom watchlist path

```bash
python3 OvtLyrMimic.py --watchlist /path/to/my_watchlist.json
```

### Verbose rule detail

```bash
python3 OvtLyrMimic.py --verbose
```

---

## Watchlist JSON

Produced by the screener; minimum useful shape:

```json
{
  "generated": "2026-07-14 08:00:00",
  "source_date": "2026-07-13",
  "market_breadth_pct": 66.0,
  "stocks": [
    {
      "ticker": "ES",
      "sector": "Utilities",
      "sector_type": "top",
      "score": 100,
      "signal": "Momentum Buy",
      "rules_passed": 9,
      "sector_breadth_pct": 90.3,
      "rs_vs_spy": 7.72
    }
  ]
}
```

Only `ticker` is strictly required per stock; `sector` / `sector_breadth_pct` improve rule 4.

---

## Integration with the screener

| Concern | Behavior |
|---------|----------|
| Indicators | Same `calculate_from_ohlcv` |
| Rules | Same `evaluate_nine_rules` |
| RS vs SPY | Shared `relative_strength` |
| History length | 1y preferred (aligns with SMA200 / EMA100) |

If counts differ, re-run the screener watchlist after a code change and confirm both import the same `ta_indicators.py`.

---

## Output modes

| Mode | Description |
|------|-------------|
| Default | Summary table + signal distribution |
| `--briefing` | Markdown table for daily logs |
| `--verbose` | Per-rule pass/fail details |

The daily bash orchestrator appends `OvtLyrMimic.py --briefing` after screener opportunities.

---

## How to use the signals (operational)

- **STRONG BUY / BUY** on the watchlist → candidates that cleared both score filter and checklist; still apply your own risk rules.  
- **NEUTRAL** → no edge claimed by the checklist.  
- **SELL/AVOID** → multiple dimensions failing; do not force a long from a high screener score alone without re-reading sector context.  

For day-to-day workflow tips: [BEST_PRACTICES.md](BEST_PRACTICES.md).

---

## Companion scripts

| Script | Purpose |
|--------|---------|
| `market_breadth_collector.py` | Breadth for rules 3–4 |
| `stock_screener.py` | Scores + watchlist |
| `ta_indicators.py` | Shared math |
| `getTodaysStockScreenerData.sh` | Cron pipeline |

---

## Disclaimer

This software is for **educational and informational purposes only**. It is **not** investment advice.

- These tools are **not guaranteed to make money**.
- **Past performance is not indicative of future results.**
- Checklist labels such as “STRONG BUY” or “SELL/AVOID” are **not guarantees** of future prices or outcomes.
- The name “OvtLyr” / OVTLYR refers to publicly discussed rule *concepts* for interoperability and education; this project is an independent implementation and is not affiliated with any commercial product unless explicitly stated.
- You alone are responsible for your decisions. Data may be delayed or incorrect.

**Full text:** [DISCLAIMER.md](DISCLAIMER.md)

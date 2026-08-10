# Nine Rules Gate & Independent Scan

Educational **multi-factor technical checklist** used as a short-list gate after sector breadth and the stock screener.

| Script | Role |
|--------|------|
| `nine_rules_gate.py` | Funnel gate: score the screener watchlist (same TA math as the screener) |
| `nine_rules_independent.py` | Independent re-score: core book ∪ personal file ∪ watchlist ∪ CLI |

Both use **`ta_indicators.py`** when available so rule counts stay aligned with `stock_screener.py`.

After the nine rules, the gate can also report **IV-based expected move** (1-sigma) from the nearest listed options expiration (ATM IV via Yahoo). See [Expected-Move-Guide.md](Expected-Move-Guide.md).

Prefer feeding the gate `nine_rules_watchlist.json` from `stock_screener.py --watchlist`.

**Windows note:** CLI formula / header strings use ASCII (`sqrt()`, `1-sigma`, `-`) so redirecting to a log under cp1252 does not raise `UnicodeEncodeError`. See [CHANGELOG.md](CHANGELOG.md).

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
- `nine_rules_watchlist.json` — from `stock_screener.py --watchlist`  
- `sp500_constituents.csv` — sector map for bare `--tickers` mode  

Without breadth files, market breadth may fall back to a crude SPY-vs-EMA proxy; sector breadth may fail closed if unknown.

---

## Usage — gate (`nine_rules_gate.py`)

### From screener watchlist (recommended)

```bash
python3 market_breadth_collector.py
python3 stock_screener.py --sectors 3
python3 stock_screener.py --watchlist
python3 nine_rules_gate.py
python3 nine_rules_gate.py --briefing
```

### Manual tickers

```bash
python3 nine_rules_gate.py --tickers AAPL MSFT NVDA AMD TSLA
```

### Custom watchlist path

```bash
python3 nine_rules_gate.py --watchlist /path/to/my_watchlist.json
```

### Verbose / skip options

```bash
python3 nine_rules_gate.py --verbose
python3 nine_rules_gate.py --no-expected-move
python3 nine_rules_gate.py --no-cache          # bypass shared OHLCV disk cache
```

---

## Usage — independent (`nine_rules_independent.py`)

Re-scores a layered universe without requiring a fresh screener run:

```bash
# Core book only (plus personal tickers.txt if present)
python3 nine_rules_independent.py

# Core ∪ screener watchlist (daily pipeline mode)
python3 nine_rules_independent.py --union-watchlist --briefing --no-expected-move

# Screener watchlist only
python3 nine_rules_independent.py --watchlist-only --verbose

# Ad-hoc
python3 nine_rules_independent.py --tickers SMCI ARM TSM
python3 nine_rules_independent.py --file my_tickers.txt

# Bypass shared OHLCV disk cache (soft-imported; safe if market_cache is absent)
python3 nine_rules_independent.py --union-watchlist --no-cache
```

Daily runners write the independent report to `logs/nine_rules_independent.log`.

---

## Expected move (IV)

After nine-rules analysis, ATM IV is pulled from listed expirations (DTE ≥ 1), **nearest first**, skipping chains with unusable IV (Yahoo often returns ~0% on thin/near-dated quotes). Up to five expirations are tried.

| Field | Formula / source |
|-------|------------------|
| IV | ATM call (or put) `impliedVolatility` (reject &lt; 5% or &gt; 500%) |
| Daily 1σ | `Price × IV / √252` |
| Weekly 1σ | `Price × IV × √5 / √252` |
| To expiration | `Price × IV × √DTE / √252` |

Price comes from the shared TA snapshot (same close used for rules). Results appear under both default summary and `--briefing`. Use `--no-expected-move` to skip the options chain when offline or rate-limited.

Expected move is a **range scale**, not a direction signal, and is not a guarantee of realized volatility.

---

## Watchlist JSON

Produced by the screener (`nine_rules_watchlist.json`); minimum useful shape:

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

Readers still accept the legacy filename `ovtlyr_watchlist.json` if the new file is missing (temporary compatibility).

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

## Output modes (gate)

| Mode | Description |
|------|-------------|
| Default | Summary table + signal distribution |
| `--briefing` | Markdown table for daily logs |
| `--verbose` | Per-rule pass/fail details |
| `--no-expected-move` | Skip ATM IV / expected-move options fetch |
| `--no-cache` | Bypass shared OHLCV disk cache ([README-market_cache.md](README-market_cache.md)) |

The daily orchestrators (`getTodaysStockScreenerData.sh` / `getStockScreenerData.bat`) append `nine_rules_gate.py --briefing` after screener opportunities, then run `nine_rules_independent.py` for an independent re-score.

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
| `ta_indicators.py` | Shared TA math |
| `market_cache.py` | Shared TTL OHLCV cache (soft import in independent) |
| `nine_rules_independent.py` | Independent re-score + core∪watchlist overlap |
| `earnings_expected_move.py` | Earnings straddle report (separate from nearest-expiry EM) |
| `getTodaysStockScreenerData.sh` | Cron pipeline (Linux/macOS) |
| `getStockScreenerData.bat` | Task Scheduler pipeline (Windows) |

---

## Naming note

Earlier releases used filenames that referenced a commercial charting product. This toolkit is an **independent educational implementation** of a common multi-factor technical checklist. It is **not affiliated with, endorsed by, or a reproduction of** any third-party commercial platform.

---

## Disclaimer

This software is for **educational and informational purposes only**. It is **not** investment advice.

- These tools are **not guaranteed to make money**.
- **Past performance is not indicative of future results.**
- Checklist labels such as “STRONG BUY” or “SELL/AVOID” are **not guarantees** of future prices or outcomes.
- You alone are responsible for your decisions. Data may be delayed or incorrect.

**Full text:** [DISCLAIMER.md](DISCLAIMER.md)

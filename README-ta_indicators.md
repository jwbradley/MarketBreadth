# ta_indicators — Shared Technical Analysis Library

Single source of truth for indicator math used by `stock_screener.py` and `nine_rules_gate.py`.  
Keeping both tools on this module prevents silent score/rule disagreements.

---

## Why it exists

Previously the screener and nine-rules gate each recomputed RSI, EMAs, ATR, and divergence with small differences (lookback periods, EMA `adjust` flags, divergence thresholds). Option C extracts that math into one library.

---

## What it provides

| API | Purpose |
|-----|---------|
| `ema`, `sma` | Moving averages (`ema` uses `adjust=False`) |
| `rsi_wilder` | Wilder RSI (industry-standard smoothing) |
| `macd` | MACD line, signal, histogram |
| `bollinger_pct` | Bollinger %B |
| `atr` | Average True Range |
| `relative_strength` | Return vs benchmark over N days |
| `detect_divergences` | Simple price/RSI 5-day divergence flags |
| `calculate_from_ohlcv` | Full indicator dict from a history DataFrame |
| `evaluate_nine_rules` | multi-factor technical 9 rules from an indicator dict |
| `nine_rules_signal` | Map rules-passed count → STRONG BUY / BUY / NEUTRAL / SELL/AVOID |
| `sector_composite_score` | Multi-metric sector strength from breadth JSON |
| `rank_sectors` | Top/bottom sector names by composite score |

---

## Nine rules (shared)

| Rule | Check |
|------|--------|
| 1 | Price > 10 EMA > 20 EMA > 50 EMA |
| 2 | Price above 20 EMA and 5-day price rising |
| 3 | Market % above 50-DMA ≥ 50 (from breadth collector) |
| 4 | Sector % above 50-DMA ≥ 50 |
| 5 | RSI between 40 and 70 |
| 6 | Volume ratio > 0.8× 20-day average |
| 7 | ATR &lt; 8% of price |
| 8 | Price above 20 EMA and 100 EMA |
| 9 | No bearish divergence flag |

Rules 3 and 4 **fail closed** if breadth context is missing (they do not invent “always pass”).

---

## Sector composite score

Weights used by `rank_sectors` / `sector_composite_score`:

| Component | Weight |
|-----------|--------|
| % above 50-DMA | 35% |
| Breadth thrust | 20% |
| A/D ratio (mapped) | 20% |
| Up/down volume ratio (mapped) | 15% |
| Net 52-week highs − lows (mapped) | 10% |

This is intentionally smoother than sorting sectors by **one-day A/D alone**.

---

## Usage (library)

```python
from ta_indicators import calculate_from_ohlcv, evaluate_nine_rules, rank_sectors
import yfinance as yf

hist = yf.Ticker("AAPL").history(period="1y", auto_adjust=True)
spy = yf.Ticker("SPY").history(period="1y", auto_adjust=True)["Close"]

ind = calculate_from_ohlcv(hist, spy_close=spy)
rules = evaluate_nine_rules(ind, market_breadth_pct=60.0, sector_breadth_pct=55.0)
print(ind["rsi"], rules["rules_passed"])
```

There is no CLI; import from the sibling scripts or your own tools.

---

## Design notes

- Prefer **one** `calculate_from_ohlcv` call per ticker per day; pass the resulting dict into scoring and rules.
- Minimum bars default for full snapshot: **200** (SMA200 / long EMAs). Callers may lower `min_bars` for short histories.
- RSI is **Wilder**, not a simple rolling mean of gains/losses.

---

## Related

- [README-stock_screener.md](README-stock_screener.md)
- [README-nine_rules.md](README-nine_rules.md)
- [BEST_PRACTICES.md](BEST_PRACTICES.md)

---

## Disclaimer

This software is for educational and informational purposes only. It is **not** investment advice and is **not guaranteed to make money**. **Past performance and historical indicators are not indicative of future prices or results.** You alone are responsible for your decisions. Market data may be delayed or wrong. See [DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer.

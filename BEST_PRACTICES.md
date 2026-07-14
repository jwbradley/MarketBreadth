# Best Practices

Practical guidance for running the Market Breadth suite so results are more reliable and easier to interpret. This is operational advice, not investment advice. See [DISCLAIMER.md](DISCLAIMER.md).

---

## 1. Treat the pipeline as a funnel

```
Regime / macro context  →  Sector breadth  →  Stock candidates  →  Nine-rules gate
```

| Layer | Tool | Use it for |
|-------|------|------------|
| Macro (optional) | GoldenRatios collectors | Risk-on / metals regime context |
| Sector map | `market_breadth_collector.py` | Where participation is strong or weak |
| Candidates | `stock_screener.py` | Who looks interesting *inside* those sectors |
| Checklist | `OvtLyrMimic.py` | Binary pass/fail on a short watchlist |

Do not skip straight to “Strong Buy” labels without reading sector and market breadth first.

---

## 2. Prefer one clean post-close run

- US cash equity session closes **16:00 ET** (15:00 CT).
- Yahoo Finance and similar feeds often need **30–90 minutes** to settle official daily bars.
- Prefer a daily job around **16:30–17:45 CT** (or local equivalent after your market’s close).
- Morning runs (e.g. 07:30 / 08:30) are useful as a **re-report of the prior close**, not as “today’s open edge.”

If the latest bar date is not the session you expect, treat labels as stale until the next successful collect.

---

## 3. Use the shared indicator path

- `stock_screener.py` and `OvtLyrMimic.py` both use **`ta_indicators.py`**.
- Do not fork a second RSI/MACD implementation in ad-hoc scripts; scores and rules will diverge.
- If you change indicator math, change it once in `ta_indicators.py` and re-run both tools.

---

## 4. Interpret signals by thesis

| Signal style | Typical context | How to use |
|--------------|-----------------|------------|
| **Momentum Buy** | Strong sector, trend aligned, RS positive | Primary long watchlist focus |
| **Buy / Neutral / Weak** | Mixed technicals | Size down or wait |
| **Reversal Watch** | Weak sector, washout / divergence cues | Secondary; needs confirmation |
| **RS in Weak Sector** | Stock outperforming while sector is weak | Leadership candidate or short-avoid list—not the same as momentum |

Primary daily focus should be **momentum names in strong sectors**. Weak-sector setups are optional and different trades.

---

## 5. Liquidity and universe

- Default liquidity floor: **$20M** average dollar volume (20-day). Override with `SCREENER_MIN_DOLLAR_VOL` if needed.
- Universe is **S&P 500 constituents** (auto-refreshed monthly). Mid/small-cap opportunities are out of scope unless you extend the list.
- Alphabet order is **not** used for “top stocks”; ranking is RS + liquidity. Trust the pre-rank step.

---

## 6. Sector ranking is multi-metric

Sectors are ranked by a **composite** (participation, thrust, A/D, up/down volume, net highs/lows)—not a single noisy 1-day A/D print.

Still:

- One day of strong breadth can reverse the next session.
- Prefer multi-day history (`market_breadth_history.json` / CSV) for trend of breadth, not only `*_latest.json`.

---

## 7. Keep the watchlist short

- Export with `stock_screener.py --watchlist` (score floor, top per sector).
- Run `OvtLyrMimic.py` on that list, not the entire S&P 500.
- If more than ~15–20 names pass, raise the score threshold or restrict to top-sector only.

---

## 8. Orchestration (Linux shell vs Windows batch)

Keep orchestrators thin; keep Python modules separate (Option C).

| | Linux / macOS | Windows |
|--|---------------|---------|
| Runner | `getTodaysStockScreenerData.sh` | `getStockScreenerData.bat` |
| Typical schedule | cron | Task Scheduler |
| Soft-fail per step | Yes | No (inspect the log after the run) |
| Virtualenv | Activates `GoldenRatios/.venv` when present | Uses `python` on `PATH` |
| Log location | `logs/todaysMarketBreadth.log` (+ `logs/errors.log`) | Path in `LOG=` at the top of the `.bat` (**edit this** before first use) |
| Layout assumption | Runs from KSI parent (`MarketBreadth/` + `GoldenRatios/`) | You start in (or `cd` to) a directory where the listed `.py` files resolve |

Suggested report order (already in both runners):

1. Macro / ratios status  
2. Breadth briefing  
3. **Best opportunities** (`--opportunities`)  
4. Full screener briefing  
5. OvtLyr gate (`--briefing`)  
6. OvtLyrMimic4 independent re-score (`--union-watchlist`)

Linux: non-zero exit count from the shell script means at least one step failed—wire that to monitoring if you care about uptime. Windows: open the configured log and confirm every “Running:” step completed.

### ASCII-safe CLI output (Windows)

On many Windows installs, Python 3.12 writes stdout as **cp1252**. Characters outside that set (em dash, arrows, √, σ, etc.) can crash a redirected run with `UnicodeEncodeError`. Prefer plain ASCII in **`print()` and argparse descriptions** (`-`, `->`, `sqrt()`, `1-sigma`). Markdown guides may still use Unicode.

---

## 9. Risk management outside the scripts

These tools **do not**:

- Size positions  
- Place orders  
- Enforce stops  
- Account for taxes, dividends, or borrow fees  

Use ATR% and liquidity as **inputs** to your own risk rules. Cap risk per name and per day independently of any score.

---

## 10. Data hygiene

- Refresh constituents if the list is stale (`market_breadth_collector.py --update-constituents`).
- Do not commit large history JSON/CSV or personal logs to a public repo (see `.gitignore`).
- Respect Yahoo Finance (and any other provider) rate limits and terms of service.
- Re-run after holidays; empty or weekend data is expected to look odd.

---

## 11. Validation before trusting a change

After editing indicators or scores:

1. `python3 -m py_compile ta_indicators.py stock_screener.py OvtLyrMimic.py OvtLyrMimic4.py market_breadth_collector.py`
2. Run breadth collect once.
3. Run screener on one sector (`--sector "Utilities" --top-stocks 5`).
4. Confirm `rules_passed` on the same ticker matches between screener output and `OvtLyrMimic.py`.
5. On Windows: redirect a briefing to a file and confirm no `UnicodeEncodeError`.
6. Only then run the full daily script (`.sh` or `.bat`).

---

## 12. What not to do

- Do not treat composite score 100 or “STRONG BUY” as certainty.
- Do not average contradictory systems (mean-reversion + trend) into one action without labeling the thesis.
- Do not hardcode secrets or paid API keys into the repo.
- Do not present outputs as personalized financial advice when sharing publicly.

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [README.md](README.md) | Project overview and pipeline |
| [README-stock_screener.md](README-stock_screener.md) | Screener details |
| [README-OvtLyrMimic.md](README-OvtLyrMimic.md) | Nine rules tool |
| [README-ta_indicators.md](README-ta_indicators.md) | Shared indicator library |
| [DISCLAIMER.md](DISCLAIMER.md) | Legal / risk disclaimer |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

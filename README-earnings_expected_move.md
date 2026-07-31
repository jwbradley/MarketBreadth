# Earnings Expected Move — Straddle-Implied Move for Upcoming Reports

Finds the stocks reporting quarterly earnings over the next few trading sessions and prices the **ATM straddle on the first option expiration after the report** to show the move the options market has priced in. Compares that implied move against the stock's own realized earnings-move history so you can see whether options look rich or cheap going into the event.

Implements the "Straddle Shortcut" from `Documents\MarketNews\Expected-Move-Guide.md` §6, applied specifically to earnings events (§C, "Earnings Plays").

---

## Why This Exists (and how it differs from `nine_rules_gate.py`)

`nine_rules_gate.py` already reports a 1-sigma expected move — but from the **nearest** option expiration. For an earnings play that is the wrong contract: if a stock reports after Monday's close, a Friday-expiring straddle measured on the expiration *before* the report contains none of the earnings move.

Measured on PLTR (reported after the close on 2026-08-03):

| Expiration used | Straddle | Implied move |
|---|---|---|
| Nearest expiry (`2026-07-31`, pre-earnings) | $0.21 | **0.17%** |
| First expiry after earnings (`2026-08-07`) | $14.00 | **11.38%** |

A ~67x difference. This tool always selects an expiration that contains the report.

---

## Requirements

```bash
pip install yfinance pandas numpy
```

Optional inputs (used to filter the calendar down to names you follow):
- `sp500_constituents.csv` — also supplies GICS sector
- `nine_rules_watchlist.json` — from `stock_screener.py --watchlist`

If neither exists the tool warns and falls back to the full calendar.

---

## Usage

```bash
# Next 3 trading sessions, S&P 500 + watchlist names
python3 earnings_expected_move.py

# Just the next 2 sessions
python3 earnings_expected_move.py --sessions 2

# Specific tickers (falls back to Yahoo for the report date if outside the window)
python3 earnings_expected_move.py --tickers PLTR VRTX

# Every name on the calendar, no universe filter
python3 earnings_expected_move.py --all-calendar

# Large caps only (billions)
python3 earnings_expected_move.py --all-calendar --min-market-cap 10

# Markdown briefing (used by getStockScreenerData.bat)
python3 earnings_expected_move.py --briefing

# Faster: skip the realized-move lookback
python3 earnings_expected_move.py --no-history

# Machine-readable
python3 earnings_expected_move.py --json
```

### Options

| Flag | Effect |
|---|---|
| `--sessions N` | Trading sessions ahead to scan (default 3; skips weekends/holidays) |
| `--tickers ...` | Ad-hoc tickers, bypassing the universe filter |
| `--all-calendar` | Do not filter to S&P 500 + watchlist |
| `--min-market-cap B` | Drop names below B billions |
| `--limit N` | Cap tickers analyzed |
| `--include-reported` | Keep names whose earnings already printed (default: dropped) |
| `--no-history` | Skip the realized earnings-move lookback |
| `--briefing` | Markdown table instead of plain text |
| `--json` | JSON to stdout |
| `--no-save` / `--output PATH` | Control the `earnings_expected_move_latest.json` snapshot |
| `--verbose` | Per-ticker progress |

---

## How It Works

1. **Calendar** — pulls the Nasdaq earnings calendar per session, which uniquely supplies the pre-market / after-hours timing.
2. **Drops already-reported names** — a pre-market reporter is done once the open passes; an after-hours reporter once the close does (checked in ET). Without this, an evening run would list names that moved that morning as upcoming.
3. **Universe filter** — intersects with S&P 500 + your watchlist.
4. **Expiration selection** — the core step:
   ```
   event date = report date + 1 session   (after-hours reporters move the NEXT session)
              = report date               (pre-market; unknown treated as pre-market, the
                                           conservative choice — never misses the move)
   expiration = first listed expiration >= event date
   ```
5. **Straddle pricing** — ATM strike chosen from strikes listed on *both* sides, so the legs form a real straddle. Each leg uses bid/ask mid, falling back to `lastPrice`.
6. **IV cross-check** — reuses `get_expected_move()` from `nine_rules_gate.py`, scaled over the same horizon in **trading** days to match the `sqrt(252)` basis.
7. **Realized history** — absolute close-to-close move around each of the last ~8 reports; reports outside available history are skipped rather than guessed.

---

## Reading the Output

```
Ticker Report      When       Spot         Exp   Strdl    Implied               Range   IVchk  HistAvg  Verdict  Quality
PLTR   2026-08-03  AMC     $123.06  2026-08-07  $14.00  +/-11.38%     $109.00-$137.00   13.7%     4.7%     RICH     GOOD
```

- **When** — `BMO` pre-market · `AMC` after-hours · `?` unknown
- **Implied** — straddle ÷ spot: the ~1-sigma (~68%) move priced in
- **Range** — straddle breakevens; profit for a buyer requires exceeding them
- **IVchk** — independent IV-formula estimate; a large divergence warrants a look
- **HistAvg** — average absolute move over the last ~8 reports

### Verdict

| Value | Meaning |
|---|---|
| `RICH` | Implied > 1.2× avg realized — options look expensive (favors selling premium) |
| `CHEAP` | Implied < 0.8× avg realized — options look cheap (favors buying) |
| `PRICED` | Implied roughly in line with history |
| `DILUTED` | No expiration within 9 days of the report, so the straddle also prices weeks of ordinary vol — **not** comparable to a single-day earnings move. Shown as `+Nd` on the expiration. |
| `N/A` | No usable earnings history |

### Quality

| Value | Meaning |
|---|---|
| `GOOD` | Both legs had two-sided quotes |
| `WIDE` | Bid/ask spread > 25% of mid — treat the number loosely |
| `STALE` | Fell back to `lastPrice`; typical outside market hours |
| `IV_ONLY` | No usable quotes; the IV estimate is the only read |
| `NO_DATA` / `ERROR` | No price/chain, or a fetch failure (see `note` in the JSON) |

**Rows are never silently dropped** — an unusable quote is labeled, not hidden.

---

## Timing Matters

Straddle mids are only meaningful while the options market is quoting. The 7:00 AM batch run happens pre-open, so expect `STALE`/`WIDE` on many rows — honest reporting, not a bug, and `IVchk` is the fallback read. For live pricing, run mid-session.

---

## Integration

Wired into `getStockScreenerData.bat`, appending a markdown section to
`Documents\MarketNews\todayStockScreener.log`:

```bat
@python earnings_expected_move.py --briefing >> "%LOG%"
```

Also writes `earnings_expected_move_latest.json` (`stocks[]` with full straddle legs, per-report realized moves, and quality/verdict fields) for downstream use.

---

## Caveats

- The Nasdaq calendar is an **undocumented endpoint** requiring a browser User-Agent. If it changes or 403s, the tool logs a warning and degrades to `--tickers` / Yahoo per-ticker rather than failing the batch run.
- Expected move is **~1-sigma and directionless** — roughly a 68% chance of landing inside the range, no indication of which way, and no guarantee of realized range.
- Implied vs realized is context, not a signal. Options are often "rich" into earnings for good reason; sellers carry the tail risk.
- A single expiration always contains some non-earnings vol; `DILUTED` flags only the worst cases.
- US market holidays are a static set covering 2026–2027 (no `pandas_market_calendars` dependency); extend `MARKET_HOLIDAYS` beyond that.

---

## Related

- `Documents\MarketNews\Expected-Move-Guide.md` — methodology (§6 straddle, §C earnings plays)
- `nine_rules_gate.py` — general expected move (nearest expiration); source of the shared IV math
- `stock_screener.py --watchlist` — produces `nine_rules_watchlist.json`

# Earnings Expected Move — Straddle-Implied Move for Upcoming Reports

Finds stocks reporting quarterly earnings over the next few trading sessions and
answers a practical question:

> **How big a stock move has the options market already priced in around this earnings report?**

It does that by pricing an **ATM straddle** on the **first option expiration after the
report**, then compares that “implied” move to the stock’s own history of earnings-day
moves so you can see whether options look **rich** (expensive), **cheap**, or roughly
**priced** versus how this name usually behaves.

Implements the “Straddle Shortcut” from `Documents\MarketNews\Expected-Move-Guide.md`
§6, applied specifically to earnings events (§C, “Earnings Plays”).

This README is written for readers who do not live in options jargon every day. Terms
are defined in plain language first; the math and integration details follow.

---

## What problem this solves (one picture)

Stocks often jump or drop hard when they report earnings. Options traders price that
uncertainty **before** the report. If you buy both a call and a put near the current
stock price (a **straddle**), the combined cost of those two options is a market-based
estimate of “how far this stock is expected to move by expiration.”

Divide that cost by the stock price and you get the **implied move** as a percentage —
the table’s **Implied +/-** column.

This tool is **not** a buy/sell recommendation. It is a **pricing tape** for upcoming
earnings: what the market is charging for the event, and how that compares to history.

---

## Options terms used in this tool (glossary)

You do not need to trade options to read the table, but these words show up in every
column explanation.

| Term | Plain meaning |
|------|----------------|
| **Underlying / Spot** | The stock itself, and its current (or last) price. Everything is measured against this. |
| **Call option** | Contract that gains value if the stock **rises**. Buying a call is a bullish bet (with limited loss = premium paid). |
| **Put option** | Contract that gains value if the stock **falls**. Buying a put is a bearish / protective bet. |
| **Strike** | The price level built into the option contract. A $100 strike call cares about the stock relative to $100. |
| **ATM (at-the-money)** | Strike closest to the current stock price. ATM options are the usual choice for measuring “how much move is priced in.” |
| **Expiration (Exp)** | The date the option contract ends. After expiration it is worthless or settled; before that, time and events (like earnings) affect its price. |
| **Premium** | What you pay for the option (or receive if you sell it). In this tool, call premium + put premium ≈ **Straddle** cost. |
| **Bid / Ask** | Bid = highest price buyers are offering. Ask = lowest price sellers want. The gap is the **spread**. Wide spreads mean the “fair” price is fuzzy. |
| **Mid** | Average of bid and ask — a common estimate of “where it would trade if spreads were tight.” |
| **Last price** | Last trade that actually printed. Useful when markets are closed, but can be **stale** (hours old). |
| **Straddle** | Own **one ATM call + one ATM put** with the **same strike and expiration**. You profit if the stock moves a lot **either way** (up *or* down) by more than the total premium paid. Direction does not matter; **size** of move does. |
| **Implied move** | Roughly: *straddle cost ÷ stock price*. Read as “the market is pricing about ±X% by this expiration.” |
| **1-sigma (~68%)** | Under a normal-distribution mental model, about two-thirds of outcomes fall inside ±1 standard deviation. Options “expected move” quotes are often framed this way. It is a rule of thumb, **not a guarantee**. |
| **IV (implied volatility)** | The volatility “baked into” option prices. Higher IV → options cost more → larger implied moves. This tool’s main number is the **straddle**, not IV itself; **IV chk** is only a cross-check. |
| **Realized move** | What the stock **actually did** in the past (here: absolute % change around prior earnings). History, not a forecast. |
| **Rich / Cheap** | Loose trader slang: **rich** = options look expensive vs history (implied ≫ typical realized); **cheap** = options look inexpensive vs history. Not moral judgments — relative pricing labels. |
| **Diluted (in this tool)** | The only usable expiration is so far after earnings that the straddle also prices **many ordinary days** of stock movement, not just the earnings jump. Comparing that fat number to a one-day historical average would be misleading. |

### Why a straddle for earnings?

- Earnings can gap **up or down**. A straddle does not require you to guess direction.
- The **combined premium** is a market consensus for “how large the reaction might be.”
- If you *bought* the straddle, you need the stock to move outside the **Expected Range**
  (roughly strike ± straddle cost) by expiration to break even before commissions —
  that is why the range is useful context, not a forecast of where the stock will land.

---

## Why this exists (and how it differs from `nine_rules_gate.py`)

`nine_rules_gate.py` already reports a 1-sigma expected move — but from the
**nearest** option expiration on the chain.

For an earnings play that is often the **wrong** contract:

- Stock reports **after Monday’s close**.
- There is still a **Friday expiration that lands *before*** that report.
- A straddle on that pre-report Friday may be nearly worthless for the earnings event
  because the big move has not happened yet *inside that contract’s life*.

Measured on PLTR (reported after the close on 2026-08-03):

| Expiration used | Straddle | Implied move |
|---|---|---|
| Nearest expiry (`2026-07-31`, pre-earnings) | $0.21 | **0.17%** |
| First expiry after earnings (`2026-08-07`) | $14.00 | **11.38%** |

A ~67× difference. **This tool always selects an expiration that still includes the report
(and the first session that can fully show the reaction).**

---

## Requirements

On this Linux host the daily pipeline uses the **shared** venv at
`~/myPrograms/KSI/GoldenRatios/.venv` (not system Python). System `pip install`
will hit PEP 668 / “externally-managed-environment” errors.

```bash
cd ~/myPrograms/KSI
source GoldenRatios/.venv/bin/activate

# Preferred: keep the venv’s requirements list complete
pip install -r GoldenRatios/requirements.txt
pip install lxml   # required for Yahoo earnings-date history (Hist Avg / Verdict)

# Or minimal set for this tool alone
pip install yfinance pandas numpy lxml
```

**`lxml` matters:** without it, Yahoo’s `get_earnings_dates()` fails, history is
skipped quietly, and every **Hist Avg** / **Verdict** cell shows `N/A` even though
straddles still price. Install `lxml` into the **same venv** the script uses.

Optional inputs (used to filter the calendar down to names you follow):

- `sp500_constituents.csv` — also supplies GICS sector  
- `nine_rules_watchlist.json` — from `stock_screener.py --watchlist`

If neither exists the tool warns and falls back to the full calendar.

---

## Usage

Always prefer the project venv’s Python on Linux:

```bash
cd ~/myPrograms/KSI
GoldenRatios/.venv/bin/python3 MarketBreadth/earnings_expected_move.py --briefing
```

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

# Markdown briefing (used by the daily .bat / .sh pipelines)
python3 earnings_expected_move.py --briefing

# Faster: skip the realized-move lookback (Hist Avg / Verdict become N/A)
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

## How it works (pipeline)

1. **Calendar** — pulls the Nasdaq earnings calendar per session (includes pre-market /
   after-hours timing when available).
2. **Drops already-reported names** — a pre-market reporter is “done” once the open
   passes; an after-hours reporter once the close does (checked in US/Eastern). Without
   this, an evening run would still list names that already moved that morning.
3. **Universe filter** — intersects with S&P 500 + your watchlist (unless
   `--all-calendar` / `--tickers`).
4. **Expiration selection** — the core step:
   ```
   event date = report date + 1 session   (after-hours: stock’s full reaction often prints NEXT session)
              = report date               (pre-market; unknown treated as pre-market —
                                           conservative so the move is not missed)
   expiration = first listed expiration on/after that event date
   ```
5. **Straddle pricing** — ATM strike chosen from strikes listed on *both* the call and
   put side (a real matching pair). Each leg uses bid/ask mid when possible, else last
   trade.
6. **IV cross-check** — reuses `get_expected_move()` from `nine_rules_gate.py`, scaled
   over the same horizon in **trading** days (`sqrt(252)` style). This is **IV chk**,
   not the primary number.
7. **Realized history** — for each of the last ~8 past reports, absolute close-to-close
   % move around the event; average becomes **Hist Avg**. Needs working Yahoo earnings
   dates (**`lxml` required**).

---

## Reading the output

Example (`--briefing`):

```
## Earnings Expected Move - 2026-08-05 to 2026-08-07

| Ticker | Report     | When |    Spot |             Exp | Straddle | Implied +/- |      Expected Range | IV chk | Hist Avg | Verdict | Quality |
| AKAM   | 2026-08-06 | AMC  | $122.27 |      2026-08-07 |   $17.70 |   +/-14.48% |   $104.30 - $139.70 |  18.3% |     1.5% | RICH    | WIDE    |
| DDOG   | 2026-08-06 | BMO  | $283.17 |      2026-08-07 |   $37.92 |   +/-13.39% |   $244.57 - $320.43 |  16.7% |    10.5% | RICH    | GOOD    |
| ZTS    | 2026-08-06 | BMO  |  $74.39 | 2026-08-21 +15d |    $9.10 |   +/-12.23% |     $65.90 - $84.10 |  15.8% |     7.7% | DILUTED | GOOD    |
```

Column widths are padded so the table is readable as plain text in the daily log
(same idea as `nine_rules_gate.py --briefing`).

### Column reference (every field)

| Column | What it is | How to read it |
|--------|------------|----------------|
| **Ticker** | Stock symbol | The company reporting. |
| **Report** | Calendar earnings **date** | Day of the scheduled report (not always the day the stock fully reacts — see **When**). |
| **When** | Time of day of the report | **`BMO`** = before the market open (pre-market). **`AMC`** = after the market close (after-hours). **`?`** = calendar did not say; treated conservatively like pre-market for event timing. |
| **Spot** | Stock price used in the math | Current/last underlying price. Implied % and range are built from this. |
| **Exp** | Option **expiration** used for the straddle | First listed expiry on/after the event date. If you see `2026-08-21 +15d`, that means the expiry is **15 calendar days after** the event — often flagged **DILUTED** because lots of non-earnings time is in that premium. |
| **Straddle** | Dollar cost of ATM call + ATM put | Cash premium for the pair. Higher $ can still be a small % on a high-priced stock — always look at **Implied +/-** too. |
| **Implied +/-** | Straddle ÷ Spot, as a percent | Primary “expected move” number: market is pricing about **± this %** by that expiration (~1-sigma framing). Direction is **unknown**. |
| **Expected Range** | Rough breakeven band for a long straddle | Approximately strike − straddle to strike + straddle (shown as dollar prices). A pure long-straddle buyer needs a move **outside** this band (before costs) to profit; it is **not** a prediction of where the stock will close. |
| **IV chk** | Independent IV-based expected move | Sanity check only. Uses ATM IV on the *nearest* listed expiration (often still the **pre-report** contract on earnings names), so it often prints **lower** than the straddle. A large gap is **normal**. Trust **Implied +/-** for earnings; use IV chk to spot rows that look absurd. |
| **Hist Avg** | Average of past earnings-day absolute moves | Mean of the last ~8 realized \|close-to-close\| moves around reports. “How hard does this stock usually thrash on earnings?” Needs `lxml` + Yahoo history; otherwise **N/A**. |
| **Verdict** | Implied vs Hist Avg label | See table below. Context only — not a trade signal. |
| **Quality** | How trustworthy the option quotes were | See table below. **WIDE** / **STALE** / **SUSPECT** mean treat numbers loosely. |

### Worked mini-example

**AKAM** — Spot $122.27, Straddle $17.70 → Implied ≈ 17.70 / 122.27 ≈ **±14.5%**.  
Hist Avg **1.5%** (past reports moved little on average). Implied ≫ history → **RICH**.  
Quality **WIDE** → bid/ask was loose; do not treat 14.48% as precise to the second decimal.

**DDOG** — Implied **±13.4%** vs Hist Avg **10.5%** → still **RICH**, but less extreme than AKAM.  
Quality **GOOD** → both legs had two-sided quotes.

**ZTS** — Exp shows **+15d** → **DILUTED**. Hist Avg is still shown for curiosity, but the
tool refuses to call it RICH/CHEAP against a multi-week straddle.

### Verdict values

| Value | Meaning in plain terms |
|---|---|
| `RICH` | Implied move is **more than 1.2×** average realized earnings move. Options look **expensive vs this stock’s history** (premium sellers sometimes prefer this setup; buyers pay up). |
| `CHEAP` | Implied is **less than 0.8×** average realized. Options look **inexpensive vs history**. |
| `PRICED` | Implied is roughly in line with history (between the two thresholds). |
| `DILUTED` | No expiration within **9 days** of the report. The straddle also prices ordinary multi-day volatility, so RICH/CHEAP vs a **single-day** historical average would mislead. Exp often shows `+Nd`. |
| `N/A` | No usable history, or quote quality forced the comparison off (e.g. **SUSPECT**), or `--no-history`. |

Thresholds in code: `RICH_RATIO = 1.2`, `CHEAP_RATIO = 0.8`,
`MAX_CLEAN_DAYS_AFTER_EVENT = 9`.

### Quality values

| Value | Meaning in plain terms |
|---|---|
| `GOOD` | Both call and put had two-sided bid/ask quotes. Best case for trusting the mid. |
| `WIDE` | Bid/ask spread was **> 25% of mid** on at least one leg. Number is directionally useful, not precise. |
| `STALE` | Fell back to **last trade** instead of a live mid — common **before open / after close / weekends**. |
| `IV_ONLY` | No usable straddle quotes; only the IV estimate remains. |
| `SUSPECT` | Straddle price looks arbitrage-broken or mostly “intrinsic junk” (thin chain / bad print). **Verdict forced to N/A.** |
| `NO_DATA` / `ERROR` | Missing price or chain, or a fetch failure. Check `note` in the JSON snapshot. |

**Rows are never silently dropped** — a bad quote is labeled, not hidden.

### Footer summary lines

After the table you may see:

- Count of priced names, average implied %, largest name  
- Lists of **RICH** / **CHEAP** / **DILUTED** tickers  
- A methodology note (same ideas as above)

---

## Timing matters

Straddle mids are most meaningful while the US options market is open and quoting.

- Early batch runs (pre-open) often show many **STALE** / **WIDE** rows — that is honest
  reporting, not a bug. Prefer **IV chk** only as a rough cross-check then.
- For live pricing into an event, re-run mid-session when possible.

---

## Integration (daily logs)

### Linux (this host)

`getTodaysStockScreenerData.sh` activates `GoldenRatios/.venv` and appends:

```bash
$VENV_PYTHON MarketBreadth/earnings_expected_move.py --briefing
```

into `MarketBreadth/logs/todaysMarketBreadth.log` (after nine-rules sections).

### Windows

`getStockScreenerData.bat` appends the same briefing to
`Documents\MarketNews\todayStockScreener.log`:

```bat
@python earnings_expected_move.py --briefing >> "%LOG%"
```

The bat starts with `cd /d "%~dp0"` so it works no matter which directory launched it.

### Snapshot file

Also writes `earnings_expected_move_latest.json` next to the script (`stocks[]` with
straddle legs, per-report realized moves, quality, verdict). That JSON is gitignored
(`*.json`); it is a local working artifact for downstream tools.

---

## Caveats (please read)

- The Nasdaq calendar is an **undocumented** endpoint needing a browser User-Agent. If
  it 403s or changes, the tool warns and degrades rather than killing the whole daily run.
- Expected move is **~1-sigma and directionless** — loosely “~68% chance inside the
  band” under a simple model. Not a guarantee; tails happen, especially on earnings.
- **RICH / CHEAP is context, not a signal.** Options are often “rich” into earnings for
  a reason: sellers demand payment for gap risk. History can understate the next surprise.
- Every expiration still includes *some* non-earnings time value; **DILUTED** only flags
  the worst mismatches.
- US holidays in code are a static list for 2026–2027 (no extra calendar library). Extend
  `MARKET_HOLIDAYS` in the script when the year rolls past that.
- Without **`lxml`** in the active venv, Hist Avg / Verdict go blank while straddles still
  appear — install it into `GoldenRatios/.venv`, not system Python.

---

## Related

- `Documents\MarketNews\Expected-Move-Guide.md` — methodology (§6 straddle, §C earnings plays)  
- `Expected-Move-Guide.md` (copy in this repo if present)  
- `nine_rules_gate.py` — general expected move (nearest expiration); shared IV math  
- `stock_screener.py --watchlist` — produces `nine_rules_watchlist.json`  
- `getTodaysStockScreenerData.sh` / `getStockScreenerData.bat` — daily orchestrators  

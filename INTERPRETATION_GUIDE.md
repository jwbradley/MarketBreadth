# MarketBreadth Output Interpretation Guide

**Source material for reading everything the daily suite prints and writes.**

Use this after a run of `getTodaysStockScreenerData.sh` (Linux) or `getStockScreenerData.bat` (Windows). Specialized API/CLI docs stay in the per-tool READMEs; this guide is about **what the numbers mean and how to act (or not act) on them**.

| If you need… | Go here |
|--------------|---------|
| How to run / schedule the suite | [README.md](README.md), [BEST_PRACTICES.md](BEST_PRACTICES.md) |
| Screener CLI flags & scoring math | [README-stock_screener.md](README-stock_screener.md), [README-ta_indicators.md](README-ta_indicators.md) |
| Nine-rules CLI | [README-nine_rules.md](README-nine_rules.md) |
| Earnings straddle details | [README-earnings_expected_move.md](README-earnings_expected_move.md) |
| Options EM concepts | [Expected-Move-Guide.md](Expected-Move-Guide.md) |
| Risk / no-advice language | [DISCLAIMER.md](DISCLAIMER.md) |

**This is educational context, not investment advice.** Labels such as `BUY NOW` or `STRONG BUY` are checklist summaries, not recommendations. See [DISCLAIMER.md](DISCLAIMER.md).

Examples below use a real post-close run dated **2026-08-07** (`logs/todaysMarketBreadth.log`). Your dates, sectors, and names will differ; the **column meanings and decision order** stay the same.

---

## 1. What a full daily run produces

### 1.1 Human-readable logs

| File | What it is |
|------|------------|
| `logs/todaysMarketBreadth.log` | **Primary daily brief** — macro status, breadth, opportunities, full screener tables, nine-rules gate + IV expected move, earnings straddle table |
| `logs/nine_rules_independent.log` | Full independent re-score of core book ∪ screener watchlist (only a pointer line lands in the main log) |
| `logs/errors.log` | START/FAIL timestamps and soft-fail detail for each pipeline step |

### 1.2 Machine-readable snapshots (usually gitignored)

| File | Produced by | Purpose |
|------|-------------|---------|
| `market_breadth_latest.json` | `market_breadth_collector.py` | S&P + 11 GICS sector breadth snapshot |
| `market_breadth_history.json` | same | Multi-day breadth history |
| `stock_screener_results.json` | `stock_screener.py` | Full per-stock technicals for screened sectors |
| `stock_screener_history.json` | same | One record per trading day (tenure / NEW) |
| `nine_rules_watchlist.json` | `stock_screener.py --watchlist` | Short list for the nine-rules gate |
| `earnings_expected_move_latest.json` | `earnings_expected_move.py` | Straddle legs, verdict, quality per reporter |

### 1.3 Order of the main log (funnel)

Read top to bottom — each layer filters the previous:

```
1. Run markers / collectors completed
2. Macro: market_ratios --status, gsr --status          (optional regime context)
3. Market breadth briefing                             (WHERE is participation?)
4. Best opportunities                                  (WHAT to do first)
5. Full stock screener briefing                        (per-sector tables)
6. Nine-rules gate + nearest-expiry IV expected move   (checklist on short list)
7. Pointer → nine_rules_independent.log                (core ∪ watchlist)
8. Earnings expected move                              (event risk / priced move)
9. COMPLETE (or COMPLETE with N failure(s))
```

**Rule of thumb:** never promote a name to “actionable” from step 5–6 alone if step 3 says the market/sector is broken or step 8 says earnings is imminent.

---

## 2. Header lines and data freshness

Look for lines like:

```text
**Data as of close:** 2026-08-07
**Indicators as of close:** 2026-08-07
```

or, on an hourly mid-session run:

```text
**Data as of:** 2026-08-07 intraday snapshot, 57% of session elapsed (volume pro-rated)
```

| Phrase | Meaning |
|--------|---------|
| **as of close** | Session finished (or bar treated as complete); volume is a full day |
| **intraday snapshot** | Live bar kept; **prices are current**, volume is scaled by session fraction |
| `bar_is_partial` / `session_fraction` in JSON | Same idea in machine form (`session_fraction` 1.0 = full day) |

Morning runs often re-report **yesterday’s** settled close. Prefer a post-close job (~16:30–17:45 CT) for the “official” daily read.

---

## 3. Macro block (GoldenRatios companions)

Appears first in the daily brief when those collectors live under `~/myPrograms/KSI/GoldenRatios/`.

### 3.1 Market ratios status

Typical fields:

| Field | What it is | How to use it |
|-------|------------|---------------|
| Gold / Silver | Spot metals levels | Context for risk-off / hard-asset bid |
| Dow / S&P 500 | Cash equity levels | Absolute level; pair with ratios below |
| **GSR** | Gold / silver ratio | Rising GSR often coincides with stress / risk-off; falling can ease that bias |
| **Dow/Gold**, **S&P/Gold** | Equity priced in gold | Falling ratios = equities weak vs gold (defensive regime cue) |

Example (2026-08-07): GSR ~69, Dow/Gold ~12.3, S&P/Gold ~1.76, with gold up hard over the prior week while equity/gold ratios compressed — **risk-sensitive backdrop**, even if equity breadth looks constructive.

### 3.2 How much weight to give it

- Macro is **context**, not a stock pick.
- Align position size / aggression with the macro tape; do not override a broken breadth regime because GSR “looks nice.”
- If these steps fail, the rest of the MarketBreadth pipeline still continues (soft-fail on Linux).

---

## 4. Market breadth briefing

Section header: `## Market Breadth (YYYY-MM-DD)`.

### 4.1 S&P 500 overall block

Example:

```text
**S&P 500 Overall:** 320 advancing / 180 declining (A/D ratio: 1.78)
- A/D Line: 4236 (rising)
- Above 50-DMA: 66.1% (332/502)
- Above 200-DMA: 73.9% (368/502)
- Up/Down Volume Ratio: 2.14
- 52-week Highs: 21 | Lows: 1 | Net: 20
- Breadth Thrust: 54.3%
```

| Metric | Meaning | Rough reading |
|--------|---------|----------------|
| Advancing / declining | Count of SPX names up vs down that session | Balanced participation |
| **A/D ratio** | Advances ÷ declines | >1 bullish day; >>2 strong day; <1 weak day |
| **A/D line** + trend | Cumulative participation | Rising = healthier; falling while index rises = thin leadership |
| **% above 50-DMA** | Short-term trend health | ≥50% often labeled **constructive** in opportunities; well below → selective / defensive |
| **% above 200-DMA** | Longer-term health | High % = bull-market participation; low = structural stress |
| **Up/down volume** | Volume in rising vs falling names | Confirms or contradicts price A/D |
| **Net 52w highs/lows** | Breakout vs breakdown breadth | Large positive = risk-on expansion; many lows = washout |
| **Breadth thrust** | 10-day EMA of advancing % (Zweig-style) | Extreme high readings are rare “thrust” context; `zweig_signal` flags extremes in JSON |

**Worked read (2026-08-07):** 66% above 50-DMA, A/D 1.78, up/down vol 2.14, net +20 highs → **broad constructive day**. That supports taking long setups from strong sectors more seriously than on a 35%-above-50DMA day.

### 4.2 Sector table

| Column | Meaning |
|--------|---------|
| A/D | Advancers / decliners in that GICS sector |
| Ratio | Sector A/D ratio |
| >50DMA / >200DMA | % of sector names above those averages |
| UpVol | Sector up/down volume ratio |
| Net H/L | Net new 52-week highs minus lows |
| Thrust | Sector breadth-thrust style metric |

**Important:** the screener does **not** pick “strongest” by this table’s A/D alone. It ranks sectors with a **multi-metric composite** (`pct_above_50dma`, thrust, A/D, up/down vol, net highs/lows). A sector can lead the table on one-day A/D and still rank mid-pack on composite (e.g. Real Estate high A/D but only 48% above 50-DMA).

### 4.3 How breadth feeds later sections

- Market **% above 50-DMA** becomes the opportunities “Regime” line and Rule 3 of the nine rules.
- Sector **% above 50-DMA** feeds Rule 4.
- Composite scores appear as `composite: 81.97` under each STRONGEST / WEAKEST screener block.

---

## 5. Best Opportunities (`--opportunities`)

Section: `## Best Opportunities (YYYY-MM-DD)`.

**Read this first for action.** Full tables are for audit and secondary names.

### 5.1 Regime line

```text
**Regime:** market 66.1% above 50-DMA -> constructive
```

| Regime text | Threshold (code) | Practical bias |
|-------------|------------------|----------------|
| constructive | market ≥ 50% above 50-DMA | Long setups more allowed |
| defensive / selective | market < 50% | Prefer waiting, smaller size, or only exceptional RS leaders |

### 5.2 The two scores you must read together

| Score | Question it answers | Moves slowly? |
|-------|---------------------|---------------|
| **Setup** (0–100) | Is this a sound vehicle? Trend, RS, liquidity, sector — **not** extension | Slower |
| **Entry** (0–100) | Is *today’s price* a good place to buy? Extension, RSI, Bollinger, volume | Faster |

**High setup + low entry = good stock at a bad price.** That is intentional, not a bug.

Legacy field `score` (JSON) is a 70/30 blend of setup/entry for old consumers. Prefer the two axes.

### 5.3 Action buckets

| Section | Who lands here | What it means for you |
|---------|----------------|------------------------|
| **Actionable now** | Labels like `BUY NOW`, `BUY / SCALE IN`, `RS LEADER - ENTRY OK` (and setup ≥ `--min-setup`, default 60) | Best **candidates** for same-day focus — still size yourself; still check earnings |
| **Strong but extended** | High setup, poor entry (`STRONG - WAIT FOR PULLBACK`, `RS LEADER - EXTENDED`) | Keep on radar; do **not** chase; note stop distance |
| **Building / secondary** | Moderate setup or speculative timing | Optional; lower priority |
| **New to the screen today** | `is_new` / first day of streak | Fresh appearance — interesting, not automatically better |
| **Earnings within 7 days** | `ER+Nd` / earnings_warning | Gap risk; technicals may not survive the print |

Empty “Actionable now” with a prose note is a **valid answer** (“nothing lines up on both axes”).

### 5.4 Opportunities table columns

| Column | Meaning | How to use |
|--------|---------|------------|
| Ticker | Symbol | — |
| Sector | GICS sector from constituents | Context for thesis (momentum vs mean reversion) |
| Setup | Setup quality 0–100 | Primary rank: structure of the idea |
| Entry | Entry timing 0–100 | Quality of *this* price |
| Rules | `N/9` nine-rules pass count | Cross-check; 8–9 is strong alignment |
| RS/SPY | 20-day return minus SPY (percentage points) | Positive = outperforming the market |
| x50DMA | Extension above 50-DMA in **ATR units** (`+1.0A` = one average day’s range above the mean) | ~0–2A more entry-friendly; >3–4A often `EXTENDED`/`CHASE` |
| Stop | Suggested stop price (2-ATR or under nearby swing low) | Distance → `risk_pct` for sizing |
| R:R | Reward:risk to 52-week high when measurable; **`open`** if at/near highs | `open` = no measured overhead supply (not “missing data”) |
| Days | Consecutive trading days on the screen in the current streak | Tenure; 1 often coincides with `NEW` |
| Flags | Extension, divergence, earnings, new | See §7 |

### 5.5 Setup / entry → action labels (top sectors)

| Setup | Entry | Label |
|------:|------:|-------|
| ≥ 70 | ≥ 65 | `BUY NOW` |
| ≥ 70 | ≥ 45 | `BUY / SCALE IN` |
| ≥ 70 | < 45 | `STRONG - WAIT FOR PULLBACK` |
| ≥ 55 | ≥ 65 | `SPECULATIVE ENTRY` |
| ≥ 55 | < 65 | `WATCH` |
| < 55 | any | `AVOID` |

**Weak (bottom) sectors** use a different vocabulary (mean reversion / relative leadership):

| Label | Rough meaning |
|-------|----------------|
| `RS LEADER - ENTRY OK` | Strong relative setup in a weak sector; entry timing OK |
| `RS LEADER - EXTENDED` | Relative leader but price stretched |
| `REVERSAL WATCH` | Possible turn (needs strong entry timing) |
| `WATCH` | Mixed |
| `AVOID / SHORT BIAS` | Structure weak for a long thesis |

### 5.6 Worked examples from 2026-08-07 opportunities

| Name | Setup / Entry | Bucket | Interpretation |
|------|---------------|--------|----------------|
| **HPE** | 94 / 68 | Actionable | High setup, entry ≥ 65 → `BUY NOW` in full table; 9/9 rules; only +1.9A — structure and price both OK |
| **DELL** | 91 / 78 | Actionable | Same pattern; entry even better |
| **DXCM** | 94 / 48 | Actionable as scale-in | Entry 48 → `BUY / SCALE IN` (not full BUY NOW); also `EXTENDED` — more cautious than HPE |
| **WDAY** | 97 / 24 | Strong but extended | Excellent vehicle, chase risk (+3.7A, `CHASE`) — wait |
| **ZBRA** | 94 / 2 | Strong but extended | Extreme extension (+6.7A) despite huge RS — poster child for “great setup, terrible entry” |
| **SLB** | 64 / 77 | Building / secondary | Weak-sector name near the mean (`AT-MEAN`); higher entry score, moderate setup — secondary only |
| **TPR, AES** | — | Earnings in 6d | Do not treat pure technical stops as sufficient through the report |

---

## 6. Full stock screener briefing

Section: `## Stock Screener (YYYY-MM-DD)`.

### 6.1 Header

| Line | Meaning |
|------|---------|
| Market breadth % | Same S&P % above 50-DMA as breadth brief |
| Sector selection: composite | Confirms multi-metric sector pick (not A/D-only) |
| Indicators as of … | Close vs intraday basis (§2) |

### 6.2 Sector blocks: STRONGEST vs WEAKEST

| Block | `sector_type` | Thesis default |
|-------|---------------|----------------|
| **STRONGEST** | `top` | Momentum / trend continuation in favored sectors |
| **WEAKEST** | `bottom` | Avoid most names; exceptions are RS leaders or reversals |

Composite score under the heading (e.g. `Health Care | composite: 81.97`) is the sector rank score from `ta_indicators.rank_sectors` (0–100 style composite).

### 6.3 Full table columns (beyond opportunities)

Same core columns as opportunities, plus:

| Column | Meaning |
|--------|---------|
| Price | Last close (or live last trade if partial bar) |
| RSI | Wilder 14 RSI |
| Action | `entry_label` from the setup/entry pair (§5.5) |

Footer notes in the log restate:

- Setup = structural quality; Entry = timing quality  
- x50DMA in ATR units  
- Stop / R:R basis  

### 6.4 Flags (all of them)

| Flag | Meaning | Practical response |
|------|---------|-------------------|
| `CHASE` | > 4.5 ATR above 50-DMA **or** ≥ 95th percentile of own 1y extension | Do not buy breakout chase; wait for pullback |
| `EXTENDED` | > 3.0 ATR **or** ≥ 85th pctile | Reduced size or wait |
| `AT-MEAN` | < 0.5 ATR from 50-DMA | Near the mean — often better entry location if setup exists |
| `NO-VOL` | ATR collapsed vs own norm (and tiny ATR%) | Often acquisition / event pin; technicals unreliable |
| `DIV-` | Bearish divergence (price up, RSI down, RSI still elevated) | Distribution risk; lower conviction |
| `DIV+` | Bullish divergence (price down, RSI up, RSI still low) | Possible washout turn (more relevant in weak sectors) |
| `ER+Nd` | Earnings in N calendar days | Cap risk or wait; see §9 |
| `NEW` | First day of current on-list streak | Fresh; confirm next sessions |
| `-` | No special flags | — |

**Worked flag reads:**

- **TECH** (Health Care): `NO-VOL,DIV-,NEW`, x50DMA capped at +8.0A — collapsed volatility + divergence; **ignore as a normal technical long**.  
- **ABT / IQV**: `CHASE,DIV-` — extended *and* divergence; wait even if setup is high.  
- **TPR**: `EXTENDED,ER+6d,NEW` — already extended into an earnings window.

### 6.5 Nine rules count in the screener

`Rules` is `rules_passed / 9` from shared `evaluate_nine_rules`:

| # | Rule | Pass condition (current code) |
|---|------|-------------------------------|
| 1 | Trend confirmation | Price > EMA10 > EMA20 > EMA50 |
| 2 | Signal alignment | Price > EMA20 and rising over 5 days |
| 3 | Market breadth | S&P % above 50-DMA ≥ 50 (fails if unknown) |
| 4 | Sector strength | Sector % above 50-DMA ≥ 50 (fails if unknown) |
| 5 | RSI zone | 40 ≤ RSI ≤ 70 |
| 6 | Liquidity / volume | 20d dollar vol ≥ floor (default $20M) **and** volume ratio > 0.6 |
| 7 | Position sizing | ATR% < 8 **and** ATR vs own 100d median < 1.5 |
| 8 | Multi-timeframe | Above EMA20 and EMA100 |
| 9 | No contradictions | No bearish divergence |

**Signal from count alone** (also used by the gate):

| Rules | Label |
|------:|-------|
| 8–9 | STRONG BUY |
| 6–7 | BUY |
| 4–5 | NEUTRAL |
| 0–3 | SELL/AVOID |

**Do not confuse** nine-rules `STRONG BUY` with screener `BUY NOW`. A name can be 8/9 rules (checklist green) and still `STRONG - WAIT FOR PULLBACK` because entry timing is poor (e.g. PLTR, WDAY on 2026-08-07).

### 6.6 Risk columns in depth

| Field | Construction | Use |
|-------|--------------|-----|
| Stop | Prefer 2 ATR below price; if a 20-day swing low sits just under that, stop under the swing (`stop_basis`) | Hard invalidation level for *your* plan — tools do not place orders |
| Risk % | Distance from price to stop as % of price | Position size = (account risk $) / (risk per share) |
| Target | 52-week high when far enough above | Measured R:R only when real overhead exists |
| R:R `open` | At/near highs (`target_basis = open_no_overhead`) | Blue-sky; do not invent a fake 2.00 R:R |

ATR floors prevent nonsense on dead-volatility names (extension cap ±8A, stop floor 0.75% of price).

---

## 7. Screener history and tenure

File: `stock_screener_history.json` (and `Days` / `NEW` in tables).

| Concept | Meaning |
|---------|---------|
| One record per **calendar trading date** | Hourly runs collapse so eight runs ≠ eight “days on list” |
| `runs_today` | How many times the screener ran that date |
| `intraday[]` | Compact within-day snapshots (last 12) |
| `days_on_list` | Length of current unbroken streak of appearances |
| `is_new` / flag `NEW` | Streak length was 0 before today |
| Drop-off then return | Streak resets → `NEW` again |

**Use tenure to prioritize attention**, not as a buy signal. Multi-day high-setup names that stay `STRONG - WAIT FOR PULLBACK` are watchlist material for a pullback; one-day `NEW` + `CHASE` is usually “note and wait.”

---

## 8. Nine-rules gate

Section: progress lines `Analyzing TICKER... SIGNAL (N/9)`, then `## Nine Rules Gate`, then `## Expected Move (1-sigma)`.

### 8.1 Universe

Only names in `nine_rules_watchlist.json` (from `stock_screener.py --watchlist`, default min setup 60, top names per sector, weak-sector filtered more tightly).

### 8.2 Gate table columns

| Column | Meaning |
|--------|---------|
| Ticker / Sector | From watchlist |
| Signal | From rule **count** only (`STRONG BUY` / `BUY` / …) |
| Rules | Pass count |
| RS/SPY | Relative strength vs SPY |

### 8.3 How to combine gate with screener action

| Screener Action | Gate Signal | Combined reading |
|-----------------|-------------|------------------|
| `BUY NOW` | STRONG BUY 8–9/9 | Strongest alignment of structure + timing + checklist |
| `BUY / SCALE IN` | STRONG BUY / BUY | Scale; respect extension flags |
| `STRONG - WAIT FOR PULLBACK` | STRONG BUY 8–9/9 | Checklist green but **price is wrong** — wait |
| Any long bias | NEUTRAL / SELL | Checklist broken; deprioritize |
| Weak-sector `REVERSAL WATCH` | BUY+ | Exploratory only; different thesis |

Example: **HPE** — screener `BUY NOW`, gate `STRONG BUY 9/9` → both axes and checklist agree.  
Example: **WDAY** — screener wait-for-pullback, gate `STRONG BUY 8/9` → hold the thesis, **do not** treat the gate as permission to chase.

### 8.4 Expected Move table (nearest-expiration IV)

This is **not** the earnings straddle tool. It uses **ATM IV on the nearest listed expiration** (often weekly), then:

| Column | Meaning |
|--------|---------|
| Price | Spot used |
| IV | Annualized implied vol from ATM option |
| Daily +/- | Approx 1-sigma one-day move: `Price × IV / sqrt(252)` |
| Weekly +/- | Same idea over ~5 trading days |
| To Exp +/- | 1-sigma to that option’s expiration |
| DTE / Exp | Days to expiration and expiry date |

**How to use:**

- Daily % is a **noise / stop-context** estimate under a normal model (~68% if IV is well specified) — **not a guarantee**.  
- Compare **your stop distance** (`risk_pct`) to daily expected move: a stop tighter than ~1 daily σ is more noise-prone.  
- On earnings names, this nearest-expiry IV can **understate** the event move if the expiry is still pre-report — use §9 for earnings.  
- `N/A` rows (e.g. EA) mean chain/IV fetch failed; ignore EM for that name.

Footer formula reminder in the log matches `Price x IV / sqrt(252)`.

---

## 9. Independent nine-rules scan

Main log only prints a completion pointer. Full content: `logs/nine_rules_independent.log`.

### 9.1 Header to trust

```text
TA engine:    MarketBreadth ta_indicators (shared)
Sources:      core, watchlist:...
Universe:     N symbols
Market breadth: 66.1% above 50-DMA
```

If TA engine is **not** shared, rule math may drift from the screener — reinstall/import path until shared.

### 9.2 Body

- Progress lines: source tags `[core]`, `[watchlist]`, `[core+watchlist]`  
- Markdown table: same signal/rules/RS columns, sorted toward stronger signals  
- **UNIVERSE OVERLAP** section:
  - In both core and watchlist  
  - Screener-only (and which of those are BUY+)  
  - Core-only BUY+  

### 9.3 How to use overlap

| Overlap case | Use |
|--------------|-----|
| Screener-only BUY+ | Ideas the breadth funnel found that are **not** in your standing core book — research candidates |
| Core-only BUY+ | Core holdings that still pass checklist even if not in today’s sector screen |
| In both | Highest continuity between personal book and today’s funnel |

Daily pipeline runs independent with `--no-expected-move` (gate already printed EM).

---

## 10. Earnings expected move

Section: `## Earnings Expected Move - DATE to DATE`.

This answers: **How large a move has the options market priced for the report?**  
It selects the **first option expiration after the earnings event**, not the nearest pre-report expiry.

**Universe (daily runners):** S&P 500 + screener watchlist, **plus** non-index names with a **known** market cap ≥ $10B (`--include-large-caps 10`). Expect roughly ~30 rows in a busy 3-session window, not the old ~9. Names with blank/unknown Nasdaq caps (SPACs, blank-check shells) are **not** admitted by this flag. Manual runs without the flag still show only the smaller universe.

### 10.1 Column reference

| Column | Meaning | How to read |
|--------|---------|-------------|
| Ticker | Symbol | — |
| Report | Calendar report date | Day of the scheduled report |
| When | `BMO` before open / `AMC` after close / `?` unknown | Affects which session fully prices the reaction |
| Spot | Underlying price | Denominator for % |
| Exp | Option expiration used; `+Nd` if far after event | Far expiries often **DILUTED** |
| Straddle | ATM call mid + put mid ($) | Cost of the pair |
| **Implied +/-** | Straddle ÷ spot | **Primary** priced move (~1-sigma framing, directionless) |
| Expected Range | Approx strike ± straddle in $ | Long-straddle breakeven band, **not** a price target forecast |
| IV chk | Separate IV-based estimate (nearest expiry) | Sanity only; often **below** straddle on earnings names |
| Hist Avg | Mean absolute move around past ~8 reports | Needs `lxml` + Yahoo history |
| Verdict | RICH / CHEAP / PRICED / DILUTED / N/A | Context vs history, **not a trade signal** |
| Quality | GOOD / WIDE / STALE / … | Trust level of the quote |

### 10.2 Verdict and quality (short form)

| Verdict | Meaning |
|---------|---------|
| RICH | Implied > 1.2× historical average move — options expensive vs this name’s past |
| CHEAP | Implied < 0.8× history |
| PRICED | Roughly in line |
| DILUTED | Expiry too far after event (>9d); do not compare to one-day history |
| N/A | No history, suspect quotes, or history skipped |

| Quality | Meaning |
|---------|---------|
| GOOD | Two-sided bid/ask both legs |
| WIDE | Spread > 25% of mid — direction OK, precision poor |
| STALE | Used last trade (common off-hours) |
| SUSPECT / NO_DATA / ERROR | Do not trust the row |

### 10.3 Worked example (2026-08-07)

| Ticker | Implied | Hist | Verdict | Takeaway |
|--------|---------|------|---------|----------|
| SMCI | ±14% | 4.5% | RICH / GOOD | Market charges a large event premium vs history |
| LITE | ±14% | 3.0% | RICH / GOOD | Same pattern, huge $ straddle on high spot |
| CAH | ±6.3% | 6.4% | PRICED / WIDE | Roughly fair vs history; quotes wide |
| SPG | ±4.6% | 1.4% | DILUTED / WIDE | Expiry +10d — do not treat as pure earnings move |

**Screener link:** names with `ER+Nd` (TPR, AES on that day) may or may not appear in this table depending on universe filter (S&P 500 + watchlist + large-caps floor on the daily run) and session window. Always reconcile both views for event risk. Large non-S&P names can show up **only** in this table (not in the equity screener) — still event-risk context, not a long setup.

---

## 11. End-to-end reading checklist (one sitting)

Use this when opening `todaysMarketBreadth.log`:

1. **Did the run complete?**  
   - `COMPLETE` vs `COMPLETE with N failure(s)` → check `errors.log` if any FAIL.

2. **Freshness**  
   - Date matches the session you care about; “as of close” vs intraday.

3. **Macro (optional)**  
   - Equity/gold and GSR: risk-on or defensive backdrop?

4. **Breadth regime**  
   - S&P % above 50-DMA constructive? A/D and up/down volume confirm?  
   - Which sectors are strong on **composite**, not only one-day A/D?

5. **Opportunities first**  
   - Actionable now: short list.  
   - Strong but extended: watchlist for pullbacks.  
   - Earnings section: remove or size-cap those names.

6. **Full tables for context**  
   - Confirm sector thesis (top vs bottom).  
   - Scan flags (`CHASE`, `NO-VOL`, `DIV-`, `ER+`).

7. **Gate**  
   - Confirm checklist still green on the short list.  
   - Use daily IV EM for stop vs noise; not for earnings gap size.

8. **Independent log (optional deep dive)**  
   - Screener-only BUY+ vs core book.

9. **Earnings EM**  
   - For anyone reporting soon: implied move, quality, verdict.

10. **Your process**  
    - Size from `risk_pct` / account risk.  
    - Tools do not place orders or enforce stops.

---

## 12. Common misreads (avoid these)

| Misread | Better reading |
|---------|----------------|
| “Everything is STRONG BUY on the gate → buy all” | Gate ignores extension; many are `WAIT FOR PULLBACK` |
| “Setup 95 means buy today” | Check **Entry** and flags |
| “R:R open means bad data” | Means no measured 52w overhead — often strong, not broken |
| “Nearest-expiry IV is the earnings move” | Use `earnings_expected_move` for reports |
| “RICH means sell premium / CHEAP means buy options” | Verdict is **history context**, not a strategy |
| “NEW means best idea” | Only means first day of streak |
| “Bottom sector WATCH is the same as top sector BUY NOW” | Different thesis vocabulary |
| “Hist Avg N/A means tool broken” | Often missing `lxml` in the venv |
| “Morning log is today’s open edge” | Often prior close re-report |

---

## 13. JSON field cheat sheet (when you dig past the log)

### 13.1 `market_breadth_latest.json`

`sp500` and each `sectors[name]` share the metric set: `ad_ratio`, `ad_line`, `ad_line_trend`, `pct_above_50dma`, `pct_above_200dma`, `up_down_vol_ratio`, `net_highs_lows`, `breadth_thrust`, `zweig_signal`, counts, volumes.

### 13.2 `stock_screener_results.json`

Top-level: `date`, `market_breadth_pct`, `sector_selection`, `bar_date`, `bar_is_partial`, `session_fraction`, `scoring` (`two_axis_setup_entry`), `sectors`.

Per stock (selected): `setup_score`, `entry_score`, `entry_label`, `extension_flag`, `rules_passed`, `signal` (same as entry label), `nine_rules_signal_label`, MAs/RSI/MACD/ATR/RS/extension/stop/target, `days_on_list`, `is_new`, earnings fields.

### 13.3 `nine_rules_watchlist.json`

`min_setup_score`, `stocks[]` with setup/entry/label, rules, stop/risk, earnings warnings — input to the gate.

### 13.4 `earnings_expected_move_latest.json`

`sessions_scanned`, `stocks[]` with straddle, implied move, quality, verdict, per-report history, notes.

---

## 14. Mapping log sections → programs

| Log section | Program / flags |
|-------------|-----------------|
| Collectors START lines | Shell/bat orchestration |
| Market ratios / GSR status | GoldenRatios collectors |
| Market Breadth | `market_breadth_collector.py --briefing` |
| Best Opportunities | `stock_screener.py --opportunities` |
| Stock Screener tables | `stock_screener.py --briefing` |
| Nine Rules Gate + EM | `nine_rules_gate.py --briefing` |
| Independent pointer | `nine_rules_independent.py --union-watchlist --briefing --no-expected-move --no-save` |
| Earnings Expected Move | `earnings_expected_move.py --briefing --include-large-caps 10` |

`ta_indicators.py` is a **library only** — never a separate log section.

---

## 15. One composite story (2026-08-07)

Putting the funnel together for that session:

1. **Macro:** gold strong, equity/gold ratios softer → risk-aware backdrop.  
2. **Breadth:** 66% above 50-DMA, positive A/D and volume → **constructive** equity participation.  
3. **Sectors:** Health Care, Consumer Discretionary, Tech lead composite; Energy/Utilities weak.  
4. **Opportunities:** Only a few **actionable** (HPE, DELL, cautious DXCM); many high-setup names are **chases** (WDAY, PLTR, ZBRA…).  
5. **Gate:** Checklist often STRONG BUY even on chases → reinforces “rules ≠ entry timing.”  
6. **Earnings EM:** SMCI/LITE priced for large gaps; separate from the equity screener watchlist unless they appear there.  
7. **User action shape:** Prefer non-extended high-setup names in strong sectors with no near ER; park extended RS leaders for pullbacks; treat weak-sector names as a different game.

Your next run will substitute different names; **keep this reading order and the two-axis discipline.**

---

## Related docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Overview, quick start, layout |
| [BEST_PRACTICES.md](BEST_PRACTICES.md) | Day-to-day operating rules |
| [README-stock_screener.md](README-stock_screener.md) | Screener CLI & scoring |
| [README-ta_indicators.md](README-ta_indicators.md) | Shared math & edit constraints |
| [README-market_cache.md](README-market_cache.md) | Shared TTL disk cache |
| [README-nine_rules.md](README-nine_rules.md) | Gate & independent CLI |
| [README-earnings_expected_move.md](README-earnings_expected_move.md) | Straddle tool deep dive (`--include-large-caps`) |
| [Expected-Move-Guide.md](Expected-Move-Guide.md) | Options EM methodology |
| [CHANGELOG.md](CHANGELOG.md) | What changed when |
| [DISCLAIMER.md](DISCLAIMER.md) | Full disclaimer |

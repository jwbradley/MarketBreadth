# ta_indicators.py

**The shared math library.** It has no `main()`, no CLI, and produces no output files. Nothing runs it directly — it exists so that three separate programs compute RSI, MACD, ATR, extension, stops, and the Nine Rules *identically*.

| Consumer | What it imports | If the numbers disagreed |
|---|---|---|
| `stock_screener.py` | everything: indicators, both scoring axes, labels, sector ranking | — |
| `nine_rules_gate.py` | `calculate_from_ohlcv`, `evaluate_nine_rules`, `nine_rules_signal` | A stock could pass 8/9 rules in the screener and 6/9 in the gate |
| `nine_rules_independent.py` | same three, **with an embedded fallback** if the import fails | Silently drifts onto its own copy of the math |

That last row is the reason this file is delicate: `nine_rules_independent.py` wraps its import in `try/except` and sets `_HAS_SHARED_TA = False` on any failure, falling back to its own internal RSI. It reports which engine it used in its footer (`TA engine: MarketBreadth ta_indicators (shared)`). A syntax error or a renamed function here does not crash it — it quietly downgrades.

**Practical rule: changes to this module must be additive.** New keys in the returned dict, new keyword arguments with defaults. Renaming or removing a key breaks the gate; changing a threshold changes the gate's verdicts without the gate's author knowing.

See `README-stock_screener.md` for the report format, briefing output, watchlist, history, and CLI flags. This document covers only the library.

---

## What's in it, in one pass

Six groups of functions, roughly in the order the screener calls them:

1. **Series primitives** — `ema`, `sma`, `rsi_wilder`, `macd`, `bollinger_pct`, `atr`. Pandas Series in, Series out.
2. **Bar hygiene** — `drop_partial_bar`, `session_fraction_elapsed`. Deals with the fact that a mid-session yfinance bar is still accumulating.
3. **`calculate_from_ohlcv()`** — the main entry point. OHLCV DataFrame in, one flat dict of ~55 scalars out. Everything downstream reads that dict, not the DataFrame.
4. **`evaluate_nine_rules()`** — the pass/fail checklist, plus `nine_rules_signal()` to phrase the count.
5. **Two-axis scoring** — `setup_quality_score`, `entry_timing_score`, `entry_label`, `extension_flag`, and the `_Budget` helper they share.
6. **Sector ranking** — `sector_composite_score`, `rank_sectors`. Consumes the breadth collector's per-sector metrics, not price data.

---

## 1. Series primitives

| Function | Notes |
|---|---|
| `ema(series, span)` | `ewm(span=..., adjust=False)` — the TA convention, not pandas' default |
| `sma(series, window)` | plain rolling mean |
| `rsi_wilder(close, period=14)` | Wilder smoothing (`alpha=1/period`), **not** the simple-average variant. Matches TradingView / StockCharts |
| `macd(close, 12, 26, 9)` | returns `(macd_line, signal_line, histogram)` |
| `bollinger_pct(close, 20, 2.0)` | %B: `0.0` = lower band, `1.0` = upper band. Can exceed either |
| `atr(high, low, close, 14)` | simple rolling mean of true range |
| `relative_strength(stock, bench, lookback=20)` | stock return minus benchmark return, in percentage points. `None` if either series is too short |
| `detect_divergences(close, rsi, lookback=5)` | `{'bearish_divergence': bool, 'bullish_divergence': bool}`. Bearish requires RSI still above 65; bullish requires RSI still below 35 |
| `_percentile_rank(series, value)` | private. Returns `None` — not `50.0` — when fewer than 20 valid points. A fabricated midpoint is worse than an honest null |

RSI uses Wilder deliberately. Swapping in the simple-average form shifts every RSI by a point or two, which is enough to move Rule 5 (`40 <= rsi <= 70`) across its boundary on borderline names.

---

## 2. The partial bar

This is the subtlest thing in the file and worth understanding before touching anything nearby.

The screener is on a Windows Task Scheduler trigger that fires **hourly from 08:30 to 15:30 ET** — every scheduled run lands mid-session. yfinance happily returns a bar for today, but that bar is still forming: its `Close` is the last trade, its `High`/`Low` are provisional, and critically its **`Volume` is only the shares traded so far**.

Two ways to handle that, and the module supports both:

```python
drop_partial_bar(hist, now_et=None) -> (DataFrame, dropped: bool)
```
Removes the last bar when its date is today and the clock is before 16:00 ET. Correct, and *wrong for this use case* — dropping the live bar means every run between 09:30 and 16:00 reports yesterday's close. Eight runs a day would produce eight byte-identical files. This is why `use_complete_bars` defaults to `False`.

```python
session_fraction_elapsed(now_et=None) -> float  # 0.0 - 1.0
```
The alternative: keep the bar, and scale the comparison instead. Returns how much of the 09:30–16:00 session is done, with a mild curve — `linear ** 0.72` — because volume is front- and back-loaded, so raw clock time understates the true fraction early on.

| ET | fraction |
|---|---|
| 09:30 | 0.000 |
| 10:00 | 0.158 |
| 10:30 | 0.260 |
| 12:30 | 0.573 |
| 14:30 | 0.828 |
| 16:00+ | 1.000 |

`calculate_from_ohlcv()` then divides the partial bar's volume by `avg_vol_20 * session_fraction`. It also **excludes the partial bar from its own 20-day average**, so a half-day of volume doesn't drag down the baseline it's being measured against. Below `session_fraction = 0.02` (the first ~8 minutes) volume tells you nothing and `volume_ratio` is set to `1.0` rather than a huge number.

Dollar volume (`dollar_volume_20d`) always uses the full-day average and never the partial bar — it's a liquidity screen, not a participation signal.

**The measured effect.** Before pro-rating, a 14:30 run compared ~3/4 of a day against a full day: median `volume_ratio` 0.47, and Rule 6 failed on 53 of 60 names for purely clock-related reasons. After: 10:30 median 2.82, 14:30 0.88, post-close 0.73 — and prices identical across all clock times, which is the point.

The three flags reporting this are in the returned dict: `partial_bar_dropped`, `bar_is_partial`, `session_fraction`. `stock_screener.py` turns them into the "as of" line in the briefing.

---

## 3. `calculate_from_ohlcv()`

```python
calculate_from_ohlcv(
    hist: pd.DataFrame,          # Open/High/Low/Close/Volume, yfinance style
    spy_close: pd.Series = None, # benchmark for relative strength; omit and RS keys are None
    min_bars: int = 200,         # returns None below this (200-DMA needs 200 bars)
    use_complete_bars: bool = False,
) -> Optional[Dict[str, Any]]
```

Returns `None` — never raises — when data is missing, short, or lacks the required columns. Flattens MultiIndex columns automatically (yfinance does that on batch downloads).

`use_complete_bars=True` drops the live bar and describes only the last closed session. Use it for backtests or exact end-of-day reconciliation, where a moving `Close` would make results irreproducible. Everything scheduled leaves it `False`.

### Returned keys

**Provenance** — `price`, `bar_date`, `partial_bar_dropped`, `bar_is_partial`, `session_fraction`

**Moving averages** — `sma20`, `sma50`, `sma200`, `ema10`, `ema20`, `ema50`, `ema100`

**Trend** — `above_20dma`, `above_50dma`, `above_200dma`, `trend_score` (0–3, count of those three), `ma_aligned` (`sma20>sma50>sma200`), `ema_aligned` (`price>ema10>ema20>ema50`), `multi_tf_aligned` (above both 20- and 100-EMA)

**Oscillators** — `rsi`, `macd`, `macd_signal`, `macd_hist`, `macd_bullish`, `bb_pct`, `bb_position` (`overbought`/`neutral`/`oversold`)

**Volatility** — `atr`, `atr_pct` (ATR as % of price), `atr_vs_own_median` (ATR% ÷ its own 100-day median — see below)

**Extension** — `ext_20dma_pct`, `ext_50dma_pct`, `ext_200dma_pct`, `ext_50dma_atr`, `ext_50dma_pctile`

**Risk** — `stop_price`, `stop_basis`, `stop_2atr`, `swing_low_20`, `risk_per_share`, `risk_pct`, `target_price`, `target_basis`, `rr_ratio`, `high_52w`

**Volume** — `volume_ratio`, `avg_volume_20d`, `daily_volume`, `dollar_volume_20d`

**Relative** — `rs_vs_spy` (20d), `rs_vs_spy_60`, `price_rising_5d`, `bearish_divergence`, `bullish_divergence`

### Why extension is measured three ways

Two stocks can both be in a textbook uptrend while one consolidates 4% above its 50-DMA and the other is stretched 26% above it. Structurally identical, opposite entry decisions. So:

- `ext_50dma_pct` — raw percent. Readable, but not comparable across a utility and a semiconductor.
- `ext_50dma_atr` — distance in ATR units. Volatility-normalized, so it *is* comparable. This is the primary term in entry timing.
- `ext_50dma_pctile` — where today's extension sits within the stock's own past year. Answers "is this unusual *for this name*."

### `atr_vs_own_median`

`atr_pct < 8` passes on essentially every liquid large cap — as a rule it was a constant. Dividing current ATR% by the stock's own 100-day median ATR% asks the useful question instead: is *this* name unusually volatile right now. Above 1.5× it's genuinely harder to size; below 0.35× something is holding it still.

### The ATR floors — read before removing them

ATR-normalized metrics blow up when ATR itself collapses. This was found in live output:

> A ticker with ATR of \$0.30 — **0.42% of price, 0.11× its own median**, the classic signature of a stock pinned under a pending acquisition — reported `ext_50dma_atr` of **25.0A** on an 11.6% move, was flagged CHASE on the strength of a vanishing denominator, and got a stop **0.83% below price**, well inside normal noise and not a survivable stop.

Three fixes, all still in place:

| Guard | Value | Where |
|---|---|---|
| Extension divisor floor | `price * 0.005` (0.5%) | `atr_for_norm` |
| Reported extension cap | `±8.0` ATR | `ext_50_atr` |
| Stop divisor floor | `price * 0.0075` (0.75%) | `atr_for_stop` |
| `NO-VOL` flag | `atr_rel < 0.35 and atr_pct < 1.0` | `extension_flag()` |

After the fix that ticker showed 8.00A (capped), a 1.76% stop, and a `NO-VOL` tag — and unaffected names were unchanged. Removing a floor brings the nonsense back.

### Stops and targets

Default stop is 2 ATR below price. When a 20-day swing low sits *just* below that level — within one ATR — the stop moves to `swing_low - 0.15 ATR` instead (`stop_basis = 'swing_low_20'`), because resting a stop immediately above an obvious structural low invites getting wicked out. When the swing low is far below, the 2-ATR stop is kept (`stop_basis = '2atr'`); anchoring to a distant low would mean absurd risk.

Target is the 52-week high, when that's far enough above price to be a real target (`target_basis = '52w_high'`). For a name at or near new highs there's no measurable overhead supply, so `target_basis` becomes `'open_no_overhead'` and **`rr_ratio` is `None`**. That null is intentional. The alternative was projecting 2R and dividing by 1R, which always prints `2.00` and reads like a measurement when it's an assumption. `stock_screener.py` renders the null as `open`.

---

## 4. Nine Rules

```python
evaluate_nine_rules(
    indicators,                        # a calculate_from_ohlcv() dict
    market_breadth_pct=None,
    sector_breadth_pct=None,
    market_threshold=50.0,
    sector_threshold=50.0,
    liquidity_floor=20_000_000.0,
) -> {'rules': {name: {'passed': bool, 'details': str}}, 'rules_passed': int, 'total_rules': 9}
```

| # | Rule | Test |
|---|---|---|
| 1 | Trend Confirmation | `price > ema10 > ema20 > ema50` |
| 2 | Signal Alignment | above 20-EMA **and** rising over 5 days |
| 3 | Market Breadth | `market_breadth_pct >= 50` |
| 4 | Sector Strength | `sector_breadth_pct >= 50` |
| 5 | Behavioral Sentiment | `40 <= rsi <= 70` |
| 6 | Liquidity/Volume | `dollar_volume_20d >= liquidity_floor` **and** `volume_ratio > 0.6` |
| 7 | Position Sizing | `atr_pct < 8` **and** `atr_vs_own_median < 1.5` |
| 8 | Multi-Timeframe | above both 20-EMA and 100-EMA |
| 9 | No Contradictions | no bearish divergence |

Rules 3 and 4 **fail closed** when breadth is unknown. Passing a name on absent data would be worse than a false negative, and the module deliberately does not invent an SPY proxy to fill the gap — that decision belongs to the caller, which has the breadth file.

Rule 6 was once `volume_ratio > 0.8` alone, which on a mid-session run failed ~88% of names for clock reasons. Dollar volume is the leg that actually decides whether a position can be entered and exited; the participation leg is kept but loosened, since a quiet drift higher isn't a disqualifier.

Rule 7 was once `atr_pct < 8` alone — 60/60 passes, i.e. a free point. Adding the relative test made it discriminate.

`nine_rules_signal(count)`: ≥8 `STRONG BUY`, ≥6 `BUY`, ≥4 `NEUTRAL`, else `SELL/AVOID`.

---

## 5. Two-axis scoring

### Why two numbers instead of one

The original design was a single 0–100 composite. It failed twice over:

- **It saturated.** Eight names printed exactly 100 while their raw values ran 99–107 before clipping. The top of the list — precisely where discrimination matters — was unranked.
- **It couldn't express the most common real situation:** an excellent business at a bad price. A 95-quality setup stretched 5 ATR above its mean averaged into a meaningless mid-70s number.

So it's split:

> **Setup Quality** — is this a good trend to own? Structural, slow-moving. Deliberately *excludes* extension and overbought measures.
> **Entry Timing** — is right now a good moment to buy it? Extension, Bollinger position, RSI, volume. Fast-moving.

A name can legitimately be setup 96 / entry 19 — that reads `STRONG - WAIT FOR PULLBACK` instead of being averaged away.

### `_Budget` — the normalization contract

**This is the part most likely to be "simplified" back into a bug.**

```python
b = _Budget(50.0)                 # base
b.add(value, low, high)           # value contributed, plus the range this term COULD contribute
...
return b.normalized()             # maps score from [lo, hi] onto 0-100
```

Every scoring term declares the minimum and maximum it could have contributed *for this particular name*. The total is then affinely mapped from that achievable range onto 0–100.

Two properties fall out, both of which a fixed divisor loses:

1. **No clipping.** A fixed divisor doesn't fix saturation, it only *moves the ceiling*. That was tried — dividing by 104 — and 18 of 60 names still pinned at exactly 100. (The reason the first estimate of the ceiling was wrong is instructive: `ad_ratio` isn't persisted in the results JSON, so a recompute from the saved file silently omitted the ±6 sector term and understated the true ceiling of ~115–119. Don't reverse-engineer the divisor from saved output.)
2. **Missing inputs cost nothing.** A ticker with no RS history or no sector breadth simply never calls `b.add()` for those terms, so it isn't measured against points it never had a chance to earn.

Result after the change, on a 60-name run: setup 33.1–96.3 with 55/60 distinct values, entry 6.2–91.2 with 41/60 distinct, **zero names pinned at 0 or 100**.

> **If you add a term, give it honest `low`/`high` bounds.** Understating the range inflates every score; overstating it compresses them. Do not reintroduce a fixed divisor.

### `setup_quality_score(indicators, sector_ad_ratio=None, sector_type='top')`

| Term | Contribution | Range |
|---|---|---|
| Trend score | `(trend_score - 1.5) * 10` | ±15 |
| EMA / MA alignment | 7 full, 4 partial, 0 none | 0 → 7 |
| Multi-timeframe | 5 or 0 | 0 → 5 |
| MACD | +6 bullish, −6 bearish (−3 for bottom-sector) | −6 → 6 |
| RS 20d | `9 * tanh(rs20 / 8)` | ±9 |
| RS 60d | `7 * tanh(rs60 / 20)` | ±7 |
| Liquidity | `(log10(dollar_vol) - 7.8) * 4`, clamped | −3 → 4 |
| ATR vs own median | +2 below 1.1×, −5 above 1.8× | −5 → 2 |
| Divergence | −8 bearish, +4 bullish (+8 for bottom-sector) | −8 → 4/8 |
| Sector A/D | +6 above 3.0, +3 above 1.5, −5 below 0.5 | −5 → 6 |

Relative strength is continuous (`tanh`) rather than bucketed, and liquidity is continuous on a log scale, because step functions flattened the ranking exactly where it needed to separate names. `tanh` keeps a runaway 60% RS from dominating while still ordering everything beneath it.

`sector_type='bottom'` softens the MACD penalty and doubles the bullish-divergence reward — for a weak-sector name the thesis is mean reversion, so a bullish divergence is the signal rather than a footnote.

### `entry_timing_score(indicators, sector_type='top')`

| Term | Contribution | Range |
|---|---|---|
| `ext_50dma_atr` | ≤1.0A +20, ≤2.0A +12, ≤3.0A +2, ≤4.5A −12, else −25 | −25 → 20 |
| `ext_50dma_pctile` | ≤40 +10, ≤60 +5, ≥85 −10, ≥95 −18 | −18 → 10 |
| Bollinger %B | top: 0.3–0.7 +10, <0.3 +5, >0.85 −8, >0.95 −15 | −15 → 10 |
| RSI | top: 45–65 +8, <35 +4, >72 −7, >78 −15 | −15 → 8 |
| Volume ratio | >1.5 +5, <0.5 −3 | −3 → 5 |

For `sector_type='bottom'` the Bollinger and RSI terms invert — deeply oversold becomes a positive, since you're looking for a turn rather than continuation.

### `entry_label(setup, timing, sector_type='top')`

**Top sectors:**

| Condition | Label |
|---|---|
| setup ≥70, timing ≥65 | `BUY NOW` |
| setup ≥70, timing ≥45 | `BUY / SCALE IN` |
| setup ≥70 | `STRONG - WAIT FOR PULLBACK` |
| setup ≥55, timing ≥65 | `SPECULATIVE ENTRY` |
| setup ≥55 | `WATCH` |
| else | `AVOID` |

**Bottom sectors:** `RS LEADER - ENTRY OK` / `RS LEADER - EXTENDED` / `REVERSAL WATCH` (needs timing ≥70) / `WATCH` / `AVOID / SHORT BIAS`.

### `extension_flag(indicators)`

Returns a short tag or `None` when unremarkable. Checked in this order:

| Flag | Condition | Meaning |
|---|---|---|
| `NO-VOL` | `atr_rel < 0.35` and `atr_pct < 1.0` | Volatility has collapsed — usually a pending acquisition. Technicals aren't tradeable signals. **Checked first**, because it matters more to the reader than any distance measure |
| `CHASE` | `ext_atr > 4.5` or `pctile >= 95` | Badly extended |
| `EXTENDED` | `ext_atr > 3.0` or `pctile >= 85` | Stretched |
| `AT-MEAN` | `ext_atr < 0.5` | Sitting on the 50-DMA |

---

## 6. Sector ranking

```python
sector_composite_score(metrics) -> float   # 0-100
rank_sectors(sectors, num=2) -> (top_names, bottom_names, scores_by_name)
```

Consumes the per-sector metric dicts written by `market_breadth_collector.py` — not price data. Weights: 35% `pct_above_50dma`, 20% `breadth_thrust`, 20% `ad_ratio` (mapped 0→0, 1→50, 3+→100), 15% `up_down_vol_ratio` (same mapping), 10% `net_highs_lows` (−10→0, 0→50, +10→100).

`rank_sectors` de-duplicates: with few sectors, a name landing in both top and bottom is removed from bottom.

---

## Editing this file

- **Additive only.** New dict keys and new keyword-args-with-defaults. A removed or renamed key breaks `nine_rules_gate.py` at runtime and makes `nine_rules_independent.py` silently fall back to its embedded copy.
- **Don't reintroduce a fixed divisor** in place of `_Budget`. It clips; see above.
- **Don't remove the ATR floors** or the ±8 extension cap.
- **Don't replace a `None` with a plausible-looking default.** `_percentile_rank` below 20 points, `rr_ratio` with no overhead supply, and `relative_strength` without enough history all return `None` on purpose. A fabricated number is indistinguishable from a real one downstream.
- **Don't change `use_complete_bars` back to `True`.** Every scheduled run is intraday; that default would make eight runs a day identical.
- After any edit: `python -m py_compile ta_indicators.py`, then run the full pipeline (`getStockScreenerData.bat`) and confirm `nine_rules_gate.py --briefing` and `nine_rules_independent.py --briefing` both still exit 0 — the gate is the canary for a broken contract.

Constants at module scope: `MARKET_TZ = ZoneInfo('America/New_York')`, `MARKET_CLOSE_HOUR = 16`. The machine's clock is Central; everything session-related converts to ET explicitly rather than relying on local time.

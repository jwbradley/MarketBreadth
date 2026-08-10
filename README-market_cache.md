# market_cache.py — TTL'd Disk Cache for the Screener Suite

Shared on-disk cache that cuts repeated yfinance and Nasdaq calls across
`stock_screener.py`, `nine_rules_gate.py`, `nine_rules_independent.py`, and
`earnings_expected_move.py`. Single file, standard library plus pandas/pyarrow.

Ported from the disk-cache pattern in the PHP `StockTicker` class
(`transfers/Programming/stock-ticker-2026-07-07`), with both of that
implementation's known bugs fixed — see [Differences From the PHP Original](#differences-from-the-php-original).

---

## Why

`getStockScreenerData.bat` runs 14 steps. Before this, they shared nothing:

- **SPY was fetched 4×** per batch — once per tool, identical parameters, data
  that cannot have changed in the intervening seconds.
- **The Nasdaq earnings calendar was fetched 3×** per run (one call per session
  scanned), and again on every ad-hoc invocation.
- **`realized_earnings_moves()` cost 2 round-trips per ticker** —
  `get_earnings_dates()` plus `history(period='3y')`. After
  `--include-large-caps 10` widened the universe from ~9 names to ~33, that
  became 66 calls where it had been 18.

There was no retry, backoff, or cache layer anywhere in the suite. A throttled
Yahoo response produced blank indicators and a silently shortened run.

---

## Requirements

Already present; nothing new to install.

```
pandas >= 2.0     pyarrow >= 21.0     yfinance >= 0.2.61
```

`pyarrow` is what backs the DataFrame store. `fastparquet` is **not** installed
and is not used.

---

## Layout

```
.market_cache/
  earnings_history/     <sha1>.json                  realized earnings moves
  nasdaq_calendar/      <sha1>.json                  one entry per session date
  ohlcv/                <sha1>.parquet + .meta.json  daily bars, CLOSED ONLY
```

Root resolution follows the same `DATA_DIR` convention as the four tools
(`MARKET_BREADTH_DIR` → `GSR_DATA_DIR` → script dir), overridable with
`MARKET_CACHE_DIR`. Deliberately **not** `.cache` — that directory already
exists in the home dir and belongs to unrelated tools (`claude`,
`code-nautilus`, `code-nemo`).

---

## Namespaces and TTLs

| Namespace | TTL | Rationale |
|---|---|---|
| `earnings_history` | 12h | Only changes when a new report prints; spans a full trading day so the 7am batch and a 3pm ad-hoc run share entries |
| `nasdaq_calendar` | 1h | Report dates are stable, but the market caps `--include-large-caps` filters on drift intraday |
| `ohlcv` | 6h | Closed bars only — see below |

---

## The Partial-Bar Rule

**The still-forming daily bar is never cached.** This is the one constraint worth
understanding before changing anything here.

`ta_indicators.py:302` pro-rates participation as:

```python
vol_ratio = daily_vol / (avg_vol_val * session_frac)
```

`session_frac` is computed at *analysis* time, but a cached numerator is frozen at
*capture* time. The denominator keeps growing while the numerator does not, so
`vol_ratio` drifts downward and Rule 6's `> 0.6` participation test fails for
purely clock-related reasons.

Measured live during the port, with a 15-minute TTL:

| | Volume (partial bar) | Rules passed |
|---|---|---|
| Fresh fetch | 1,543,974 | **8/9** |
| 15-min-old cache | 1,525,141 | **7/9** |

FOXA dropped out of the briefing entirely. Price drift was irrelevant — 7e-08
relative, from `auto_adjust` re-deriving the back-adjustment off a moved last
price. Volume was decisive, because within a session it only ever increases.

So `history()`:

1. strips the partial bar before writing, storing settled bars only;
2. treats an all-closed entry as incomplete while the market is open, and
   re-fetches;
3. serves from cache once the session has closed.

**Consequence: the mid-session hit rate on `ohlcv` is intentionally ~0.** The
wins are after 16:00 ET, and on the failure path below. The other two namespaces
are unaffected — neither caches intraday-varying data — and they hit at 100% on a
warm run.

---

## Throttle Resilience

When a fetch raises, `history()` returns the cached frame instead of `None`:

```python
f = market_cache.history('MSFT', period='1y')
# simulated 429 Too Many Requests -> 250 cached bars, last 2026-08-07
```

Empty and failed results are never *written*: caching a throttled empty frame
would turn one bad response into hours of blank indicators. Stale-but-real beats
no indicators at all, which is the case the user asked for.

`fetch_calendar_day()` follows the same rule — it caches only a non-empty day,
since every failure path in it (including a Nasdaq 403) reports itself as `[]`,
and caching that for an hour would hide the outage. A genuinely empty session (a
holiday) costs one cheap re-fetch.

---

## API

| Function | Notes |
|---|---|
| `history(ticker, period='1y', auto_adjust=True, ttl=OHLCV_TTL)` | Cached OHLCV. Drop-in for `yf.Ticker(t).history(...)`. Closed bars only |
| `json_get(ns, key)` | Returns **`(hit, payload)`** — a tuple, not a sentinel |
| `json_set(ns, key, payload, ttl=)` | Expiry stamped into the entry at write time |
| `cached_call(ns, key, producer, ttl=)` | Read-through wrapper; exceptions from `producer` propagate |
| `frame_get(ns, key)` / `frame_set(ns, key, frame, ttl=)` | DataFrame store (parquet + sidecar) |
| `disable()` / `enabled()` | Process-local off switch, behind every `--no-cache` flag |
| `stats()` / `stats_line()` | Per-process hit/miss/write/error counters |
| `purge(expired_only=True)` | Returns `(files_removed, bytes_freed)` |

`json_get` returns a tuple because **`(True, None)` is a real hit on a cached
`None`**, distinct from `(False, None)` for a miss. "This ticker has no usable
earnings history" is a legitimate result, common among the recently-listed
`--include-large-caps` additions, and it costs the same two round-trips to
rediscover as a positive answer.

---

## CLI

```bash
python market_cache.py --stats      # per-namespace live/expired/size
python market_cache.py --purge      # drop expired entries
python market_cache.py --purge-all  # drop everything
```

```
Cache root: C:\Users\DT17787\.market_cache
namespace                      live  expired      size
earnings_history                  4        0     2.0KB
nasdaq_calendar                   3        0   132.6KB
ohlcv                            25        0   426.7KB
```

Nothing prunes automatically. `--purge` is safe to schedule; entries are also
expired individually on read.

---

## Integration

All four tools take **`--no-cache`** to bypass reads and writes. The environment
variable `MARKET_CACHE_DISABLE=1` does the same globally.

`earnings_expected_move.py` prints a cache line to **stderr** after the run, so
it never lands in the markdown briefing appended to the log:

```
Analyzing 4 earnings candidate(s)...
  cache: 7 hit / 0 miss (100%), 0 written
```

`nine_rules_independent.py` imports it **softly** (`try/except ImportError`,
falling back to direct yfinance) because that tool deliberately duplicates its
scoring path to stay standalone. The cache is an optimization there, not a
dependency.

Every filesystem and decode error degrades to a plain miss rather than raising —
a broken cache must never fail the batch run. That also means a permissions
problem is silent, so check `--stats` shows entries before assuming you are
saving calls.

---

## Measured Effect

| Scenario | Before | After |
|---|---|---|
| `earnings_expected_move.py --limit 4 --include-large-caps 10`, warm | 14.3s | **7.1s** (7 hit / 0 miss) |
| `nine_rules_gate.py --briefing`, warm | 12.7s | **7.7s** |
| Full `getStockScreenerData.bat` | — | 2m53s, 33 earnings rows |
| Throttled `history()` | `None`, blank indicators | 250 cached bars |

The `ohlcv` namespace contributes little of that mid-session by design; the
savings shown come from `earnings_history` and `nasdaq_calendar`, plus SPY
deduplication within a single tool's own run.

---

## Verifying a Change Here

Cached and uncached runs **will** differ on a live market. Two consecutive
`--no-cache` runs of `nine_rules_gate.py` differ from each other by ~0.1% on RS
values — that is the noise floor, not a cache bug. The check that matters is the
**rule count** column:

```bash
python nine_rules_gate.py --briefing --no-expected-move            > cached.txt
python nine_rules_gate.py --briefing --no-expected-move --no-cache > fresh.txt
# extract and compare the N/9 column; any changed count is a real regression
```

That test is what caught the FOXA flip. Comparing whole files will only ever tell
you the market moved.

Also confirmed during the port: parquet round-trips float64 **exactly**
(max diff 0.0), and two consecutive live yfinance fetches agree exactly on closed
bars — so any closed-bar difference is `auto_adjust` re-derivation, not a cache
artifact.

---

## Differences From the PHP Original

Both of the caching bugs documented in that project's readme are fixed here:

- **Key canonicalization.** The PHP key is `sha1(implode(',', $symbols) . '_' . $provider)`,
  so `'AAPL,MSFT'` and `'MSFT,AAPL'` are two different files. `_canonical()` sorts
  collection inputs and uses `sort_keys=True` on dicts, so argument order never
  splits an entry.
- **Expiry stamped at write time.** The PHP `cache_set()` accepts a `$ttl` and
  ignores it, checking `filemtime` against a mutable instance TTL — so lowering
  the refresh interval retroactively expires files written under the old one.
  Here `expires_at` is written into the entry and read back from it.

Also improved: writes are atomic (temp file + `os.replace`, no torn reads), and
the parquet store writes the data file *before* its sidecar, so a half-finished
write reads back as a miss rather than as a valid entry pointing at a truncated
file.

---

## Related

- `README-earnings_expected_move.md` — the tool with the heaviest cache use
- `ta_indicators.py` — `drop_partial_bar()` / `session_fraction_elapsed()`, the
  functions the partial-bar rule exists to protect
- `transfers/Programming/stock-ticker-2026-07-07/readme.md` — "Techniques Worth
  Borrowing", where this port was scoped

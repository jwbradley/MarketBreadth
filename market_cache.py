#!/usr/bin/env python3
"""
market_cache.py - TTL'd on-disk cache for slow, repeated market-data lookups.

The screeners are single-sourced on yfinance and re-fetch the same data across
tools within a session: realized_earnings_moves() pulls three years of daily bars
per ticker, and a --include-large-caps run does that ~33 times instead of ~9.
None of it changes between calls minutes apart. This trades a little disk for a
lot of Yahoo round-trips, which also lowers the odds of getting throttled.

Two stores, because the payloads differ:

  json_cache   dicts / lists / scalars -> one .json file
  frame_cache  pandas DataFrames       -> one .parquet + a .meta.json sidecar

Both degrade to a plain miss on any filesystem or decode problem rather than
raising: a broken cache must never fail a batch run. Set MARKET_CACHE_DISABLE=1
to bypass reads and writes entirely.

Ported from the disk-cache idea in the PHP StockTicker class, with its two
sharp edges fixed:

  * Key inputs are canonicalized (sorted keys, stable JSON) before hashing, so
    ('AAPL','MSFT') and ('MSFT','AAPL') are the same entry rather than two.
  * The expiry is stamped INTO the entry at write time. The PHP version checks
    filemtime against a mutable instance TTL, so lowering the TTL retroactively
    expires files written under the old one.

CLI:
    python market_cache.py --stats     # per-namespace size / entry counts
    python market_cache.py --purge     # drop expired entries
    python market_cache.py --purge-all # drop everything
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# Same resolution order as stock_screener.py / nine_rules_gate.py /
# earnings_expected_move.py, so the cache lands beside the data those tools write.
DATA_DIR = os.environ.get(
    'MARKET_BREADTH_DIR',
    os.environ.get('GSR_DATA_DIR', os.path.dirname(os.path.abspath(__file__))),
)

# Dedicated directory name. NOT '.cache' - that already exists in the home dir
# and belongs to unrelated tools (claude, code-nautilus, code-nemo).
CACHE_ROOT = os.environ.get(
    'MARKET_CACHE_DIR', os.path.join(DATA_DIR, '.market_cache')
)

DEFAULT_TTL = 6 * 3600  # 6h: long enough to span a session, short enough to see a new report

_DISABLED = os.environ.get('MARKET_CACHE_DISABLE', '').strip().lower() in (
    '1', 'true', 'yes', 'on',
)

_STATS = {'hit': 0, 'miss': 0, 'write': 0, 'error': 0}


# ---------------------------------------------------------------------------
# Keys and paths
# ---------------------------------------------------------------------------

def _canonical(key: Any) -> str:
    """
    Stable text for any key input. sort_keys makes dict ordering irrelevant, and
    tuples/lists of symbols are sorted so ('A','B') and ('B','A') collapse to one
    entry - the order-sensitivity bug in the PHP original.
    """
    if isinstance(key, (list, tuple, set)):
        parts = sorted(_canonical(k) for k in key)
        return '[' + ','.join(parts) + ']'
    try:
        return json.dumps(key, sort_keys=True, default=str, separators=(',', ':'))
    except Exception:
        return repr(key)


def _digest(key: Any) -> str:
    return hashlib.sha1(_canonical(key).encode('utf-8')).hexdigest()


def _ns_dir(namespace: str) -> Optional[str]:
    """Namespace directory, created on demand. None if it cannot be made."""
    safe = ''.join(c if (c.isalnum() or c in '-_') else '_' for c in namespace)
    path = os.path.join(CACHE_ROOT, safe)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        _STATS['error'] += 1
        return None


def _atomic_write(path: str, data: bytes) -> bool:
    """Write via a temp file in the same dir, then replace. No torn reads."""
    tmp = f'{path}.tmp.{os.getpid()}'
    try:
        with open(tmp, 'wb') as fh:
            fh.write(data)
        os.replace(tmp, path)
        return True
    except OSError:
        _STATS['error'] += 1
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def _drop(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# JSON store
# ---------------------------------------------------------------------------

def json_get(namespace: str, key: Any) -> Tuple[bool, Any]:
    """
    Returns (hit, payload). A miss - absent, expired, or unreadable - is
    (False, None). Expired entries are unlinked on read.

    (hit, None) is a real hit on a cached None, which is why this returns a
    tuple instead of a sentinel: 'this ticker has no usable history' is a result
    worth caching, and it is the expensive case to recompute.
    """
    if _DISABLED:
        return False, None
    d = _ns_dir(namespace)
    if d is None:
        return False, None
    path = os.path.join(d, _digest(key) + '.json')
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            entry = json.load(fh)
    except (OSError, ValueError):
        _STATS['miss'] += 1
        return False, None

    if not isinstance(entry, dict) or 'expires_at' not in entry:
        _drop(path)
        _STATS['miss'] += 1
        return False, None

    if time.time() >= float(entry['expires_at']):
        _drop(path)
        _STATS['miss'] += 1
        return False, None

    _STATS['hit'] += 1
    return True, entry.get('payload')


def json_set(namespace: str, key: Any, payload: Any, ttl: int = DEFAULT_TTL) -> bool:
    """Store `payload`. The expiry is baked in here, not derived at read time."""
    if _DISABLED:
        return False
    d = _ns_dir(namespace)
    if d is None:
        return False
    now = time.time()
    entry = {
        'key': _canonical(key)[:400],  # for eyeballing the cache dir; not read back
        'created_at': now,
        'expires_at': now + max(1, int(ttl)),
        'ttl': max(1, int(ttl)),
        'payload': payload,
    }
    try:
        blob = json.dumps(entry, default=str).encode('utf-8')
    except (TypeError, ValueError):
        _STATS['error'] += 1
        return False
    ok = _atomic_write(os.path.join(d, _digest(key) + '.json'), blob)
    if ok:
        _STATS['write'] += 1
    return ok


def cached_call(
    namespace: str,
    key: Any,
    producer: Callable[[], Any],
    ttl: int = DEFAULT_TTL,
) -> Any:
    """
    Read-through helper: return the cached payload, else call `producer()`, cache
    the result, and return it. Exceptions from `producer` propagate - a failed
    fetch is not a cacheable result.
    """
    hit, payload = json_get(namespace, key)
    if hit:
        return payload
    value = producer()
    json_set(namespace, key, value, ttl=ttl)
    return value


# ---------------------------------------------------------------------------
# DataFrame store (parquet + sidecar)
# ---------------------------------------------------------------------------

def frame_get(namespace: str, key: Any):
    """Cached DataFrame, or None on any miss. Requires pandas + pyarrow."""
    if _DISABLED:
        return None
    d = _ns_dir(namespace)
    if d is None:
        return None
    stem = os.path.join(d, _digest(key))
    data_path, meta_path = stem + '.parquet', stem + '.meta.json'
    try:
        with open(meta_path, 'r', encoding='utf-8') as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        _STATS['miss'] += 1
        return None

    if time.time() >= float(meta.get('expires_at', 0)):
        _drop(data_path, meta_path)
        _STATS['miss'] += 1
        return None

    try:
        import pandas as pd
        frame = pd.read_parquet(data_path)
    except Exception:
        _drop(data_path, meta_path)
        _STATS['miss'] += 1
        return None

    _STATS['hit'] += 1
    return frame


def frame_set(namespace: str, key: Any, frame, ttl: int = DEFAULT_TTL) -> bool:
    """
    Store a DataFrame. Writes the parquet first and the sidecar second, so a
    half-finished write reads back as a miss rather than as a valid entry
    pointing at a truncated file.
    """
    if _DISABLED or frame is None:
        return False
    d = _ns_dir(namespace)
    if d is None:
        return False
    stem = os.path.join(d, _digest(key))
    data_path, meta_path = stem + '.parquet', stem + '.meta.json'
    try:
        frame.to_parquet(data_path)
    except Exception:
        _STATS['error'] += 1
        _drop(data_path)
        return False

    now = time.time()
    meta = {
        'key': _canonical(key)[:400],
        'created_at': now,
        'expires_at': now + max(1, int(ttl)),
        'ttl': max(1, int(ttl)),
        'rows': int(getattr(frame, 'shape', (0, 0))[0]),
    }
    ok = _atomic_write(meta_path, json.dumps(meta).encode('utf-8'))
    if ok:
        _STATS['write'] += 1
    else:
        _drop(data_path)
    return ok


# ---------------------------------------------------------------------------
# OHLCV history - the one shared, hot yfinance call
# ---------------------------------------------------------------------------

# All scheduled screener runs are INTRADAY (08:30-15:30 ET), which makes the
# final bar partial and still moving. That interacts badly with any nonzero TTL:
#
#   ta_indicators pro-rates participation as daily_vol / (avg_vol * session_frac),
#   where session_frac is computed at ANALYSIS time but a cached numerator was
#   frozen at CAPTURE time. The denominator keeps growing while the numerator
#   does not, so vol_ratio drifts downward and Rule 6's `> 0.6` participation
#   test fails for purely clock-related reasons. Observed live: FOXA went 8/9 ->
#   7/9 off a 15-minute-old bar whose volume read 1,525,141 against the current
#   1,543,974. Price drift is irrelevant here (7e-08 relative); volume is not,
#   because it only ever increases within a session.
#
# So the partial bar is never served from cache. Only CLOSED bars are stored, and
# a live request re-fetches whenever the caller needs today's forming bar. The
# long tail - 250 settled daily bars per ticker - is what the cache is for, and
# that is where all the round-trips are anyway.
OHLCV_TTL = 6 * 3600
NS_OHLCV = 'ohlcv'


def _has_partial_bar(frame) -> bool:
    """True when the frame's last bar belongs to a session that has not closed."""
    try:
        from ta_indicators import drop_partial_bar
        _trimmed, dropped = drop_partial_bar(frame)
        return bool(dropped)
    except Exception:
        # Without the helper, assume a partial bar rather than risk caching one.
        return True


def history(ticker: str, period: str = '1y', auto_adjust: bool = True,
            ttl: int = OHLCV_TTL):
    """
    Cached `yf.Ticker(ticker).history(...)`, a drop-in for the call sites that
    share identical parameters. SPY alone is fetched once per tool - four times
    across one batch run - for data that cannot have changed in between.

    Cache entries hold CLOSED bars only. When the live frame carries a partial
    bar, that bar is stripped before writing and the cached entry is treated as
    incomplete on read, so the caller still gets a fresh fetch for today. This
    keeps the volume pro-rating in ta_indicators honest; see the note above.

    Returns the DataFrame, or None if the fetch failed. Empty and failed results
    are never cached: those are the cases worth retrying, and caching an empty
    frame would turn one throttled response into hours of blank indicators.
    """
    key = {'ticker': str(ticker).upper(), 'period': period, 'auto_adjust': bool(auto_adjust)}

    frame = frame_get(NS_OHLCV, key)
    if frame is not None and not _has_partial_bar(frame):
        # Cached frame is all-closed. Serve it only if the market is closed too;
        # mid-session the caller needs today's forming bar, which we never store.
        try:
            from ta_indicators import MARKET_CLOSE_HOUR, MARKET_TZ
            from datetime import datetime as _dt
            now = _dt.now(MARKET_TZ)
            mid_session = now.weekday() < 5 and 9 <= now.hour < MARKET_CLOSE_HOUR
        except Exception:
            mid_session = True
        if not mid_session:
            return frame

    try:
        import yfinance as yf
        live = yf.Ticker(ticker).history(period=period, auto_adjust=auto_adjust)
    except Exception:
        # Fetch failed - a stale-but-real frame beats no indicators at all, and
        # this is precisely the throttled case the cache exists to soften.
        return frame

    if live is None or live.empty:
        return frame if frame is not None else live

    to_store = live
    if _has_partial_bar(live):
        try:
            from ta_indicators import drop_partial_bar
            to_store, _ = drop_partial_bar(live)
        except Exception:
            to_store = None
    if to_store is not None and not to_store.empty:
        frame_set(NS_OHLCV, key, to_store, ttl=ttl)
    return live


# ---------------------------------------------------------------------------
# Maintenance / reporting
# ---------------------------------------------------------------------------

def disable() -> None:
    """Turn the cache off for this process (used by --no-cache flags)."""
    global _DISABLED
    _DISABLED = True


def enabled() -> bool:
    return not _DISABLED


def stats() -> Dict[str, int]:
    """Hit/miss/write/error counters for this process."""
    return dict(_STATS)


def stats_line() -> str:
    s = _STATS
    total = s['hit'] + s['miss']
    rate = (s['hit'] / total * 100.0) if total else 0.0
    return (
        f"cache: {s['hit']} hit / {s['miss']} miss ({rate:.0f}%), "
        f"{s['write']} written"
        + (f", {s['error']} error" if s['error'] else '')
    )


def _entries() -> List[Tuple[str, str, Optional[float], int]]:
    """(namespace, path, expires_at or None, bytes) for every cache file."""
    out: List[Tuple[str, str, Optional[float], int]] = []
    if not os.path.isdir(CACHE_ROOT):
        return out
    for ns in sorted(os.listdir(CACHE_ROOT)):
        ns_path = os.path.join(CACHE_ROOT, ns)
        if not os.path.isdir(ns_path):
            continue
        for name in os.listdir(ns_path):
            path = os.path.join(ns_path, name)
            if not os.path.isfile(path) or name.endswith('.parquet'):
                continue  # parquet expiry lives in its sidecar
            exp: Optional[float] = None
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    exp = float(json.load(fh).get('expires_at', 0))
            except (OSError, ValueError, TypeError):
                pass
            size = 0
            try:
                size = os.path.getsize(path)
                if name.endswith('.meta.json'):
                    size += os.path.getsize(path[: -len('.meta.json')] + '.parquet')
            except OSError:
                pass
            out.append((ns, path, exp, size))
    return out


def purge(expired_only: bool = True) -> Tuple[int, int]:
    """Delete cache entries. Returns (files_removed, bytes_freed)."""
    if not expired_only:
        freed = sum(e[3] for e in _entries())
        count = len(_entries())
        try:
            shutil.rmtree(CACHE_ROOT)
        except OSError:
            return 0, 0
        return count, freed

    now, removed, freed = time.time(), 0, 0
    for _ns, path, exp, size in _entries():
        if exp is None or now >= exp:
            if path.endswith('.meta.json'):
                _drop(path, path[: -len('.meta.json')] + '.parquet')
            else:
                _drop(path)
            removed += 1
            freed += size
    return removed, freed


def _human(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n / 1.0:.1f}{unit}'
        n /= 1024.0
    return f'{n:.1f}GB'


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description='Inspect or purge the market data cache.')
    ap.add_argument('--stats', action='store_true', help='per-namespace summary')
    ap.add_argument('--purge', action='store_true', help='drop expired entries')
    ap.add_argument('--purge-all', action='store_true', help='drop every entry')
    args = ap.parse_args()

    if args.purge_all:
        n, freed = purge(expired_only=False)
        print(f'Removed {n} entr{"y" if n == 1 else "ies"}, freed {_human(freed)}')
        return 0
    if args.purge:
        n, freed = purge(expired_only=True)
        print(f'Removed {n} expired entr{"y" if n == 1 else "ies"}, freed {_human(freed)}')
        return 0

    entries = _entries()
    print(f'Cache root: {CACHE_ROOT}')
    if not entries:
        print('  (empty)')
        return 0

    now = time.time()
    by_ns: Dict[str, List[Tuple[Optional[float], int]]] = {}
    for ns, _p, exp, size in entries:
        by_ns.setdefault(ns, []).append((exp, size))

    print(f'{"namespace":<28} {"live":>6} {"expired":>8} {"size":>9}')
    for ns in sorted(by_ns):
        items = by_ns[ns]
        live = sum(1 for exp, _s in items if exp is not None and now < exp)
        dead = len(items) - live
        size = sum(s for _e, s in items)
        print(f'{ns:<28} {live:>6} {dead:>8} {_human(size):>9}')

    total = sum(s for _e, s in ((e[2], e[3]) for e in entries))
    print(f'{"TOTAL":<28} {len(entries):>6} {"":>8} {_human(total):>9}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

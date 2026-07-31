#!/usr/bin/env python3
"""
Earnings Expected Move

For stocks reporting quarterly earnings in the next few trading sessions, price the
ATM straddle on the first option expiration AFTER the report to get the move the
market has priced in - see Expected-Move-Guide.md section 6 ("The Straddle Shortcut").

Why a dedicated tool: nine_rules_gate.py reports expected move from the NEAREST
expiration, which is wrong for an earnings play. A stock reporting after the close
on Monday has a Friday-expiring straddle worth pennies if measured on the expiration
that lands before the event - the earnings move is not in that contract at all.
This module always selects an expiration that contains the report.

Data sources:
  - Nasdaq earnings calendar API (symbol, report date, pre-market/after-hours timing)
  - sp500_constituents.csv + nine_rules_watchlist.json (universe filter)
  - Yahoo options chain for straddle quotes, with IV formula as cross-check
  - Yahoo earnings history + daily bars for realized past earnings moves

Usage:
  python3 earnings_expected_move.py                        # Next 3 sessions, S&P500 + watchlist
  python3 earnings_expected_move.py --sessions 2           # Only next 2 sessions
  python3 earnings_expected_move.py --tickers PLTR VRTX    # Ad-hoc tickers
  python3 earnings_expected_move.py --all-calendar         # Skip universe filter
  python3 earnings_expected_move.py --briefing             # Markdown for the log
  python3 earnings_expected_move.py --no-history           # Skip realized-move lookback
"""

import argparse
import json
import math
import os
import sys
import textwrap
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

try:
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip install yfinance pandas numpy")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the vetted expiration sorting and IV math rather than re-deriving it.
from nine_rules_gate import (  # noqa: E402
    TRADING_DAYS_PER_YEAR,
    _sorted_expirations,
    get_expected_move,
)

DATA_DIR = os.environ.get(
    'MARKET_BREADTH_DIR',
    os.environ.get('GSR_DATA_DIR', os.path.dirname(os.path.abspath(__file__))),
)
WATCHLIST_FILE = os.path.join(DATA_DIR, 'nine_rules_watchlist.json')
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')
LATEST_JSON = os.path.join(DATA_DIR, 'earnings_expected_move_latest.json')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')

NASDAQ_CALENDAR_URL = 'https://api.nasdaq.com/api/calendar/earnings?date={date}'
REQUEST_HEADERS = {
    # Nasdaq returns 403 to the default urllib agent.
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Politeness delay between Yahoo option-chain fetches (seconds).
FETCH_DELAY = 0.3

# Verdict thresholds: implied vs average realized earnings move.
RICH_RATIO = 1.2
CHEAP_RATIO = 0.8

# Quote quality: bid/ask spread wider than this fraction of mid is untrustworthy.
WIDE_SPREAD_RATIO = 0.25

# An expiration more than this many days past the event bundles in a lot of ordinary
# (non-earnings) vol, so its straddle overstates the pure earnings move. Such rows are
# flagged DILUTED and excluded from the RICH/CHEAP verdict rather than compared against
# a single-day realized move.
MAX_CLEAN_DAYS_AFTER_EVENT = 9

# Market hours in ET, used to tell whether a same-day pre-market report has already printed.
MARKET_TZ = ZoneInfo('America/New_York')
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 16

# US market holidays. pandas_market_calendars / exchange_calendars are not installed
# and this tool only ever looks a few sessions ahead, so a small static set suffices.
MARKET_HOLIDAYS = {
    # 2026
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25',
    '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
    # 2027
    '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31',
    '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24',
}


# ---------------------------------------------------------------------------
# Trading session helpers
# ---------------------------------------------------------------------------

def is_trading_day(d: date) -> bool:
    """Weekday and not a listed US market holiday."""
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in MARKET_HOLIDAYS


def next_trading_day(d: date) -> date:
    """First trading day strictly after d."""
    nxt = d + timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def trading_days_between(start: date, end: date) -> int:
    """
    Count trading sessions in (start, end]. Used for the IV horizon so the day count
    matches the sqrt(252) trading-day annualization - mixing calendar days with a
    trading-day basis overstates the move by ~18% on a one-week horizon.
    """
    if end <= start:
        return 0
    days = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur):
            days += 1
        cur += timedelta(days=1)
    return days


def upcoming_sessions(count: int, start: Optional[date] = None) -> List[date]:
    """
    Next `count` trading sessions to scan for earnings, starting with today when
    today is a trading day (pre-market reporters still ahead of us).
    """
    sessions: List[date] = []
    cur = start or date.today()
    if not is_trading_day(cur):
        cur = next_trading_day(cur)
    while len(sessions) < count:
        sessions.append(cur)
        cur = next_trading_day(cur)
    return sessions


def already_reported(report_date: date, timing: str, now_et: Optional[datetime] = None) -> bool:
    """
    True when the report has already printed, so its move is history and no straddle
    prices it any more.

    A pre-market name reporting today is done by the time the market opens; an
    after-hours name reporting today is done once the close has passed. Without this
    check an evening run lists names that moved this morning as if they were upcoming.
    """
    now = now_et or datetime.now(MARKET_TZ)
    today = now.date()
    if report_date < today:
        return True
    if report_date > today:
        return False
    if timing == 'pre-market':
        return now.hour >= MARKET_OPEN_HOUR
    if timing == 'after-hours':
        return now.hour >= MARKET_CLOSE_HOUR
    # Unknown timing: only treat as done after the close.
    return now.hour >= MARKET_CLOSE_HOUR


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def load_sp500() -> Dict[str, str]:
    """Map ticker -> GICS sector from the constituents CSV (same normalization as nine_rules_gate)."""
    if not os.path.exists(CONSTITUENTS_FILE):
        return {}
    try:
        df = pd.read_csv(CONSTITUENTS_FILE)
    except Exception:
        return {}
    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        sym = str(row['Symbol']).replace('.', '-')
        mapping[sym] = row.get('GICS Sector', '')
    return mapping


def load_watchlist_tickers() -> List[str]:
    """Tickers from nine_rules_watchlist.json (written by stock_screener.py --watchlist)."""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            data = json.load(f)
    except Exception:
        return []
    return [s['ticker'] for s in data.get('stocks', []) if s.get('ticker')]


# ---------------------------------------------------------------------------
# Earnings calendar
# ---------------------------------------------------------------------------

def _parse_market_cap(raw: Any) -> Optional[float]:
    """'$293,095,362,308' -> 293095362308.0"""
    if raw is None:
        return None
    txt = str(raw).replace('$', '').replace(',', '').strip()
    if not txt or txt in ('N/A', 'NA', '--'):
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def normalize_timing(raw: Optional[str]) -> str:
    """Nasdaq 'time' field -> 'pre-market' | 'after-hours' | 'unknown'."""
    txt = (raw or '').lower()
    if 'pre-market' in txt or 'before' in txt:
        return 'pre-market'
    if 'after-hours' in txt or 'after' in txt:
        return 'after-hours'
    return 'unknown'


def fetch_calendar_day(session: date, verbose: bool = False) -> List[Dict[str, Any]]:
    """Fetch one day of the Nasdaq earnings calendar. Returns [] on any failure."""
    url = NASDAQ_CALENDAR_URL.format(date=session.isoformat())
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        if verbose:
            print(f"  WARNING: calendar fetch failed for {session}: {type(e).__name__}: {e}")
        return []
    except Exception as e:  # undocumented endpoint - never let it kill the batch run
        if verbose:
            print(f"  WARNING: calendar fetch error for {session}: {type(e).__name__}: {e}")
        return []

    rows = ((payload or {}).get('data') or {}).get('rows') or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        symbol = (row.get('symbol') or '').strip().upper().replace('.', '-')
        if not symbol:
            continue
        out.append({
            'ticker': symbol,
            'company': (row.get('name') or '').strip(),
            'report_date': session.isoformat(),
            'timing': normalize_timing(row.get('time')),
            'market_cap': _parse_market_cap(row.get('marketCap')),
            'eps_forecast': (row.get('epsForecast') or '').strip() or None,
            'fiscal_quarter': (row.get('fiscalQuarterEnding') or '').strip() or None,
        })
    return out


def fetch_earnings_calendar(
    sessions: List[date],
    verbose: bool = False,
    include_reported: bool = False,
) -> List[Dict[str, Any]]:
    """
    Earnings entries across the given sessions, de-duplicated on first (earliest) sighting.

    Names whose report has already printed are dropped unless include_reported is set -
    their move is realized and no straddle prices it any more.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    dropped = 0
    for session in sessions:
        entries = fetch_calendar_day(session, verbose=verbose)
        kept = 0
        for entry in entries:
            report_d = datetime.strptime(entry['report_date'], '%Y-%m-%d').date()
            if not include_reported and already_reported(report_d, entry['timing']):
                dropped += 1
                continue
            if entry['ticker'] not in seen:
                seen[entry['ticker']] = entry
                kept += 1
        if verbose:
            print(f"  {session} ({session.strftime('%a')}): "
                  f"{len(entries)} reporters, {kept} still upcoming")
    if verbose and dropped:
        print(f"  ({dropped} already-reported entr{'y' if dropped == 1 else 'ies'} skipped; "
              f"use --include-reported to keep them)")
    return list(seen.values())


def earnings_date_from_yfinance(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fallback for --tickers, or when the Nasdaq endpoint is unavailable.
    yfinance's calendar has no pre/post timing, so timing is 'unknown'.
    """
    try:
        cal = yf.Ticker(ticker).calendar or {}
    except Exception:
        return None
    raw = cal.get('Earnings Date')
    if not raw:
        return None
    dates = raw if isinstance(raw, (list, tuple)) else [raw]
    for d in dates:
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date) and d >= date.today():
            return {
                'ticker': ticker,
                'company': '',
                'report_date': d.isoformat(),
                'timing': 'unknown',
                'market_cap': None,
                'eps_forecast': None,
                'fiscal_quarter': None,
            }
    return None


# ---------------------------------------------------------------------------
# Expiration selection - the core of this tool
# ---------------------------------------------------------------------------

def effective_event_date(report_date: date, timing: str) -> date:
    """
    First session on which the earnings reaction is tradable.

    After-hours reporters move the NEXT session, so the option must survive past
    that day. Pre-market (and unknown, treated as pre-market since it is the
    conservative choice - it never selects an expiration that misses the move)
    react on the report date itself.
    """
    if timing == 'after-hours':
        return next_trading_day(report_date)
    return report_date


def select_expiration(
    expirations: List[str],
    event_date: date,
) -> Optional[Tuple[str, int]]:
    """
    First expiration on/after the event date, so the contract contains the report.

    Returns (expiration, days_after_event) or None. days_after_event exposes how
    much non-earnings time is bundled in: a large value (no weeklies listed) means
    the straddle overstates the pure earnings move.
    """
    for exp_str in _sorted_expirations(expirations, prefer_min_dte=0):
        try:
            exp_d = datetime.strptime(exp_str, '%Y-%m-%d').date()
        except ValueError:
            continue
        if exp_d >= event_date:
            return exp_str, (exp_d - event_date).days
    return None


# ---------------------------------------------------------------------------
# Straddle pricing
# ---------------------------------------------------------------------------

def get_spot(stock: yf.Ticker) -> Optional[float]:
    """Last price, preferring fast_info, falling back to recent closes."""
    try:
        fi = stock.fast_info
        for key in ('lastPrice', 'last_price'):
            try:
                px = fi.get(key) if hasattr(fi, 'get') else None
            except Exception:
                px = None
            if px and float(px) > 0:
                return float(px)
    except Exception:
        pass
    try:
        hist = stock.history(period='5d')
        if not hist.empty:
            px = float(hist['Close'].iloc[-1])
            if px > 0:
                return px
    except Exception:
        pass
    return None


def _leg_price(row: pd.Series) -> Tuple[Optional[float], str]:
    """
    Price one option leg.

    Returns (price, quality) where quality is 'mid' (two-sided quote),
    'wide' (two-sided but spread > WIDE_SPREAD_RATIO of mid), 'last'
    (fell back to lastPrice - stale outside market hours), or 'none'.
    """
    bid = row.get('bid')
    ask = row.get('ask')
    last = row.get('lastPrice')

    def _num(v: Any) -> Optional[float]:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    bid_f, ask_f, last_f = _num(bid), _num(ask), _num(last)

    if bid_f and ask_f and bid_f > 0 and ask_f > 0 and ask_f >= bid_f:
        mid = (bid_f + ask_f) / 2.0
        if mid > 0 and (ask_f - bid_f) / mid > WIDE_SPREAD_RATIO:
            return mid, 'wide'
        return mid, 'mid'

    if last_f and last_f > 0:
        return last_f, 'last'
    return None, 'none'


def price_straddle(
    stock: yf.Ticker,
    expiration: str,
    spot: float,
) -> Optional[Dict[str, Any]]:
    """
    Price the ATM straddle on one expiration.

    ATM strike is chosen from strikes listed on BOTH sides so the two legs share a
    strike - a real straddle, not a mismatched pair.
    """
    try:
        chain = stock.option_chain(expiration)
    except Exception:
        return None

    calls, puts = chain.calls, getattr(chain, 'puts', None)
    if calls is None or puts is None or calls.empty or puts.empty:
        return None
    if 'strike' not in calls.columns or 'strike' not in puts.columns:
        return None

    shared = set(calls['strike'].dropna()) & set(puts['strike'].dropna())
    if not shared:
        return None
    strike = min(shared, key=lambda s: abs(float(s) - spot))

    call_row = calls[calls['strike'] == strike].iloc[0]
    put_row = puts[puts['strike'] == strike].iloc[0]

    call_px, call_q = _leg_price(call_row)
    put_px, put_q = _leg_price(put_row)
    if call_px is None or put_px is None:
        return None

    straddle = call_px + put_px
    if straddle <= 0:
        return None

    # Worst leg quality governs the row.
    if 'last' in (call_q, put_q):
        quality = 'STALE'
    elif 'wide' in (call_q, put_q):
        quality = 'WIDE'
    else:
        quality = 'GOOD'

    # Arbitrage sanity check: a straddle is worth at least the strike's intrinsic value,
    # and a strike far from spot makes the "ATM" straddle mostly intrinsic rather than a
    # read on the expected move. Thin chains (one shared strike, stale prints) hit this.
    intrinsic = abs(spot - float(strike))
    if straddle < intrinsic or intrinsic > 0.5 * straddle:
        quality = 'SUSPECT'

    def _oi(row: pd.Series) -> Optional[int]:
        try:
            v = row.get('openInterest')
            return int(v) if v is not None and math.isfinite(float(v)) else None
        except (TypeError, ValueError):
            return None

    return {
        'strike': float(strike),
        'call_price': round(call_px, 2),
        'put_price': round(put_px, 2),
        'straddle': round(straddle, 2),
        'implied_move_pct': round(straddle / spot * 100.0, 2),
        'lower_breakeven': round(float(strike) - straddle, 2),
        'upper_breakeven': round(float(strike) + straddle, 2),
        'quality': quality,
        'call_oi': _oi(call_row),
        'put_oi': _oi(put_row),
    }


# ---------------------------------------------------------------------------
# Realized earnings moves (implied vs history)
# ---------------------------------------------------------------------------

def realized_earnings_moves(
    stock: yf.Ticker,
    lookback: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Absolute close-to-close move across each of the last `lookback` reports:
    close(first session on/after report) vs close(prior session).

    Reports whose surrounding bars fall outside available history are skipped
    rather than guessed at.
    """
    try:
        earnings = stock.get_earnings_dates(limit=lookback + 6)
    except Exception:
        return None
    if earnings is None or earnings.empty:
        return None

    try:
        hist = stock.history(period='3y')
    except Exception:
        return None
    if hist is None or hist.empty:
        return None

    idx = hist.index
    if getattr(idx, 'tz', None) is not None:
        hist = hist.copy()
        hist.index = idx.tz_localize(None)

    moves: List[Dict[str, Any]] = []
    for ts, row in earnings.iterrows():
        # Only past reports have a Reported EPS; future rows have none.
        if 'Reported EPS' in earnings.columns and pd.isna(row.get('Reported EPS')):
            continue
        try:
            stamp = ts.tz_localize(None) if getattr(ts, 'tz', None) is not None else ts
            stamp = stamp.normalize()
        except Exception:
            continue

        pos = hist.index.searchsorted(stamp)
        # pos == 0 -> no prior bar; pos >= len -> no reaction bar yet.
        if pos <= 0 or pos >= len(hist):
            continue

        prev_close = float(hist['Close'].iloc[pos - 1])
        after_close = float(hist['Close'].iloc[pos])
        if prev_close <= 0:
            continue
        moves.append({
            'date': stamp.date().isoformat(),
            'move_pct': round(abs(after_close / prev_close - 1.0) * 100.0, 2),
        })
        if len(moves) >= lookback:
            break

    if not moves:
        return None
    pcts = [m['move_pct'] for m in moves]
    return {
        'count': len(pcts),
        'avg_pct': round(sum(pcts) / len(pcts), 2),
        'max_pct': round(max(pcts), 2),
        'moves': moves,
    }


def verdict(
    implied_pct: Optional[float],
    avg_realized_pct: Optional[float],
    days_after_event: Optional[int] = None,
) -> str:
    """
    RICH / CHEAP / PRICED - implied vs the stock's own earnings history.

    Returns 'DILUTED' when the only expiration after the report is far enough out that
    the straddle also prices weeks of ordinary vol; comparing that to a single-day
    realized move would label almost everything RICH.
    """
    if implied_pct is None or not avg_realized_pct:
        return 'N/A'
    if days_after_event is not None and days_after_event > MAX_CLEAN_DAYS_AFTER_EVENT:
        return 'DILUTED'
    ratio = implied_pct / avg_realized_pct
    if ratio > RICH_RATIO:
        return 'RICH'
    if ratio < CHEAP_RATIO:
        return 'CHEAP'
    return 'PRICED'


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_entry(
    entry: Dict[str, Any],
    sector_map: Dict[str, str],
    include_history: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Price one earnings candidate. Always returns a row; failures carry a 'note'."""
    ticker = entry['ticker']
    result: Dict[str, Any] = {
        **entry,
        'sector': sector_map.get(ticker, ''),
        'spot': None,
        'expiration': None,
        'dte': None,
        'days_after_event': None,
        'straddle': None,
        'iv_expected_move': None,
        'history': None,
        'verdict': 'N/A',
        'quality': 'NO_DATA',
        'note': None,
    }

    report_d = datetime.strptime(entry['report_date'], '%Y-%m-%d').date()
    event_d = effective_event_date(report_d, entry['timing'])
    result['event_date'] = event_d.isoformat()

    stock = yf.Ticker(ticker)
    spot = get_spot(stock)
    if not spot:
        result['note'] = 'no price'
        if verbose:
            print(f"  {ticker}: skipped (no price)")
        return result
    result['spot'] = round(spot, 2)

    try:
        expirations = list(stock.options or [])
    except Exception:
        expirations = []
    if not expirations:
        result['note'] = 'no options chain'
        if verbose:
            print(f"  {ticker}: no options chain")
        return result

    picked = select_expiration(expirations, event_d)
    if not picked:
        result['note'] = 'no expiration after earnings'
        if verbose:
            print(f"  {ticker}: no expiration on/after {event_d}")
        return result

    exp_str, days_after = picked
    exp_d = datetime.strptime(exp_str, '%Y-%m-%d').date()
    result['expiration'] = exp_str
    result['dte'] = max((exp_d - date.today()).days, 0)
    result['days_after_event'] = days_after

    straddle = price_straddle(stock, exp_str, spot)
    time.sleep(FETCH_DELAY)

    if straddle:
        result['straddle'] = straddle
        result['quality'] = straddle['quality']
    else:
        result['note'] = 'no usable straddle quotes'

    # IV-formula cross-check over the same horizon, in TRADING days to match sqrt(252).
    iv_em = get_expected_move(ticker, spot)
    if iv_em:
        iv_dec = iv_em.get('iv_decimal')
        horizon_td = max(trading_days_between(date.today(), exp_d), 1)
        if iv_dec:
            horizon_move = (spot * iv_dec * math.sqrt(float(horizon_td))) / math.sqrt(
                TRADING_DAYS_PER_YEAR
            )
            result['iv_expected_move'] = {
                'iv': iv_em['iv'],
                'move': round(horizon_move, 2),
                'move_pct': round(horizon_move / spot * 100.0, 2),
                'trading_days': horizon_td,
            }
    if straddle is None and result['iv_expected_move']:
        result['quality'] = 'IV_ONLY'
    time.sleep(FETCH_DELAY)

    if include_history:
        result['history'] = realized_earnings_moves(stock)
        time.sleep(FETCH_DELAY)

    implied = (straddle or {}).get('implied_move_pct')
    if implied is None:
        implied = (result['iv_expected_move'] or {}).get('move_pct')
    # A SUSPECT straddle (stale/intrinsic-dominated) must not drive a rich/cheap call.
    if result.get('quality') == 'SUSPECT':
        result['verdict'] = 'N/A'
    else:
        result['verdict'] = verdict(
            implied,
            (result['history'] or {}).get('avg_pct'),
            days_after_event=result.get('days_after_event'),
        )
    result['implied_move_pct'] = implied

    if verbose:
        if implied is not None:
            hist_txt = ''
            if result['history']:
                hist_txt = f" | hist avg {result['history']['avg_pct']:.1f}%"
            print(
                f"  {ticker}: {entry['report_date']} ({entry['timing']}) "
                f"exp {exp_str} | implied +/-{implied:.2f}% "
                f"[{result['quality']}]{hist_txt} {result['verdict']}"
            )
        else:
            print(f"  {ticker}: {result['note']}")
    return result


def sort_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Largest implied move first; unpriceable rows last."""
    return sorted(
        results,
        key=lambda r: (r.get('implied_move_pct') is None, -(r.get('implied_move_pct') or 0.0)),
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

TIMING_LABEL = {'pre-market': 'BMO', 'after-hours': 'AMC', 'unknown': '?'}

METHOD_NOTE = (
    "Implied move = ATM straddle (call mid + put mid) on the first expiration after the "
    "report, per Expected-Move-Guide.md section 6. ~1-sigma (~68%) range, not a "
    "directional forecast. Quality: GOOD two-sided quotes | WIDE spread >25% of mid | "
    "STALE lastPrice fallback | IV_ONLY no usable quotes | SUSPECT straddle below or "
    "dominated by intrinsic value (thin chain / stale print). Verdict compares implied to the "
    f"stock's own average realized earnings move; DILUTED means the nearest expiration is "
    f">{MAX_CLEAN_DAYS_AFTER_EVENT}d past the report, so the straddle also prices "
    "non-earnings vol and is not comparable to a single-day move. IV chk is a sanity check "
    "only - it uses ATM IV from the nearest listed expiration, which on an earnings name is "
    "often the pre-report contract, so it typically reads BELOW the straddle. Treat a large "
    "gap as expected, not as an error; the straddle is the number to trade off."
)


# Column headers and alignment for the report table. '<' left-aligns labels,
# '>' right-aligns numbers so decimal points stack.
REPORT_COLUMNS: List[Tuple[str, str]] = [
    ('Ticker', '<'),
    ('Report', '<'),
    ('When', '<'),
    ('Spot', '>'),
    ('Exp', '>'),
    ('Straddle', '>'),
    ('Implied +/-', '>'),
    ('Expected Range', '>'),
    ('IV chk', '>'),
    ('Hist Avg', '>'),
    ('Verdict', '<'),
    ('Quality', '<'),
]


def _report_row(r: Dict[str, Any]) -> List[str]:
    """Format one result as the cell strings for REPORT_COLUMNS."""
    st = r.get('straddle') or {}
    iv = r.get('iv_expected_move') or {}
    hist = r.get('history') or {}
    spot = r.get('spot')
    implied = r.get('implied_move_pct')

    exp_s = r.get('expiration') or 'N/A'
    # Mark expirations well past the event - the straddle carries extra non-event vol.
    dae = r.get('days_after_event')
    if dae is not None and dae > MAX_CLEAN_DAYS_AFTER_EVENT:
        exp_s = f"{exp_s} +{dae}d"

    if st.get('lower_breakeven') is not None:
        range_s = f"${st['lower_breakeven']:,.2f} - ${st['upper_breakeven']:,.2f}"
    else:
        range_s = 'N/A'

    return [
        r['ticker'],
        r.get('report_date', ''),
        TIMING_LABEL.get(r.get('timing'), '?'),
        f"${spot:,.2f}" if spot else 'N/A',
        exp_s,
        f"${st['straddle']:,.2f}" if st.get('straddle') else 'N/A',
        f"+/-{implied:.2f}%" if implied is not None else 'N/A',
        range_s,
        f"{iv['move_pct']:.1f}%" if iv.get('move_pct') is not None else 'N/A',
        f"{hist['avg_pct']:.1f}%" if hist.get('avg_pct') is not None else 'N/A',
        r.get('verdict', 'N/A'),
        r.get('quality', 'N/A'),
    ]


def print_report(results: List[Dict[str, Any]], markdown: bool, sessions: List[date]) -> None:
    span = f"{sessions[0].isoformat()} to {sessions[-1].isoformat()}" if sessions else 'n/a'
    title = f"Earnings Expected Move - {span}"

    priced = [r for r in results if r.get('implied_move_pct') is not None]

    if markdown:
        print(f"\n## {title}")
        print()
    else:
        print(f"\n{title}")

    if not results:
        msg = "No qualifying earnings reporters found in this window."
        print(f"*{msg}*" if markdown else f"{'=' * 40}\n{msg}")
        return

    headers = [h for h, _ in REPORT_COLUMNS]
    aligns = [a for _, a in REPORT_COLUMNS]
    rows = [_report_row(r) for r in results]

    # Size each column to its widest cell so the pipes line up when the log is
    # read as plain text, not only when a markdown renderer draws the table.
    widths = [
        max(len(h), *(len(row[i]) for row in rows))
        for i, h in enumerate(headers)
    ]

    def render(cells: List[str]) -> str:
        body = ' | '.join(f"{c:{a}{w}}" for c, a, w in zip(cells, aligns, widths))
        # Markdown needs the closing pipe; plain text does not need the padding
        # that a trailing left-aligned column would leave behind.
        return f"| {body} |" if markdown else body.rstrip()

    table_width = sum(widths) + 3 * (len(widths) - 1) + (4 if markdown else 0)

    if markdown:
        print(render(headers))
        # Dash runs sized to the columns, with alignment colons, so the divider
        # lines up with the cells above and below it.
        print('|' + '|'.join(
            (':' + '-' * (w + 1) if a == '<' else '-' * (w + 1) + ':')
            for a, w in zip(aligns, widths)
        ) + '|')
    else:
        print('=' * table_width)
        print(render(headers))
        print('-' * table_width)

    for cells in rows:
        print(render(cells))

    # Flag rows we could not price so they are not mistaken for absent events.
    unpriced = [r for r in results if r.get('implied_move_pct') is None]
    if priced:
        avg_implied = sum(r['implied_move_pct'] for r in priced) / len(priced)
        biggest = max(priced, key=lambda r: r['implied_move_pct'])
        summary = (
            f"{len(priced)} priced | avg implied +/-{avg_implied:.2f}% | "
            f"largest: {biggest['ticker']} +/-{biggest['implied_move_pct']:.2f}%"
        )
        rich = [r['ticker'] for r in priced if r['verdict'] == 'RICH']
        cheap = [r['ticker'] for r in priced if r['verdict'] == 'CHEAP']
        diluted = [r['ticker'] for r in priced if r['verdict'] == 'DILUTED']
        if markdown:
            # Blank line so the notes do not abut the table and get parsed as
            # part of it; bullets instead of a wall of italic lines.
            print()
            print(f"**{summary}**")
            print()
            if rich:
                print(f"- **RICH** (implied > {RICH_RATIO}x avg realized): {', '.join(rich)}")
            if cheap:
                print(f"- **CHEAP** (implied < {CHEAP_RATIO}x avg realized): {', '.join(cheap)}")
            if diluted:
                print(
                    f"- **DILUTED** (no expiration within {MAX_CLEAN_DAYS_AFTER_EVENT}d of "
                    f"the report; implied includes non-earnings vol): {', '.join(diluted)}"
                )
            if unpriced:
                print(f"- **Not priceable**: {', '.join(r['ticker'] for r in unpriced)}")
            print()
            for line in textwrap.wrap(METHOD_NOTE, width=100):
                print(f"> {line}")
        else:
            print('-' * table_width)
            print(f"  {summary}")
            if rich:
                print(f"  RICH:  {', '.join(rich)}")
            if cheap:
                print(f"  CHEAP: {', '.join(cheap)}")
            if diluted:
                print(f"  DILUTED (expiry >{MAX_CLEAN_DAYS_AFTER_EVENT}d past report): "
                      f"{', '.join(diluted)}")
            if unpriced:
                print(f"  Not priceable: {', '.join(r['ticker'] for r in unpriced)}")
    elif unpriced:
        msg = f"No rows could be priced ({len(unpriced)} candidate(s) had no usable options data)."
        print(f"\n*{msg}*" if markdown else f"\n  {msg}")


def save_json(results: List[Dict[str, Any]], sessions: List[date], path: str) -> None:
    payload = {
        'generated': datetime.now().isoformat(timespec='seconds'),
        'sessions_scanned': [s.isoformat() for s in sessions],
        'count': len(results),
        'stocks': results,
    }
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Earnings expected move from ATM straddle pricing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Next 3 sessions:        python3 earnings_expected_move.py
  Next 2 sessions:        python3 earnings_expected_move.py --sessions 2
  Specific tickers:       python3 earnings_expected_move.py --tickers PLTR VRTX
  Whole calendar:         python3 earnings_expected_move.py --all-calendar
  Markdown briefing:      python3 earnings_expected_move.py --briefing
  Faster (no history):    python3 earnings_expected_move.py --no-history
        """,
    )
    parser.add_argument(
        '--sessions', type=int, default=3,
        help='Trading sessions ahead to scan (default: 3)',
    )
    parser.add_argument('--tickers', nargs='+', help='Ad-hoc tickers (skips calendar filter)')
    parser.add_argument(
        '--all-calendar', action='store_true',
        help='Do not filter to S&P 500 + watchlist',
    )
    parser.add_argument(
        '--min-market-cap', type=float, default=0.0,
        help='Minimum market cap in billions (default: 0 = no filter)',
    )
    parser.add_argument('--limit', type=int, help='Cap number of tickers analyzed')
    parser.add_argument(
        '--include-reported', action='store_true',
        help='Keep names whose earnings already printed (default: dropped)',
    )
    parser.add_argument('--briefing', action='store_true', help='Markdown output')
    parser.add_argument('--no-history', action='store_true', help='Skip realized-move lookback')
    parser.add_argument('--json', action='store_true', help='Print JSON instead of a table')
    parser.add_argument('--no-save', action='store_true', help='Do not write the latest JSON')
    parser.add_argument('--output', help='Path for the JSON snapshot')
    parser.add_argument('--verbose', action='store_true', help='Per-ticker progress')
    args = parser.parse_args()

    if args.sessions < 1:
        print('ERROR: --sessions must be >= 1', file=sys.stderr)
        sys.exit(2)

    sessions = upcoming_sessions(args.sessions)
    sector_map = load_sp500()

    if args.verbose:
        print(f"Scanning {len(sessions)} trading session(s): "
              f"{', '.join(s.isoformat() for s in sessions)}")

    # Build candidate list
    if args.tickers:
        tickers = [t.strip().upper().replace('.', '-') for t in args.tickers]
        calendar_entries = fetch_earnings_calendar(
            sessions, verbose=args.verbose, include_reported=args.include_reported
        )
        by_ticker = {e['ticker']: e for e in calendar_entries}
        entries = []
        for t in tickers:
            if t in by_ticker:
                entries.append(by_ticker[t])
            else:
                # Not in the scanned window - ask Yahoo for its next report date.
                fallback = earnings_date_from_yfinance(t)
                if fallback:
                    entries.append(fallback)
                elif args.verbose:
                    print(f"  {t}: no upcoming earnings date found")
    else:
        entries = fetch_earnings_calendar(
            sessions, verbose=args.verbose, include_reported=args.include_reported
        )
        if not args.all_calendar:
            universe = set(sector_map) | set(load_watchlist_tickers())
            if not universe:
                print(
                    'WARNING: no universe files found '
                    f'({os.path.basename(CONSTITUENTS_FILE)}, '
                    f'{os.path.basename(WATCHLIST_FILE)}); using full calendar.',
                    file=sys.stderr,
                )
            else:
                entries = [e for e in entries if e['ticker'] in universe]
        if args.min_market_cap > 0:
            floor = args.min_market_cap * 1e9
            entries = [
                e for e in entries
                if e.get('market_cap') is None or e['market_cap'] >= floor
            ]

    entries.sort(key=lambda e: (e['report_date'], e['ticker']))
    if args.limit:
        entries = entries[: args.limit]

    if not entries:
        sessions_txt = f"{sessions[0].isoformat()} to {sessions[-1].isoformat()}"
        if args.json:
            print(json.dumps({
                'generated': datetime.now().isoformat(timespec='seconds'),
                'sessions_scanned': [s.isoformat() for s in sessions],
                'count': 0,
                'stocks': [],
            }, indent=2))
        else:
            print_report([], markdown=args.briefing, sessions=sessions)
            print(
                f"\nNo qualifying reporters for {sessions_txt}. "
                "Try --sessions 5, --all-calendar, or --tickers."
            )
        return

    print(f"\nAnalyzing {len(entries)} earnings candidate(s)...", file=sys.stderr)
    results = []
    for entry in entries:
        try:
            results.append(
                analyze_entry(
                    entry,
                    sector_map,
                    include_history=not args.no_history,
                    verbose=args.verbose,
                )
            )
        except KeyboardInterrupt:
            print('\nInterrupted.', file=sys.stderr)
            break
        except Exception as e:  # one bad ticker must not sink the run
            if args.verbose:
                print(f"  {entry['ticker']}: error {type(e).__name__}: {e}")
            results.append({**entry, 'quality': 'ERROR', 'note': f'{type(e).__name__}: {e}',
                            'implied_move_pct': None, 'verdict': 'N/A'})

    results = sort_results(results)

    if args.json:
        print(json.dumps({
            'generated': datetime.now().isoformat(timespec='seconds'),
            'sessions_scanned': [s.isoformat() for s in sessions],
            'count': len(results),
            'stocks': results,
        }, indent=2))
    else:
        print_report(results, markdown=args.briefing, sessions=sessions)

    if not args.no_save:
        out_path = args.output or LATEST_JSON
        try:
            save_json(results, sessions, out_path)
            if not args.json:
                print(f"\nSaved: {out_path}")
        except Exception as e:
            print(f"\nWarning: could not write {out_path}: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
